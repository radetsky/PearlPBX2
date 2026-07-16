import textwrap
import logging
import os

from django.db.models import Q

from core.models import (
    SIPPeer,
    SIPTransport,
    SIPUser,
    Settings,
    DialplanContext,
    DialplanExtension,
    DialplanMacro,
    RoutingTable,
    RoutingRecord,
    ManagerUsers,
    CallQueueGlobalSettings,
    Queue,
    QueueMember,
    QueueRule,
    PenaltyChange,
    MusicOnHold,
    MusicOnHoldPlaylistEntry,
)

from django.conf import settings

logger = logging.getLogger(__name__)

AUTO_GENERATED_HEADER = "; === This is auto generated file. Do not edit it! ===\n"
GENERAL_SECTION = "[general]\n"


def _write_cert_file(write_dir: str, filename: str, content: str) -> None:
    """Write certificate content to file under ASTERISK_ROOT_DIR."""
    os.makedirs(write_dir, exist_ok=True)
    safe_name = os.path.basename(filename)
    path = os.path.join(write_dir, safe_name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with open(fd, "w") as f:
        f.write(content)


def write_tls_cert_files() -> None:
    """Write TLS certificate files to disk. Call only during apply, not preview."""
    cert_dir = os.path.join(settings.ASTERISK_CONFIG_DIR, "certificate")
    cert_write_dir = os.path.normpath(settings.ASTERISK_ROOT_DIR + cert_dir)
    for transport in SIPTransport.objects.filter(protocol="tls"):
        if transport.ca_list_file.strip():
            _write_cert_file(cert_write_dir, f"{transport.name}-ca.crt", transport.ca_list_file)
        if transport.cert_file.strip():
            _write_cert_file(cert_write_dir, f"{transport.name}.crt", transport.cert_file)
        if transport.priv_key_file.strip():
            _write_cert_file(cert_write_dir, f"{transport.name}.key", transport.priv_key_file)


def make_pjsip_conf_transports() -> str:
    result = "; ==== Transports section ====\n"
    cert_dir = os.path.join(settings.ASTERISK_CONFIG_DIR, "certificate")
    transports = SIPTransport.objects.all()
    for transport in transports:
        description = "; " + transport.description + "\n"
        section_name = f"[{transport.name}]\n"
        type_line = "type = transport\n"
        protocol = "protocol = " + transport.protocol + "\n"
        bind = "bind = " + transport.bind + "\n"
        comment_nat = "; NAT Settings\n"

        external_media_address = ""
        if transport.external_media_address is not None:
            external_media_address = (
                "external_media_address = " + transport.external_media_address + "\n"
            )

        external_signaling_address = ""
        if transport.external_signaling_address is not None:
            external_signaling_address = (
                "external_signaling_address = "
                + transport.external_signaling_address
                + "\n"
            )

        local_nets = ""
        if transport.local_nets is not None:
            nets = transport.local_nets.replace(" ", "").split(",")
            for net in nets:
                local_nets += "local_net = " + net + "\n"

        tls_settings = ""
        if transport.protocol == "tls":
            tls_settings += "; TLS Settings\n"
            tls_settings += "allow_reload = " + ("yes" if transport.allow_reload else "no") + "\n"
            tls_settings += "verify_server = " + ("yes" if transport.verify_server else "no") + "\n"
            tls_settings += "method = " + transport.method + "\n"
            if transport.ca_list_file.strip():
                tls_settings += f"ca_list_file = {os.path.join(cert_dir, transport.name + '-ca.crt')}\n"
            if transport.cert_file.strip():
                tls_settings += f"cert_file = {os.path.join(cert_dir, transport.name + '.crt')}\n"
            if transport.priv_key_file.strip():
                tls_settings += f"priv_key_file = {os.path.join(cert_dir, transport.name + '.key')}\n"

        result += (
            description
            + section_name
            + type_line
            + protocol
            + bind
            + comment_nat
            + external_media_address
            + external_signaling_address
            + local_nets
            + tls_settings
        )

        result += "\n"

    return result


def __section_trunk_remote_registration(trunk: SIPPeer):
    reg_host: str | None = (trunk.registration_uri or "").split(",")[0].strip()
    if not reg_host:
        logger.warning(
            f"Trunk {trunk.name} has no registration_uri defined. Skipping remote registration section."
        )
        return "; No registration_uri defined for trunk. Skipping remote registration section.\n"
    if not trunk.username:
        logger.warning(
            f"Trunk {trunk.name} has no username defined. Skipping remote registration section."
        )
        return "; No username defined for trunk. Skipping remote registration section.\n"
    transport: SIPTransport | None = trunk.transport
    if not transport:
        logger.warning(
            f"Trunk {trunk.name} has no transport defined. Skipping remote registration section."
        )
        return "; No transport defined for trunk. Skipping remote registration section.\n"
    if transport.protocol not in ["udp", "tcp", "tls"]:
        logger.warning(
            f"Trunk {trunk.name} has unsupported transport protocol {transport.protocol}. Skipping remote registration section."
        )
        return "; Unsupported transport protocol for trunk. Skipping remote registration section.\n"

    result = "; Registration\n"
    result += f"[{trunk.name}]\n"
    result += "type=registration\n"
    result += f"outbound_auth={trunk.name}\n"
    result += f"server_uri=sip:{reg_host};transport={transport.protocol}\n"
    result += f"client_uri=sip:{trunk.username}@{reg_host};transport={transport.protocol}\n"
    effective_contact_user = (trunk.contact_user or "").strip() or trunk.username
    result += f"contact_user={effective_contact_user}\n"
    result += "retry_interval=60\n"
    result += "forbidden_retry_interval=600\n"
    result += "expiration=3600\n"
    result += "line=yes\n"
    result += f"endpoint={trunk.name}\n"
    result += "\n"

    return result


def __section_trunk_auth_userpass(trunk: SIPPeer):
    custom_auth_settings = getattr(trunk, "custom_auth_settings", None)
    if isinstance(custom_auth_settings, str):
        custom_auth_settings = custom_auth_settings.strip()
    if custom_auth_settings:
        return (
            f"; Custom auth settings for {trunk.name}\n"
            f"[{trunk.name}]\n"
            "type=auth\n"
            f"{custom_auth_settings}\n"
        )
    if getattr(trunk, "username", None) and getattr(trunk, "secret", None):
        result = f"; Authentication\n[{trunk.name}]\ntype=auth\n"
        if trunk.auth_type == "md5":
            result += "auth_type=md5\n"
            result += f"md5_cred={trunk.md5_cred}\n"
            result += f"username={trunk.username}\n"
            result += f"realm={trunk.auth_realm}\n"
        else:
            result += "auth_type=userpass\n"
            result += f"username={trunk.username}\n"
            result += f"password={trunk.secret}\n"
        result += "\n"
        return result
    return ""


def __build_aor_contact_line(trunk: SIPPeer, transport: SIPTransport) -> str:
    host = (trunk.contact_uri or "").split(",")[0].strip()
    if not host:
        return ""
    sip = "sips" if transport.protocol in ["wss", "tls"] else "sip"
    return f"contact={sip}:{host}\n"


def __section_trunk_aor(trunk: SIPPeer):
    custom_aor_settings = (trunk.custom_aor_settings or "").strip()
    if custom_aor_settings:
        return (
            f"; Custom AOR settings for {trunk.name}\n"
            f"[{trunk.name}]\n"
            "type=aor\n"
            f"{custom_aor_settings}\n"
        )

    transport: SIPTransport | None = trunk.transport
    if not transport:
        logger.warning(
            f"Trunk {trunk.name} has no transport defined. Skipping AOR section."
        )
        return "; No transport defined for trunk. Skipping AOR section.\n"

    result = (
        f"; AOR\n[{trunk.name}]\ntype=aor\nqualify_frequency=30\nqualify_timeout=5.0\n"
    )

    if trunk.registrationHere or trunk.registrationThere:
        result += "max_contacts=1\nremove_existing=yes\n"
    else:
        result += __build_aor_contact_line(trunk, transport)

    return result + "\n"


def __section_trunk_endpoint(trunk: SIPPeer) -> str:
    """
    Generates the endpoint section for a SIP trunk.
    """
    if not trunk.transport:
        logger.warning(
            f"Trunk {trunk.name} has no transport defined. Skipping endpoint section."
        )
        return "; No transport defined for trunk. Skipping endpoint section.\n"
    if not trunk.routing_table:
        logger.warning(
            f"Trunk {trunk.name} has no routing table defined. Skipping endpoint section."
        )
        return "; No routing table defined for trunk. Skipping endpoint section.\n"
    lines = [
        "; Endpoint",
        f"[{trunk.name}]",
        "type=endpoint",
        f"transport={trunk.transport.name}",
        f"context={trunk.routing_table.name}",
        "direct_media=no",
        "dtmf_mode=rfc4733",
        "disallow=all",
        "allow=ulaw,alaw",  # TODO: list ALLOWED codecs
    ]

    if trunk.registrationThere or (trunk.username and trunk.secret):
        lines.append(f"outbound_auth={trunk.name}")

    if trunk.registrationHere:
        lines.append(f"auth={trunk.name}")

    lines.append(f"aors={trunk.name}")

    if not trunk.registrationHere and trunk.match_hosts and trunk.match_hosts.strip():
        lines.append("identify_by=ip")

    if (
        trunk.username is not None
        and trunk.username != ""
        and not trunk.registrationHere
    ):
        lines.append(f"from_user={trunk.username}")

    if trunk.nat:
        lines.extend(
            [
                "media_use_received_transport=yes",
                "rtp_symmetric=yes",
                "rewrite_contact=yes",
                "force_rport=yes",
            ]
        )

    lines.append("\n")  # Blank line for separation
    return "\n".join(lines)


def __section_trunk_identify(trunk: SIPPeer) -> str:
    """
    Generates the identify section for a SIP trunk.
    """
    result = [
        "; Identify",
        f"[{trunk.name}]",
        "type=identify",
        f"endpoint={trunk.name}",
    ]

    match_src = trunk.match_hosts
    if match_src:
        for hp in [h.strip() for h in match_src.split(",") if h.strip()]:
            result.append(f"match={hp}")

    result.append("")  # Add a blank line at the end
    return "\n".join(result)


def make_pjsip_conf_uplinks():
    result = "; ==== Uplinks section ====\n"

    trunks = SIPPeer.objects.all()
    for trunk in trunks:
        comment = "; " + trunk.name + "\n"
        result += comment
        # registration
        result += (
            __section_trunk_remote_registration(trunk)
            if trunk.registrationThere
            else "; do not register on the remote side\n"
        )

        # auth
        result += __section_trunk_auth_userpass(trunk)
        # aor
        result += __section_trunk_aor(trunk)
        # endpoint
        result += __section_trunk_endpoint(trunk)
        if trunk.match_hosts and trunk.match_hosts.strip():
            result += __section_trunk_identify(trunk)

        result += "\n"

    result += "\n"
    return result


def make_pjsip_conf_users_template():
    result = "; ==== Users template ====\n"
    result += "[user-template](!)\n"
    settings = Settings.objects.first()
    if settings and settings.user_template:
        user_template = settings.user_template
        if not user_template.endswith("\n"):
            user_template += "\n"
        result += user_template
    result += "\n"
    return result


def make_pjsip_conf_users_aor_template():
    result = "; ==== Users AOR template ====\n"
    result += "[user-aor-template](!)\n"
    settings = Settings.objects.first()
    if settings and settings.user_aor_template:
        user_aor_template = settings.user_aor_template
        if not user_aor_template.endswith("\n"):
            user_aor_template += "\n"
        result += user_aor_template
    result += "qualify_frequency=30\n"
    result += "qualify_timeout=5.0\n"
    result += "\n\n"
    return result


def make_pjsip_conf_users_auth_template():
    result = "; ==== Users AUTH template ====\n"
    result += "[user-auth-template](!)\n"
    settings = Settings.objects.first()
    if settings and settings.user_auth_template:
        user_auth_template = settings.user_auth_template
        if not user_auth_template.endswith("\n"):
            user_auth_template += "\n"
        result += user_auth_template
    result += "\n\n"
    return result


def _with_trailing_newline(value: str | None) -> str:
    """Return the text with a trailing newline, or "" when empty."""
    text = value or ""
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def __make_pjsip_conf_webrtc_user(user: SIPUser):
    assert user.transport is not None
    result = "; ==== WebRTC user ====\n"
    result += f"[{user.username}](webrtc-template-endpoint)\n"
    result += "type=endpoint\n"
    result += f"context={user.username}\n"
    result += f"transport={user.transport.name}\n"
    result += f"auth={user.username}\n"
    result += f"aors={user.username}\n"
    result += f"callerid= {user.name} <{user.extension}>\n"
    result += _with_trailing_newline(user.custom_settings)
    result += "\n"

    result += f"[{user.username}](webrtc-template-auth)\n"
    result += f"md5_cred = {user.md5_cred}\nusername = {user.username}\n"
    result += f"realm = {user.realm}\n"
    result += _with_trailing_newline(user.custom_auth_settings) + "\n"

    result += f"[{user.username}](webrtc-template-aor)\n"
    result += _with_trailing_newline(user.custom_aor_settings) + "\n"

    return result


def get_users_excluded_from_pjsip():
    """Return SIPUsers that will be skipped during pjsip.conf generation."""
    return SIPUser.objects.filter(Q(transport__isnull=True) | Q(routing_table__isnull=True))


def make_pjsip_conf_users():
    result = "; ==== Users section ====\n"
    excluded_ids = get_users_excluded_from_pjsip().values_list("pk", flat=True)
    users = SIPUser.objects.exclude(pk__in=excluded_ids)
    for user in users:

        if user.transport.protocol == "wss":
            result += __make_pjsip_conf_webrtc_user(user)
            continue

        result += "; " + user.name + "\n"
        result += f"[{user.username}](user-template)\n"
        result += f"transport={user.transport.name}\n"
        result += f"auth={user.username}\n"
        result += f"aors={user.username}\n"
        result += f"callerid={user.name} <{user.extension}>\n"
        result += f"context={user.routing_table.name}\n"
        result += "dtmf_mode=rfc4733\n"
        result += "direct_media=no\n"
        if user.nat:
            result += "media_use_received_transport=yes\n"
            result += "rtp_symmetric=yes\n"
            result += "rewrite_contact=yes\n"
            result += "force_rport=yes\n"
        result += (user.custom_settings or "") + "\n\n"

        result += f"[{user.username}](user-auth-template)\n"
        if user.auth_type == SIPUser.AUTHTYPE_CHOICES[0][0]:  # userpass
            result += "type = auth\n"
            result += "auth_type = userpass\n"
            result += f"username = {user.username}\n"
            result += f"password = {user.secret}\n"
        else:
            result += "type = auth\n"
            result += "auth_type = md5\n"
            result += f"md5_cred = {user.md5_cred}\n"
            result += f"username = {user.username}\n"
            result += f"realm = {user.realm}\n"

        result += (user.custom_auth_settings or "") + "\n\n"

        result += f"[{user.username}](user-aor-template)\n"
        result += (user.custom_aor_settings or "") + "\n\n"

        result += "\n"

    return result


def make_pjsip_webrtc_templates():
    qs = SIPTransport.objects.filter(protocol="wss")
    if len(qs) == 0:
        return ""

    settings = Settings.objects.first()
    if not settings:
        return ""

    result = "; ==== WebRTC templates ====\n"
    result += """; WebRTC Template for Endpoint
; -----------
[webrtc-template-endpoint](!)\n"""
    if settings.webrtc_template:
        result += settings.webrtc_template
    result += "\n\n"

    result += """; WebRTC Template for AOR
; -----------
[webrtc-template-aor](!)\n"""
    if settings.webrtc_aor_template:
        result += settings.webrtc_aor_template
    result += "\n\n"

    result += """; WebRTC Template for Auth
; -----------
[webrtc-template-auth](!)\n"""
    if settings.webrtc_auth_template:
        result += settings.webrtc_auth_template
    result += "\n\n"

    return result


def make_pjsip_conf():
    plaintext = AUTO_GENERATED_HEADER
    plaintext += ";=== Use PearlPBX admin panel! ===\n"
    plaintext += make_pjsip_conf_transports()
    plaintext += make_pjsip_webrtc_templates()
    plaintext += make_pjsip_conf_uplinks()
    plaintext += make_pjsip_conf_users_template()
    plaintext += make_pjsip_conf_users_aor_template()
    plaintext += make_pjsip_conf_users_auth_template()
    plaintext += make_pjsip_conf_users()

    return plaintext


def make_queuerules_conf() -> str:
    """Generates the contents of the queuerules.conf configuration file from the QueueRule and PenaltyChange models.
    Returns a string ready to be written to a file.
    """

    output = []
    output.append(GENERAL_SECTION)
    output.append(AUTO_GENERATED_HEADER)

    for rule in QueueRule.objects.all():
        output.append(f"[{rule.name}]")
        if rule.description:
            output.append(f"; {rule.description}")
        penalty_changes = PenaltyChange.objects.filter(rule=rule).order_by(
            "seconds", "order"
        )

        for change in penalty_changes:
            parts = [
                str(change.seconds),
                change.max_penalty,
                change.min_penalty,
                change.raise_penalty,
            ]
            while parts and parts[-1] == "":
                parts.pop()
            output.append(f"penaltychange => {','.join(parts)}")
        output.append("")

    return "\n".join(output)


def _opt(key: str, value, default_comment: str = "") -> str:
    """Return config line or commented placeholder if value is falsy."""
    if value:
        return f"{key}={value}"
    return f";{key}={default_comment}" if default_comment else f";{key}"


def _bool_opt(key: str, value) -> str:
    """Return config line for boolean value."""
    return f"{key}={'yes' if value else 'no'}"


def _make_queue_announcement_lines(ann) -> list[str]:
    """Generate announcement configuration lines."""
    fields = [
        ("queue-youarenext", ann.queue_youarenext),
        ("queue-thereare", ann.queue_thereare),
        ("queue-callswaiting", ann.queue_callswaiting),
        ("queue-quantity1", ann.queue_quantity1),
        ("queue-quantity2", ann.queue_quantity2),
        ("queue-holdtime", ann.queue_holdtime),
        ("queue-minute", ann.queue_minute),
        ("queue-minutes", ann.queue_minutes),
        ("queue-seconds", ann.queue_seconds),
        ("queue-thankyou", ann.queue_thankyou),
        ("queue-reporthold", ann.queue_reporthold),
    ]
    return [_opt(key, value) for key, value in fields]


def _make_single_queue_config(queue: Queue) -> list[str]:
    """Generate configuration lines for a single queue."""
    output = [f"[{queue.name}]"]

    output.append(
        f"musicclass={queue.music_class.name}" if queue.music_class else ";musicclass"
    )
    output.append(_opt("announce", queue.announce))
    output.append(_opt("queue_announce", queue.queue_announce))
    output.append(f"strategy={queue.strategy}")
    output.append(_opt("maxlen", queue.maxlen, "0"))
    output.append(f"weight={queue.weight}")
    output.append(_bool_opt("setqueuevar", queue.setqueuevar))
    output.append(_bool_opt("random-periodic-announce", queue.random_periodic_announce))
    output.append(_opt("servicelevel", queue.service_level, "0"))
    output.append(_opt("context", queue.context))
    output.append(_opt("timeout", queue.timeout, "15"))
    output.append(_opt("retry", queue.retry, "5"))
    output.append(_opt("timeoutpriority", queue.timeoutpriority, "app"))
    output.append(_opt("wrapuptime", queue.wrapuptime, "0"))

    output.append(_bool_opt("autofill", queue.autofill))
    output.append(f"autopause={queue.autopause}")
    output.append(f"autopausedelay={queue.autopausedelay}")
    output.append(_bool_opt("reportholdtime", queue.reportholdtime))
    output.append(_bool_opt("setinterfacevar", queue.setinterfacevar))
    output.append(_bool_opt("setqueueentryvar", queue.setqueueentryvar))

    output.append(f"announce-frequency={queue.announce_frequency}")
    output.append(f"announce-holdtime={queue.announce_holdtime}")
    output.append(f"min-announce-frequency={queue.min_announce_frequency}")
    output.append(f"periodic-announce-frequency={queue.periodic_announce_frequency}")
    output.append(
        _bool_opt("relative-periodic-announce", queue.relative_periodic_announce)
    )
    output.append(f"announce-position={queue.announce_position}")
    output.append(_bool_opt("announce-to-first-user", queue.announce_to_first_user))
    output.append(f"announce-position-limit={queue.announce_position_limit}")
    output.append(f"announce-round-seconds={queue.announce_round_seconds}")
    output.append(
        _bool_opt("announce-position-only-up", queue.announce_position_only_up)
    )

    if queue.queue_announcement:
        output.extend(_make_queue_announcement_lines(queue.queue_announcement))

    output.append(_opt("periodic-announce", queue.periodic_announce))
    output.append(_opt("monitor-format", queue.monitor_format))
    output.append(f"joinempty={queue.joinempty}")
    output.append(f"leavewhenempty={queue.leavewhenempty}")
    output.append(f"ringinuse={queue.__ringinuse__()}")
    output.append(f"timeoutrestart={queue.__timeoutrestart__()}")
    output.append(
        _opt("defaultrule", queue.defaultrule.name if queue.defaultrule else None)
    )

    for member in QueueMember.objects.filter(queue=queue):
        output.append(
            f"member => {member.interface},{member.penalty},{member.member_name},"
            f"{member.__state_interface__()},{member.__ringinuse__()},{member.wrapuptime}"
        )

    return output


def make_queues_configurations() -> str:
    output = []
    for queue in Queue.objects.all():
        output.extend(_make_single_queue_config(queue))
    return "\n".join(output)


def make_queues_conf():
    plaintext = AUTO_GENERATED_HEADER
    plaintext += "; === Use PearlPBX admin panel! ===\n"
    plaintext += "; ==== General section ====\n"
    plaintext += GENERAL_SECTION

    global_settings = CallQueueGlobalSettings.objects.first()
    if global_settings:
        plaintext += f"persistent_members = {'yes' if global_settings.persistent_members else 'no'}\n"
        plaintext += f"autofill = {'yes' if global_settings.autofill else 'no'}\n"
        plaintext += f"monitor-type = {global_settings.monitor_type}\n"
        plaintext += (
            f"shared_lastcall = {'yes' if global_settings.shared_lastcall else 'no'}\n"
        )
        plaintext += f"negative_penalty_invalid = {'yes' if global_settings.negative_penalty_invalid else 'no'}\n"
        plaintext += f"log_membername_as_agent = {'yes' if global_settings.log_membername_as_agent else 'no'}\n"
        plaintext += f"force_longest_waiting_caller = {'yes' if global_settings.force_longest_waiting_caller else 'no'}\n"
    else:
        plaintext += "persistent_members = yes\n"
        plaintext += "autofill = yes\n"
        plaintext += "monitor-type = MixMonitor\n"
        plaintext += "shared_lastcall = no\n"
        plaintext += "negative_penalty_invalid = yes\n"
        plaintext += "log_membername_as_agent = yes\n"
        plaintext += "force_longest_waiting_caller = no\n"

    plaintext += "; ==== Queues section ====\n"
    plaintext += make_queues_configurations()

    return plaintext


def make_dialplan_extension(extension):
    plaintext = f"    // {extension.description}\n"
    plaintext += f"    {extension.ext} => " + "{\n"
    cleaned_text = extension.dialplan.replace("\r", "")
    indented_text = textwrap.indent(cleaned_text, " " * 8)
    plaintext += indented_text
    if not indented_text.endswith("\n"):
        plaintext += "\n"

    plaintext += "    }\n"
    return plaintext


def _asterisk_pattern_specificity(ext_pattern: str) -> tuple:
    """
    Returns a tuple for sorting: higher specificity comes first.
    1. More literal digits/letters (not X, !, [], etc)
    2. Fewer wildcards (X, !, [], etc)
    3. Longer pattern
    4. '_X!' always last
    """
    if ext_pattern == "_X!":
        return (0, 0, 0, 1)
    # Remove leading underscore
    pattern = ext_pattern[1:] if ext_pattern.startswith("_") else ext_pattern
    # Count literal chars (digits/letters)
    literal_count = sum(1 for c in pattern if c.isdigit() or c.isalpha())
    # Count wildcards
    wildcard_count = (
        pattern.count("X")
        + pattern.count("!")
        + pattern.count("[")
        + pattern.count("]")
    )
    # Length
    length = len(pattern)
    # _X! always last
    is_xbang = 1 if ext_pattern == "_X!" else 0
    # Sort by: more literal, fewer wildcards, longer, not _X!
    return (literal_count, -wildcard_count, length, -is_xbang)


def make_dialplan_contexts():
    plaintext = "// ==== Printing data of dialplan contexts in PBX admin panel ====\n"
    plaintext += "// ==== Dialplan contexts ====\n"
    for context in DialplanContext.objects.all():
        plaintext += f"// {context.description}\n"
        plaintext += f"context {context.name} {{\n"
        # Get all extensions for this context and sort them
        extensions = list(DialplanExtension.objects.filter(context=context))
        extensions.sort(
            key=lambda ext: _asterisk_pattern_specificity(ext.ext), reverse=True
        )
        for extension in extensions:
            plaintext += make_dialplan_extension(extension)
        plaintext += "}\n"
    return plaintext


def make_dialplan_macros():
    plaintext = "// ==== Macros ====\n"
    for macro in DialplanMacro.objects.all():
        plaintext += f"// {macro.description}\n"
        plaintext += f"macro {macro.name}() " + "{\n"
        cleaned_text = macro.macro.replace("\r", "")
        indented_text = textwrap.indent(cleaned_text, " " * 4)
        plaintext += indented_text
        if not indented_text.endswith("\n"):
            plaintext += "\n"
        plaintext += "}\n"

    return plaintext


def make_routing_tables():
    plaintext = "// ==== Routing tables ==== \n"
    for rt in RoutingTable.objects.all():
        plaintext += f"context {rt.name} " + "{\n"
        # Get all RoutingRecords for this table and sort them by Asterisk specificity
        records = list(RoutingRecord.objects.filter(routing_table=rt))
        records.sort(
            key=lambda rec: _asterisk_pattern_specificity(rec.prefix), reverse=True
        )
        for dir in records:
            plaintext += f"    // {dir.name}\n"
            plaintext += (
                f"    {dir.prefix} => "
                + "{ goto "
                + f"{dir.context},"
                + "${EXTEN},1; }\n"
            )
        plaintext += "}\n"
    return plaintext


def make_extensions_ael():
    plaintext = "// === This is auto generated file. Do not edit it! ===\n"
    plaintext += "// === Use PearlPBX admin panel! ===\n"
    plaintext += make_dialplan_macros()
    plaintext += make_routing_tables()
    plaintext += make_dialplan_contexts()
    return plaintext


def make_manager_conf():
    plaintext = AUTO_GENERATED_HEADER
    plaintext += "; === Use PearlPBX admin panel! ===\n"

    manager_port = settings.ASTERISK_MANAGER_PORT
    manager_username = settings.ASTERISK_MANAGER_USERNAME
    manager_secret = settings.ASTERISK_MANAGER_SECRET
    manager_bind = settings.ASTERISK_MANAGER_BIND

    plaintext += GENERAL_SECTION
    plaintext += "enabled = yes\n"
    plaintext += "webenabled = yes\n"
    plaintext += f"port = {manager_port}\n"
    plaintext += f"bindaddr = {manager_bind}\n"
    plaintext += "displayconnects = yes\n"
    plaintext += "timestampevents = yes\n"
    plaintext += "authtimeout = 10\n"
    plaintext += "authlimit = 10\n"
    plaintext += "httptimeout = 60\n"
    plaintext += f"[{manager_username}]\n"
    plaintext += "displayconnects = yes\n"
    plaintext += f"secret = {manager_secret}\n"
    plaintext += "read = system,call,log,verbose,command,agent,user\n"
    plaintext += "write = system,call,log,verbose,command,agent,user\n"
    plaintext += "writetimeout = 5000\n"
    plaintext += "eventfilter=!Event: RTCP*|!Event: VarSet|!Event: Cdr\n"

    manager_users = ManagerUsers.objects.all()
    for user in manager_users:
        plaintext += f"[{user.username}]\n"
        plaintext += f"secret = {user.secret}\n"
        plaintext += f"read = {user.read}\n"
        plaintext += f"write = {user.write}\n"
        plaintext += (
            f"writetimeout = {user.writetimeout}\n" if user.writetimeout else ""
        )
        plaintext += f"eventfilter = {user.eventfilter}\n" if user.eventfilter else ""
        plaintext += f"deny = {user.deny}\n" if user.deny else ""
        plaintext += f"permit = {user.permit}\n" if user.permit else ""
        plaintext += f"acl = {user.acl}\n" if user.acl else ""
        plaintext += "\n"

    return plaintext


def _make_moh_files_config(moh: MusicOnHold) -> str:
    """Generate config for files mode MOH class."""
    directory = moh.directory or "moh"
    result = f"directory=moh/{directory}\n"
    if moh.sort:
        result += f"sort={moh.sort}\n"
    return result


def _make_moh_playlist_config(moh: MusicOnHold) -> str:
    """Generate config for playlist mode MOH class."""
    lines = []
    for entry in MusicOnHoldPlaylistEntry.objects.filter(moh_class=moh):
        if entry.file:
            file_without_ext = str(entry.file).rsplit(".", 1)[0]
            lines.append(f"entry=/var/lib/asterisk/moh/{file_without_ext}")
        elif entry.url:
            lines.append(f"entry={entry.url}")
    return "\n".join(lines) + "\n" if lines else ""


def make_musiconhold_conf():
    plaintext = AUTO_GENERATED_HEADER
    plaintext += "; === Use PearlPBX admin panel! ===\n\n"
    plaintext += GENERAL_SECTION
    plaintext += "cachertclasses=yes\n"
    plaintext += "preferchannelclass=yes\n\n"

    for moh in MusicOnHold.objects.all():
        plaintext += f"[{moh.name}]\nmode={moh.mode}\n"

        if moh.mode == "files":
            plaintext += _make_moh_files_config(moh)
        elif moh.mode == "playlist":
            plaintext += _make_moh_playlist_config(moh)

        plaintext += "\n"

    return plaintext
