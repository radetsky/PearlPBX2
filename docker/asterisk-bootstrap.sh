#!/bin/sh
# Seeds Asterisk config that must exist before Asterisk's first boot into the
# shared config volume. Docker auto-populates an empty volume from the
# andrius/asterisk:22 image's baked-in defaults as soon as any container
# mounts it, which can race ahead of the asterisk-init -> asterisk dependency
# ordering — so each step below checks for its own "already handled" marker
# rather than assuming an empty volume.
set -e

CONF_DIR=/etc/asterisk
mkdir -p "$CONF_DIR"

SOUNDS_EN_DIR=/var/lib/asterisk/sounds/en
CORE_SOUNDS_URL="https://downloads.asterisk.org/pub/telephony/sounds/asterisk-core-sounds-en-gsm-current.tar.gz"

# manager.conf: the image ships with AMI disabled (enabled = no). Django's
# "Apply Changes" reloads Asterisk over AMI, and the AMI client used by
# fastagi/dashboard-listener/callback-service also needs it live — but there
# is no other way to enable it on a fresh volume, since reaching Asterisk's
# CLI to run "manager reload" is not possible from other containers. This
# breaks that chicken-and-egg problem once, using the same
# ASTERISK_MANAGER_* credentials core/conf.py's make_manager_conf() will
# later generate, so a subsequent "Apply Changes" overwrites this file with
# equivalent content and the existing AMI session keeps working.
#
# Idempotent: does nothing once Django has applied a real config (its output
# is stamped with this marker — see core.conf.AUTO_GENERATED_HEADER). A
# manager.conf without the marker is either missing or the vendor image's
# own disabled-AMI default — both get (re)written.
bootstrap_manager_conf() {
    CONF_FILE="$CONF_DIR/manager.conf"
    DJANGO_MARKER="This is auto generated file. Do not edit it!"

    if [ -f "$CONF_FILE" ] && grep -q "$DJANGO_MARKER" "$CONF_FILE" 2>/dev/null; then
        echo "manager.conf already applied by Django, skipping bootstrap"
        return 0
    fi

    cat > "$CONF_FILE" <<EOF
[general]
enabled = yes
webenabled = yes
port = ${ASTERISK_MANAGER_PORT:-5038}
bindaddr = ${ASTERISK_MANAGER_BIND:-0.0.0.0}
displayconnects = yes

[${ASTERISK_MANAGER_USERNAME:-admin}]
secret = ${ASTERISK_MANAGER_SECRET:-admin}
read = system,call,log,verbose,command,agent,user
write = system,call,log,verbose,command,agent,user
EOF

    echo "Bootstrap manager.conf written for user '${ASTERISK_MANAGER_USERNAME:-admin}'"
}

# modules.conf: several modules the vendor image ships on disk are never
# loaded because the image's default modules.conf (autoload = no, explicit
# load = list) doesn't list them:
#   - res_crypto.so: required by the image's own healthcheck.sh.
#   - res_srtp.so: required for DTLS-SRTP, i.e. any WebRTC (wss) call —
#     without it, res_pjsip_sdp_rtp.c logs "Attempted to set an invalid
#     DTLS-SRTP configuration" and the call fails to negotiate.
# This is a vendor image inconsistency, not something core/conf.py generates
# or manages — Django never touches modules.conf, so this fix persists
# across "Apply Changes" runs. Each module is checked and appended
# independently so a volume that already has one but not the other (e.g.
# from a manual patch) still gets fixed up.
#
# codec_opus.so is deliberately NOT added here: the andrius/asterisk:22
# image only ships the Opus runtime library (libopus.so) and
# res_format_attr_opus.so, not the codec_opus.so translator module itself
# (confirmed absent from /usr/lib/asterisk/modules — the image was built
# without libopus-dev). Adding a "load =" line for a module file that
# doesn't exist just logs a warning on every start. WebRTC endpoints still
# negotiate audio via the g722/ulaw entries already in the webrtc_template
# allow list (core/models.py Settings.webrtc_template) without it.
bootstrap_modules_conf() {
    MODULES_FILE="$CONF_DIR/modules.conf"

    if [ ! -f "$MODULES_FILE" ]; then
        echo "modules.conf not present yet, skipping module patches"
        return 0
    fi

    for module in res_crypto.so res_srtp.so; do
        if grep -q "load = $module" "$MODULES_FILE" 2>/dev/null; then
            echo "modules.conf already loads $module, skipping"
            continue
        fi
        {
            echo ""
            echo "; Added by docker/asterisk-bootstrap.sh — present on disk in the"
            echo "; andrius/asterisk:22 image but not loaded by its default modules.conf."
            echo "load = $module"
        } >> "$MODULES_FILE"
        echo "Patched modules.conf: added $module"
    done
}

# Core sounds: the andrius/asterisk:22 image ships /var/lib/asterisk/sounds
# completely empty — no standard prompts at all (confirmed: only our own
# custom files, seeded separately by Django's SoundFile model, ever land
# there). Anything seed_quickstart's dialplan plays via a stock prompt name
# (demo-echotest, agent-loginok, agent-loggedoff, vm-goodbye, invalid,
# queue-*) is otherwise silent. Downloads the official GSM-encoded package
# once — GSM keeps the download small and needs no transcoding module beyond
# what the image already loads.
#
# Idempotent: skipped once a known file from the package is already present
# (covers both a prior run of this script and a volume carried over from an
# image that already had it).
bootstrap_core_sounds() {
    if [ -f "$SOUNDS_EN_DIR/demo-echotest.gsm" ]; then
        echo "Core sounds already installed, skipping"
        return 0
    fi

    mkdir -p "$SOUNDS_EN_DIR"
    echo "Downloading asterisk-core-sounds-en-gsm..."
    if wget -qO /tmp/core-sounds.tar.gz "$CORE_SOUNDS_URL"; then
        tar -xzf /tmp/core-sounds.tar.gz -C "$SOUNDS_EN_DIR"
        rm -f /tmp/core-sounds.tar.gz
        echo "Core sounds installed into $SOUNDS_EN_DIR"
    else
        echo "WARNING: could not download core sounds from $CORE_SOUNDS_URL — prompts will stay silent until this succeeds on a future start"
    fi
}

# http.conf: needed for WebRTC (wss) SIP transports — PJSIP's websocket
# transport rides on Asterisk's built-in HTTP server, which the vendor image
# ships disabled and bound to 127.0.0.1. core/conf.py does not generate this
# file (see project memory), so it's not covered by Django's "Apply Changes"
# and must be seeded here like manager.conf.
#
# Idempotent: skipped once the file already has enabled=yes (covers both a
# prior run of this script and a manually edited file).
bootstrap_http_conf() {
    CONF_FILE="$CONF_DIR/http.conf"

    if [ -f "$CONF_FILE" ] && grep -q "^enabled=yes" "$CONF_FILE" 2>/dev/null; then
        echo "http.conf already enabled, skipping bootstrap"
        return 0
    fi

    cat > "$CONF_FILE" <<EOF
[general]
enabled=yes
bindaddr=0.0.0.0
bindport=8088
prefix=asterisk
EOF

    echo "Bootstrap http.conf written (websocket transport for WebRTC)"
}

bootstrap_manager_conf
bootstrap_modules_conf
bootstrap_http_conf
bootstrap_core_sounds
