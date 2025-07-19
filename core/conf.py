import textwrap
import logging

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
)

from django.conf import settings

logger = logging.getLogger(__name__)


def make_pjsip_conf_transports() -> str:
    result = "; ==== Transports section ====\n"
    transports = SIPTransport.objects.all()
    for transport in transports:
        description = "; " + transport.description + "\n"
        section_name = f"[{transport.name}]\n"  # FIXME validate it
        type = "type = transport\n"
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

        result += (
            description
            + section_name
            + type
            + protocol
            + bind
            + comment_nat
            + external_media_address
            + external_signaling_address
            + local_nets
        )

        result += "\n"

    return result


def __section_trunk_remote_registration(trunk: SIPPeer):
    host_port: str | None = trunk.host_port
    if not host_port:
        logger.warning(
            f"Trunk {trunk.name} has no host_port defined. Skipping remote registration section."
        )
        return (
            "; No host_port defined for trunk. Skipping remote registration section.\n"
        )
    hosts_and_ports = host_port.split(",")
    if len(hosts_and_ports) == 0:
        logger.warning(
            f"Trunk {trunk.name} has no valid host_port defined. Skipping remote registration section."
        )
        return "; No valid host_port defined for trunk. Skipping remote registration section.\n"
    transport: SIPTransport | None = trunk.transport
    if not transport:
        logger.warning(
            f"Trunk {trunk.name} has no transport defined. Skipping remote registration section."
        )
        return (
            "; No transport defined for trunk. Skipping remote registration section.\n"
        )
    if transport.protocol not in ["udp", "tcp", "tls"]:
        logger.warning(
            f"Trunk {trunk.name} has unsupported transport protocol {transport.protocol}. Skipping remote registration section."
        )
        return "; Unsupported transport protocol for trunk. Skipping remote registration section.\n"

    result = "; Registration\n"
    result += f"[{trunk.name}]\n"
    result += "type=registration\n"
    result += f"outbound_auth={trunk.name}\n"
    result += f"server_uri=sip:{hosts_and_ports[0]};transport={transport.protocol}\n"
    result += f"client_uri=sip:{trunk.username}@{hosts_and_ports[0]};transport={transport.protocol}\n"
    result += f"contact_user={trunk.username}\n"
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
        return (
            f"; Authentication\n"
            f"[{trunk.name}]\n"
            "type=auth\n"
            "auth_type=userpass\n"
            f"username={trunk.username}\n"
            f"password={trunk.secret}\n"
            "\n"
        )
    return ""


def __section_trunk_aor(trunk: SIPPeer):
    custom_aor_settings = trunk.custom_aor_settings
    if custom_aor_settings:
        #  trim and check for empty string
        custom_aor_settings = custom_aor_settings.strip()
        if custom_aor_settings:
            result = f"; Custom AOR settings for {trunk.name}\n"
            result += f"[{trunk.name}]\n"
            result += "type=aor\n"
            result += custom_aor_settings + "\n"
            return result

    transport: SIPTransport | None = trunk.transport
    if not transport:
        logger.warning(
            f"Trunk {trunk.name} has no transport defined. Skipping AOR section."
        )
        return "; No transport defined for trunk. Skipping AOR section.\n"
    host_port: str | None = trunk.host_port
    result = "; AOR\n"
    result += f"[{trunk.name}]\n"
    result += "type=aor\n"
    result += "qualify_frequency=30\n"
    result += "qualify_timeout=5.0\n"
    if trunk.registrationHere or trunk.registrationThere:
        result += "max_contacts=1\n"
        result += "remove_existing=yes\n"
    elif host_port:
        hosts_and_ports = host_port.split(",")
        if len(hosts_and_ports) > 0:
            username = f"{trunk.username}@" if trunk.username else ""
            if transport.protocol in ["wss", "tls"]:
                sip = "sips"
            else:
                sip = "sip"
            result += f"contact={sip}:{username}{hosts_and_ports[0]};transport={transport.protocol}\n"
    result += "\n"
    return result


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

    if not trunk.registrationHere:
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

    host_port = trunk.host_port
    if host_port:
        hosts_and_ports = [hp.strip() for hp in host_port.split(",") if hp.strip()]
        for hp in hosts_and_ports:
            host, _port = hp.split(":") if ":" in hp else (hp, None)
            result.append(f"match={host}")

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
        # identify
        result += __section_trunk_identify(trunk)

        result += "\n"

    result += "\n"
    return result


