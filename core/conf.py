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
)


logger = logging.getLogger(__name__)


def make_pjsip_conf_transports():
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
    result = "; Registration\n"
    result += f"[{trunk.name}]\n"
    result += "type=registration\n"
    result += f"outbound_auth={trunk.name}\n"
    result += (
        f"server_uri=sip:{trunk.host_port}\\;transport={trunk.transport.protocol}\n"
    )
    result += f"client_uri=sip:{trunk.username}@{trunk.host_port}\\;transport={trunk.transport.protocol}\n"
    result += "retry_interval=60\n"
    result += "\n"

    return result


def __section_trunk_auth_userpass(trunk: SIPPeer):
    result = "; Authentication\n"
    result += f"[{trunk.name}]\n"
    result += "type=auth\n"
    result += "auth_type=userpass\n"
    result += f"username={trunk.username}\n"
    result += f"password={trunk.secret}\n"
    result += "\n"

    return result


def __section_trunk_aor(trunk: SIPPeer):
    result = "; AOR\n"
    result += f"[{trunk.name}]\n"
    result += "type=aor\n"
    result += f"contact=sip:{trunk.host_port}\n"
    result += "\n"

    return result


def __section_trunk_endpoint(trunk: SIPPeer):
    result = "; Endpoint\n"
    result += f"[{trunk.name}]\n"
    result += "type=endpoint\n"
    result += f"transport={trunk.transport.name}\n"
    result += f"context=from-{trunk.name}\n"
    result += "disallow=all\n"
    result += "allow=ulaw,alaw\n"  # TODO list ALLOWED codecs
    if trunk.registrationThere:
        result += f"outbound_auth={trunk.name}\n"

    if trunk.registrationHere or not trunk.registrationThere:
        result += f"auth={trunk.name}\n"

    result += f"aors={trunk.name}\n"
    result += "\n"

    return result


def __section_trunk_identify(trunk: SIPPeer):
    result = "; Identify\n"
    result += f"[{trunk.name}]\n"
    result += "type=identify\n"
    result += f"endpoint={trunk.name}\n"
    result += f"match={trunk.host_port}\n"
    result += "\n"

    return result


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
    result += settings.user_template
    result += "\n\n"
    return result


def make_pjsip_conf_users_aor_template():
    result = "; ==== Users AOR template ====\n"
    result += "[user-aor-template](!)\n"
    settings = Settings.objects.first()
    result += settings.user_aor_template
    result += "\n\n"
    return result


def make_pjsip_conf_users_auth_template():
    result = "; ==== Users AUTH template ====\n"
    result += "[user-auth-template](!)\n"
    settings = Settings.objects.first()
    result += settings.user_auth_template
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
    result += user.custom_settings + "\n"
    result += "\n"

    result += f"[{user.username}](webrtc-template-auth)\n"
    result += f"md5_cred = {user.md5_cred}\nusername = {user.username}\n"
    result += f"realm = {user.realm}\n"
    result += user.custom_auth_settings + "\n\n"

    result += f"[{user.username}](webrtc-template-aor)\n"
    result += user.custom_aor_settings + "\n\n"
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
        result += f"auth = {user.username}\n"
        result += f"aors = {user.username}\n"
        result += f"callerid = {user.name} <{user.extension}>\n"
        result += user.custom_settings + "\n\n"

        result += f"[{user.username}](user-auth-template)\n"
        result += f"md5_cred = {user.md5_cred}\nusername = {user.username}\n"
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


def make_queues_conf_queues():
    plaintext = ""

    return plaintext


def make_queues_conf():
    plaintext = "; === This is auto generated file. Do not edit it! ===\n"
    plaintext += "; === Use PearlPBX admin panel! ===\n"
    plaintext += "; ==== General section ====\n"
    plaintext += "[general]\n"
    plaintext += "persistent_members = yes\n"
    plaintext += "autofill = no\n"
    plaintext += "monitor-type = MixMonitor\n"
    plaintext += "shared_lastcall = no\n"
    plaintext += "negative_penalty_invalid = no\n"
    plaintext += "log_membername_as_agent = no\n"

    plaintext += "; ==== Queues section ====\n"
    plaintext += make_queues_conf_queues()

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

    settings = Settings.objects.first()
    django_secret = settings.django_manager_secret

    plaintext += "[general]\n"
    plaintext += "enabled = yes\n"
    plaintext += "webenabled = yes\n"
    plaintext += "port = 5038\n"
    plaintext += "bindaddr = 0.0.0.0\n"
    plaintext += "displayconnects = yes\n"
    plaintext += "timestampevents = yes\n"
    plaintext += "authtimeout = 10\n"
    plaintext += "authlimit = 10\n"
    plaintext += "httptimeout = 60\n"
    plaintext += "[django]\n"
    plaintext += "displayconnects = yes\n"
    plaintext += f"secret = {django_secret}\n"
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
