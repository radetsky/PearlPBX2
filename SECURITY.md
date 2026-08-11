# Security Policy

## Supported Versions

Only the latest release and the `main` branch are supported with security fixes. There is no
long-term-support branch — please upgrade to the latest version before reporting an issue.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report privately via [GitHub Security Advisories](../../security/advisories/new) ("Report a
vulnerability" under the Security tab of this repository). This keeps the report and any
discussion private until a fix is available.

Include as much detail as possible:

- Affected component (Django app, `core/`, a specific service under `services/`, Ansible role, etc.)
- Steps to reproduce, or a proof of concept
- Impact (e.g. AMI credential exposure, unauthorized call origination, config injection, auth bypass)
- Version/commit affected

You should receive an initial response within 7 days. If the report is confirmed, a fix will be
prepared and a GitHub Security Advisory published once a patched release is available; you will
be credited unless you prefer to remain anonymous.

## Scope Notes

PearlPBX2 manages Asterisk configuration and AMI credentials and generates config files that are
applied directly to `/etc/asterisk`. Reports involving any of the following are especially
relevant:

- AMI credential handling or exposure
- Authentication/authorization bypass in the Django admin, dashboard, or REST API
- Injection into generated Asterisk configuration (pjsip.conf, AEL dialplan, etc.)
- FastAGI/AGI input handling in `services/`
- Callback service race conditions affecting call origination

Deployment-only issues (e.g. a hardened `env.sample` value not changed by an operator) are still
welcome as reports, but are lower priority than issues in the application itself.