def make_pjsip_conf_users_template():
    result = "; ==== Users template ====\n"
    result += "[user-template](!)\n"
    settings = Settings.objects.first()
    user_template = settings.user_template
    if user_template and not user_template.endswith("\n"):
        user_template += "\n"
        result += user_template
    result += "\n"
    return result


def make_pjsip_conf_users_aor_template():
    result = "; ==== Users AOR template ====\n"
    result += "[user-aor-template](!)\n"
    settings = Settings.objects.first()
    user_aor_template = settings.user_aor_template
    if user_aor_template and not user_aor_template.endswith("\n"):
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
    user_auth_template = settings.user_auth_template
    if not user_auth_template.endswith("\n"):
        user_auth_template += "\n"
    result += user_auth_template
    result += "\n\n"
    return result


def __make_pjsip_conf_webrtc_user(user: SIPUser):
    result = "; ==== WebRTC user ====\n"
    result += f"[{user.username}](webrtc-template-endpoint)\n"
    result += "type=endpoint\n"
    result += f"context={user.username}\n"
    result += f"transport={user.transport.name}\n"
    result += f"auth={user.username}\n"
    result += f"aors={user.username}\n"
    result += f"callerid= {user.name} <{user.extension}>\n"
    custom_settings = user.custom_settings
    if custom_settings and not custom_settings.endswith("\n"):
        custom_settings += "\n"
        result += custom_settings
    result += "\n"

    result += f"[{user.username}](webrtc-template-auth)\n"
    result += f"md5_cred = {user.md5_cred}\nusername = {user.username}\n"
    result += f"realm = {user.realm}\n"
    custom_auth_settings = user.custom_auth_settings
    if custom_auth_settings and not custom_auth_settings.endswith("\n"):
        custom_auth_settings += "\n"
        result += custom_auth_settings + "\n"

    result += f"[{user.username}](webrtc-template-aor)\n"
    custom_aor_settings = user.custom_aor_settings
    if custom_aor_settings and not custom_aor_settings.endswith("\n"):
        custom_aor_settings += "\n"
        result += custom_aor_settings + "\n"

    return result


def make_pjsip_conf_users():
    result = "; ==== Users section ====\n"
    users = SIPUser.objects.all()
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
        result += user.custom_settings + "\n\n"

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

        result += user.custom_auth_settings + "\n\n"

        result += f"[{user.username}](user-aor-template)\n"
        result += user.custom_aor_settings + "\n\n"

        result += "\n"

    return result


def make_pjsip_webrtc_templates():
    qs = SIPTransport.objects.filter(protocol="wss")
    if len(qs) == 0:
        return ""

    result = "; ==== WebRTC templates ====\n"
    result += """; WebRTC Template for Endpoint
; -----------
[webrtc-template-endpoint](!)\n"""
    settings = Settings.objects.first()
    result += settings.webrtc_template
    result += "\n\n"

    result += """; WebRTC Template for AOR
; -----------
[webrtc-template-aor](!)\n"""
    result += settings.webrtc_aor_template
    result += "\n\n"

    result += """; WebRTC Template for Auth
; -----------
[webrtc-template-auth](!)\n"""
    result += settings.webrtc_auth_template
    result += "\n\n"

    return result


def make_pjsip_conf():
    plaintext = "; === This is auto generated file. Do not edit it! ===\n"
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
    output.append("[general]\n")
    output.append("; === This is auto generated file. Do not edit it! ===\n")

    for rule in QueueRule.objects.prefetch_related("penalty_changes").all():
        output.append(f"[{rule.name}]")
        if rule.description:
            output.append(f"; {rule.description}")
        penalty_changes = rule.penalty_changes.all().order_by("seconds", "order")

        for change in penalty_changes:
            parts = [str(change.seconds)]
            parts.append(str(change.max_penalty) or "")
            parts.append(str(change.min_penalty) or "")
            parts.append(str(change.raise_penalty) or "")
            parts.append(str(change.order) or "")

            while parts and parts[-1] == "":
                parts.pop()

            output.append(f"penaltychange => {','.join(parts)}")
        output.append("")

    return "\n".join(output)


