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

# modules.conf: the image's own healthcheck.sh requires res_crypto (among
# other modules) to be loaded, but the image's own default modules.conf
# (autoload = no, explicit load = list) does not load it — the module file
# is present on disk, it is just never listed. Confirmed harmless to load
# manually (no certs/config needed: `module load res_crypto.so` just works).
# This is a vendor image inconsistency, not something core/conf.py generates
# or manages — Django never touches modules.conf, so this fix persists
# across "Apply Changes" runs.
bootstrap_modules_conf() {
    MODULES_FILE="$CONF_DIR/modules.conf"

    if [ ! -f "$MODULES_FILE" ]; then
        echo "modules.conf not present yet, skipping res_crypto patch"
        return 0
    fi
    if grep -q "res_crypto" "$MODULES_FILE" 2>/dev/null; then
        echo "modules.conf already references res_crypto, skipping"
        return 0
    fi

    {
        echo ""
        echo "; Added by docker/asterisk-bootstrap.sh — the andrius/asterisk:22"
        echo "; image's own healthcheck.sh requires this module, but the vendor"
        echo "; default modules.conf (autoload = no) does not load it."
        echo "load = res_crypto.so"
    } >> "$MODULES_FILE"

    echo "Patched modules.conf: added res_crypto.so"
}

bootstrap_manager_conf
bootstrap_modules_conf