def make_queues_configurations() -> str:
    queues = Queue.objects.all()
    output = []
    for queue in queues:
        output.append(f"[{queue.name}]")
        output.append(
            f"musicclass={queue.music_class.name}"
            if queue.music_class
            else ";musicclass"
        )
        output.append(f"announce={queue.announce}" if queue.announce else ";announce=")
        output.append(
            f"queue_announce={queue.queue_announce}"
            if queue.queue_announce
            else ";queue_announce="
        )
        output.append(f"strategy={queue.strategy}")  # 'ringall', 'leastrecent', etc.
        output.append(
            f"servicelevel={queue.service_level}"
            if queue.service_level
            else ";servicelevel = 0"
        )
        output.append(f"context={queue.context}" if queue.context else ";context=")
        output.append(f"timeout={queue.timeout}" if queue.timeout else ";timeout=15")
        output.append(f"retry={queue.retry}" if queue.retry else ";retry=5")
        output.append(
            f"timeoutpriority={queue.timeoutpriority}"
            if queue.timeoutpriority
            else ";timeoutpriority=app"
        )
        output.append(
            f"wrapuptime={queue.wrapuptime}" if queue.wrapuptime else ";wrapuptime=0"
        )
        output.append("autofill=yes" if queue.autofill else "autofill=no")
        output.append(f"autopause={queue.autopause}")
        output.append(f"autopausedelay={queue.autopausedelay}")
        output.append(
            "reportholdtime=yes" if queue.reportholdtime else "reportholdtime=no"
        )
        output.append(
            "setinterfacevar=yes" if queue.setinterfacevar else "setinterfacevar=no"
        )
        output.append(
            "setqueueentryvar=yes" if queue.setqueueentryvar else "setqueueentryvar=no"
        )
        output.append(f"announce-frequency={queue.announce_frequency}")
        output.append(
            "announce-holdtime=yes"
            if queue.announce_holdtime
            else "announce-holdtime=no"
        )
        output.append(f"min-announce-frequency={queue.min_announce_frequency}")
        output.append(
            f"periodic-announce-frequency={queue.periodic_announce_frequency}"
        )
        output.append(
            "periodic-announce-frequency=yes"
            if queue.periodic_announce_frequency
            else "periodic-announce-frequency=no"
        )
        output.append(
            "relative-periodic-announce=yes"
            if queue.relative_periodic_announce
            else "relative-periodic-announce=no"
        )
        output.append(f"announce-holdtime={queue.announce_holdtime}")
        output.append(f"announce-position={queue.announce_position}")
        output.append(
            "announce-to-first-user=yes"
            if queue.announce_to_first_user
            else "announce-to-first-user=no"
        )
        output.append(f"announce-position-limit={queue.announce_position_limit}")
        output.append(f"announce-round-seconds={queue.announce_round_seconds}")
        output.append(
            "announce-position-only-up=yes"
            if queue.announce_position_only_up
            else "announce-position-only-up=no"
        )
        output.append(
            f"queue-youarenext={queue.queue_announcement.queue_youarenext}"
            if queue.queue_announcement.queue_youarenext
            else ";queue-youarenext="
        )
        output.append(
            f"queue-thereare={queue.queue_announcement.queue_thereare}"
            if queue.queue_announcement.queue_thereare
            else ";queue-thereare="
        )
        output.append(
            f"queue-callswaiting={queue.queue_announcement.queue_callswaiting}"
            if queue.queue_announcement.queue_callswaiting
            else ";queue-callswaiting="
        )
        output.append(
            f"queue-quantity1={queue.queue_announcement.queue_quantity1}"
            if queue.queue_announcement.queue_quantity1
            else ";queue-quantity1="
        )
        output.append(
            f"queue-quantity2={queue.queue_announcement.queue_quantity2}"
            if queue.queue_announcement.queue_quantity2
            else ";queue-quantity2="
        )
        output.append(
            f"queue-holdtime={queue.queue_announcement.queue_holdtime}"
            if queue.queue_announcement.queue_holdtime
            else ";queue-holdtime="
        )
        output.append(
            f"queue-minute={queue.queue_announcement.queue_minute}"
            if queue.queue_announcement.queue_minute
            else ";queue-minute="
        )
        output.append(
            f"queue-minutes={queue.queue_announcement.queue_minutes}"
            if queue.queue_announcement.queue_minutes
            else ";queue-minutes="
        )
        output.append(
            f"queue-seconds={queue.queue_announcement.queue_seconds}"
            if queue.queue_announcement.queue_seconds
            else ";queue-seconds="
        )
        output.append(
            f"queue-thankyou={queue.queue_announcement.queue_thankyou}"
            if queue.queue_announcement.queue_thankyou
            else ";queue-thankyou="
        )
        output.append(
            f"queue-reporthold={queue.queue_announcement.queue_reporthold}"
            if queue.queue_announcement.queue_reporthold
            else ";queue-reporthold="
        )
        output.append(
            f"periodic-announce={queue.periodic_announce}"
            if queue.periodic_announce
            else ";periodic-announce="
        )
        output.append(
            f"monitor-format={queue.monitor_format}"
            if queue.monitor_format
            else ";monitor-format="
        )
        output.append(f"joinempty={queue.joinempty}")
        output.append(f"leavewhenempty={queue.leavewhenempty}")
        output.append(f"ringinuse={queue.ringinuse}")
        output.append(f"timeoutrestart={queue.timeoutrestart}")
        output.append(
            f"defaultrule={queue.defaultrule}" if queue.defaultrule else ";defaultrule="
        )
        members = QueueMember.objects.filter(queue=queue)
        for member in members:
            output.append(
                f"member => {member.interface},{member.penalty},{member.member_name},{member.__state_interface__()},{member.__ringinuse__()},{member.wrapuptime}"
            )

    return "\n".join(output)


def make_queues_conf():
    plaintext = "; === This is auto generated file. Do not edit it! ===\n"
    plaintext += "; === Use PearlPBX admin panel! ===\n"
    plaintext += "; ==== General section ====\n"
    plaintext += "[general]\n"

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
    else:
        plaintext += "persistent_members = yes\n"
        plaintext += "autofill = yes\n"
        plaintext += "monitor-type = MixMonitor\n"
        plaintext += "shared_lastcall = no\n"
        plaintext += "negative_penalty_invalid = yes\n"
        plaintext += "log_membername_as_agent = yes\n"

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


def make_dialplan_contexts():
    plaintext = "// ==== Printing data of dialplan contexts in PBX admin panel ====\n"
    plaintext += "// ==== Dialplan contexts ====\n"
    for context in DialplanContext.objects.all():
        plaintext += f"// {context.description}\n"
        plaintext += f"context {context.name}" + " {\n"
        for extension in DialplanExtension.objects.filter(context=context):
            plaintext += make_dialplan_extension(extension)
        plaintext += "    h => {\n"
        plaintext += "        NoOp(Hangup);\n"
        plaintext += "        NoOp(HANGUPCAUSE_STRING=${HANGUPCAUSE_KEYS()});\n"
        plaintext += "        NoOp(DIALSTATUS=${DIALSTATUS});\n"
        plaintext += "        Hangup();\n"
        plaintext += "    }\n"
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
        for dir in RoutingRecord.objects.filter(routing_table=rt).order_by("prefix"):
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
    plaintext = "; === This is auto generated file. Do not edit it! ===\n"
    plaintext += "; === Use PearlPBX admin panel! ===\n"

    manager_host = settings.ASTERISK_MANAGER_HOST
    manager_port = settings.ASTERISK_MANAGER_PORT
    manager_username = settings.ASTERISK_MANAGER_USERNAME
    manager_secret = settings.ASTERISK_MANAGER_SECRET

    plaintext += "[general]\n"
    plaintext += "enabled = yes\n"
    plaintext += "webenabled = yes\n"
    plaintext += f"port = {manager_port}\n"
    plaintext += f"bindaddr = {manager_host}\n"
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
    plaintext += "writetimeout = 100\n"
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
