# PearlPBX2 — Code Review Issues

Full-project code review (Django app, `core/`, `apps/*`, `services/*`, settings, config generator).
Date: 2026-07-03. Issues are grouped by severity. File references point to the current
`feature/agi_slack` branch.

> **C1–C7 (all CRITICAL) are fixed** on branch `feature/agi_slack` (see git history).
> This document now tracks the remaining HIGH / MEDIUM / LOW issues.

---

## HIGH

### H1. WebRTC user custom settings are silently dropped from pjsip.conf
`core/conf.py:385-403` (`__make_pjsip_conf_webrtc_user`) — the `result +=` lines are
*inside* the `if ... not endswith("\n")` blocks:

```python
custom_settings = user.custom_settings
if custom_settings and not custom_settings.endswith("\n"):
    custom_settings += "\n"
    result += custom_settings   # only reached when the text did NOT end with \n
```

Any custom endpoint/auth/AOR settings that already end with a newline (the common case
for a textarea) are omitted from the generated config. Same pattern three times.

### H2. Any logged-in user can hang up calls and pause queue members
`apps/dashboard/views.py:289` (`hangup_channel`) and `:335` (`pause_queue_member`)
are protected only by `@login_required`. A user in the "Report Viewer" group (menu
implies read-only) can terminate any active call or pause any agent via a direct POST.

**Fix:** add a permission check (e.g. custom `dashboard.control_calls` permission or
group check) consistent with `ReportViewPermissionMixin`.

### H3. "Apply Changes" defaults to `core restart now`
`pbx/admin.py:88-91` — unless the form explicitly posts `reload_type=soft`, the view
executes `core restart now` via AMI, killing every active call. A config change on a
busy PBX should never hard-restart by default.

**Fix:** default to `soft_reload()`; make full restart an explicit, clearly-labelled
option. Also `AsteriskManagementInterface` is never `logoff()`-ed here (connection
leak, one per apply).

### H4. `PasswordWithToggleInput` renders unescaped values into `mark_safe` HTML
`core/widgets.py:46-52` — `value` (a stored SIP password) is `.format()`-ed into the
HTML template without `escape()`. A password containing `"` or `<` breaks the markup
and enables stored XSS in the admin. Additionally `render_value=True` means secrets
are always echoed into the page source, and the JS "generate" button uses
`Math.random()` (not cryptographically secure).

**Fix:** escape attributes (or build the widget on top of Django template rendering),
set `render_value=False`, use `crypto.getRandomValues()` in JS.

### H5. Config-injection via free-text model fields into generated Asterisk configs
`core/conf.py` interpolates many DB fields directly into `pjsip.conf` /
`extensions.ael` / `queues.conf`: descriptions become comments
(`"; " + transport.description`), `custom_settings`, `queue.context`,
`member.interface`, `announce` file names, `ManagerUsers.read/write/deny/permit`, etc.
None are checked for newlines or `[section]` markers, so a staff user can inject
arbitrary config lines (e.g. a new `[section]` with `type=...` or an AEL statement)
through fields that look harmless. Model-level validators exist only for a few name
fields; `DialplanExtension.dialplan` is validated only in the *form* (`clean_dialplan`),
not at model level, so imports/management commands bypass validation entirely.

**Fix:** strip/deny `\n`, `[`, `]` in single-line fields; attach
`AsteriskDialplanValidator` to the model field; validate `Queue.*` free-text fields.

### H6. `ApplyChangesView.apply_to_fs` writes user-controlled paths
`pbx/admin.py:160` — `path = settings.ASTERISK_ROOT_DIR + cfg.path` where
`ConfigurationFile.path` is arbitrary text from the admin form. `..` sequences or an
empty `ASTERISK_ROOT_DIR` (production sets it to `""`?) let a superuser-authored DB row
write anywhere the `asterisk` user can. Combined with C2/H4-style issues this is a
privilege-escalation path from "Django superuser" to "asterisk system user".
Also `backup_dir()` (`pbx/admin.py:174`) calls `tar.add()` on a directory that does not
exist on first run → apply fails with a traceback-derived message.

**Fix:** `os.path.normpath` + verify the resolved path stays under
`ASTERISK_ROOT_DIR`; create the config dir before backup or skip backup when missing.
Note `_build_cfgfiles()` also hardcodes `/etc/asterisk/...` and ignores
`ASTERISK_CONFIG_DIR` — the setting is advertised in CLAUDE.md/env but not honoured.

### H7. CLI arguments are silently ignored in both standalone services
`services/callback/callback.py:426-433` and
`services/dashboard/dashboard_listener.py:1009-1016` — `merge_args_env()` keeps the
env value whenever it is not `None`, but `read_env_vars()` always returns defaults, so
env values are *never* `None` and CLI args (`--ami_user=...` etc., documented in
CLAUDE.md and README) never take effect. Operators believe they changed credentials
when they didn't.

**Fix:** invert the precedence: `getattr(args, key) if getattr(args, key) is not None
else env_vars[key]`.

### H8. Plaintext secrets: uniqueness constraints leak other users' passwords
`core/models.py:281-288` (`SIPUser.secret`, `unique=True`) and `:682-690`
(`ManagerUsers.secret`, `unique=True`) — uniqueness on a password field means: when an
admin enters a password that collides with another account, the form error reveals that
this exact password is in use elsewhere (password oracle). SIP secrets must be stored
retrievably, but they must not be unique.

**Fix:** drop `unique=True` from both secret fields (migration required).

### H9. DEBUG mode and weak defaults outside "Production"
`pbx/settings.py:24-28` — `DEVMODE="Development"` (the default, "Ubuntu on VPS" per
comment) runs with `DEBUG=True` and a committed `SECRET_KEY` on an internet-facing VPS.
`Staging` disables secure cookies (`:160-162`). DB defaults are `rad/rad/rad`
(`:93-95`). `LOGGING` keeps `DEBUG` level console handlers in production (`:166-197`),
flooding journald with AMI event payloads (caller IDs — PII).

**Fix:** `DEBUG=True` only for `without_asterisk_on_localhost`; require explicit
secrets for anything network-reachable; INFO-level logging by default.

---

## MEDIUM

### M1. CDR CSV export: header/row column mismatch
`apps/reports/views.py:679-703` — header has 7 columns ending with "Channel", but each
row writes 8 values (`cdr.channel`, `cdr.dstchannel`). Every exported CSV is
misaligned for consumers that trust the header.

### M2. `AnalyticsMissedCallsView` and agent report have N+1 query storms
`apps/reports/views.py:966-1010` — per abandoned call, up to 3 additional queries
(`QueueLog` exists + 2 × `CDR` exists), per queue. A busy day (hundreds of abandons)
issues thousands of queries per page view. `get_agent_performance_data`
(`:248-271`) runs one aggregate query per agent. Both are aggregatable in SQL
(the `lost_and_found` service already shows the batched pattern).

### M3. `ConfigurationFileAdmin.save_model` silently discards edits
`core/admin.py:255-267` — when a `ConfigurationFile` exists and the *content* is
unchanged, the method returns without saving, so edits to `name`, `description`,
`path` are silently lost. When content changed, `obj.created = timezone.now()` is
ineffective (`auto_now_add` overrides it). No feedback to the user in either case.

### M4. `HomepageStatusView` leaks AMI connections and blocks the worker
`core/views/base_views.py:155-169` — a new `AMIClient` (with its listener thread) is
created per polling request; `logoff()` happens only if the callback chain reaches
`on_version`. On timeout (`done.wait(3)`) the client/thread/socket leak. Under a
30-second dashboard poll this steadily accumulates. Also blocks a WSGI worker for up
to 3 s per request.

**Fix:** `finally: client.logoff()`; consider caching the status in Redis (the
dashboard listener already has all of this data).

### M5. FastAGI service blocks the Twisted reactor
`services/fastagi/fastagi.py` — all DB access is synchronous SQLAlchemy, called from
reactor callbacks; `_query_ami_queue_status` (`:314-316`) busy-waits with
`time.sleep(0.1)` up to 3 s; `agi_entry_function` (`:705`) runs `db.test_connection()`
(a blocking round-trip) for *every* incoming call. One slow query stalls every
concurrent call's AGI processing. Also the global `db` is created only under
`if __name__ == "__main__"` (`:726`), so the module can't be imported/tested.

**Fix:** `twisted.internet.threads.deferToThread` for DB/AMI work (or adbapi), remove
the per-call connection test.

### M6. Monitor filename built from caller-controlled data
`services/fastagi/fastagi.py:147` — `filename = f"{date_path}/{time_str}_{src}_{dst}"`
where `src` is the caller ID from the network. A crafted caller ID containing `/`,
`..` or `,` flows into `os.makedirs` (`mkdir_p`) and into the `MixMonitor` argument
list (`:471`), allowing path traversal / extra MixMonitor options.

**Fix:** whitelist `[0-9A-Za-z+_-]` (reuse the dashboard's `_VALID_NAME_RE` idea)
before embedding in paths/AGI args.

### M7. API error handling leaks internals and 500s on bad dates
`apps/api/views/lists.py` — every view has `except Exception as e: return
JsonResponse({"error": str(e)}, status=500)`, exposing driver/ORM messages to
unauthenticated callers (see C1). `expiration_date` is taken raw from JSON and passed
to a `DateTimeField` — an invalid string throws deep in the ORM. Validate input
(a small `forms.Form` per endpoint would do) and log instead of echoing exceptions.

### M8. MOH directory served without authentication; storage paths hardcoded
`pbx/urls.py:29-31` — `/moh/<path>` uses `django.views.static.serve` with no auth in
all modes (fine for hold music, but the same tree is writable by admins — check this is
intended to be public). `core/storages.py` and `MusicOnHold._get_moh_base_path`
hardcode `/var/lib/asterisk/moh|sounds` instead of settings, duplicating the DEVMODE
switch in three places.

### M9. Queue admin exposes options the generator never writes
`core/models.py` defines `maxlen`, `weight`, `setqueuevar`,
`random_periodic_announce`; `CallQueueGlobalSettings.force_longest_waiting_caller` —
none are emitted by `core/conf.py:_make_single_queue_config()` /
`make_queues_conf()`. Admins set values that silently do nothing.

### M10. `MusicOnHold.mode`/`sort` have invalid defaults
`core/models.py:854-877` — `default=1` (int) with string `TextChoices`
(`"files"`, `"random"`). A programmatically created object gets mode `1`, matching
no branch in `make_musiconhold_conf()` → empty class definition.

### M11. Provisioning: Cisco configs fail to save; TFTP dir handling inconsistent
`apps/provision/provisioning_manager.py:82` builds `filename = f"{model}/....xml"` but
only the *base* directory is created (`:31`) — `open()` fails with
`FileNotFoundError` for every Cisco phone. Default `config_directory` hardcodes
`/var/lib/tftpboot/` instead of `settings.TFTP_DIR` (admin passes it, any other caller
doesn't). Also `apps/provision/views.py:apply_all_configurations` is a stub that
"simulates" provisioning and reports success without writing anything — dead и
misleading; the real action lives in `PhoneDeviceAdmin`.

### M12. `SIPUser.save()` side effects are one-way
`core/models.py:409-449` — creating/renaming a user auto-manages a
`DialplanExtension`, but deleting a `SIPUser` leaves the extension behind (no
`delete()` override / signal), and two users pointing at the same previous extension
value can hijack each other's row via
`DialplanExtension.objects.get(context=..., ext=previous_extension)`. Also
`DialplanContext.save`/`RoutingTable.save` raise `ValidationError` inside `save()` —
outside a form this becomes a 500 rather than a form error (the check already exists
in the admin forms; the model check should live in `clean()`).

### M13. Dashboard listener robustness gaps
`services/dashboard/dashboard_listener.py`:
- `ami_connect()` (`:118-130`) ignores the login response — wrong credentials are
  discovered only when events never arrive;
- `handle_signal` (`:1019-1022`) calls `sys.exit()` from a signal handler; the
  `process()` loop catches only `Exception`, so shutdown via `finally` runs during
  cancellation and may itself be cancelled — Slack flush on shutdown is best-effort at
  most;
- main loop burns CPU with `await asyncio.sleep(0.1)` (`:940-941`) — use an
  `asyncio.Event`;
- `handle_varset` watches `"CDR(billsec)"` (`:551`), which AMI never emits as a
  `VarSet` variable name.

### M14. `callback.py` documentation vs. behaviour
`services/callback/CLAUDE.md` claims "AMI reconnection: automatic on disconnect via
`on_disconnect()`", but `callback.py` never registers an `on_disconnect` callback —
the health-check thread `os._exit(1)`s instead (relies on systemd `Restart=`). Either
implement the callback or fix the docs/unit expectations. Also
`update_call_status`/`update_uniqueid` interpolate `self.dbtable` into SQL via
f-string — config-sourced, but still avoid (`psycopg2.sql.Identifier`).

### M15. `get_all_queues` uses blocking `KEYS`
`apps/dashboard/views.py:78` — `r.keys("asterisk:queue:*")` blocks Redis; the code
elsewhere already uses `scan_iter`. Low impact at small scale, easy fix.

### M16. Duplicated 60-line HTTP-range implementation
`apps/reports/views.py` — `AudioFileView` and `AudioFileByUniqueidView` duplicate the
whole Range/206 logic; the ranged branch also reads the entire slice into memory.
Extract one helper (or use `django-ranged-response` style `FileResponse` handling).

---

## LOW

### L1. Ukrainian text in code contradicts the project's English-only rule
`core/models.py:904, 1718` (docstrings of `moh_file_upload_path`,
`sound_file_upload_path`), `core/models.py:1811,1816` (Monitor Meta comments),
`core/admin.py:197,199,271` (inline comments). The repo is being prepared for
open-source — these should be English.

### L2. Leftover / conflicting modules
- `core/views.py` (a 1-line stub) coexists with the `core/views/` package — Python
  resolves the package, but the stray file confuses tools; delete it.
- `core/urls.py:6-7` registers two different paths under the same route name
  `"login"` — `reverse("login")` resolves to only one of them.
- `_asterisk_pattern_specificity` (`core/conf.py:707`) — the `is_xbang` term is dead
  code (the `_X!` case returns earlier).

### L3. `validate_bind_ip` quirks
`core/validators.py:24-40` — stray `logger.info(value)` on every validation; rejects
ports < 1024 (blocks e.g. TLS on 443/5061 < 1024? 5061 is fine, but 443 for WSS is
not); IPv4-only although PJSIP transports support IPv6 binds.

### L4. `SIPTransport.METHOD_CHOICES` offers SSLv2/SSLv3
`core/models.py:70-78` — long-broken protocols shouldn't be selectable; modern
Asterisk/PJSIP rejects them anyway.

### L5. `generate_safe_password(len)` shadows builtin and misleads
`core/utils.py:49-58` — parameter named `len`, return annotation `string` (the
module), and `token_urlsafe(n)` returns ~4/3·n chars, so
`generate_32_char_password()` yields ~43 characters (see C7 for the concrete
breakage).

### L6. `Whitelist` lacks audit fields; `Blacklist` has them
`core/models.py:1612,1654` — inconsistent inheritance from `AuditFields` for two
otherwise-symmetric models.

### L7. Reports CSV exports iterate unbounded querysets
`QueueLogReportView.export_csv` / `export_cdr_csv` write the entire filtered set into
an in-memory `HttpResponse`. Use `StreamingHttpResponse` with a generator for large
date ranges.

### L8. Liveness of dashboard state is weaker than the sweep assumes
`REDIS_STATE_TTL = 7200` (`dashboard_listener.py:54`) is the same key the FastAGI
ULINE sweep uses as a "dashboard is running" signal (`fastagi.py:663`). If the
listener dies, the sweep keeps trusting up to 2-hour-stale channel data. Use a short
dedicated heartbeat key (e.g. 90 s TTL refreshed by the health check).

### L9. `manager.conf` enables the HTTP AMI interface unconditionally
`core/conf.py:785` — `webenabled = yes` for all deployments; unless the HTTP manager
is actually used, generate `webenabled = no`.

### L10. Misc
- `core/ami.py:16` — `timeout=3600` for a client used for a single reload; generic
  `raise Exception(...)` instead of a custom error.
- `apps/reports/mixins.py` maps permissions to the `auth.` app label — works (they are
  created in core migrations) but housing custom permissions on a core model Meta
  would be more idiomatic and migration-safe.
- `requirements.txt` pins `uvicorn==0.40.0` and then adds unpinned
  `uvicorn[standard]` — duplicate/conflicting lines.
- `pbx/settings.py:242` `DASHBOARD_MISSED_CALL_WINDOW_MINUTES` docstring says
  "0 = current day" — implemented in `get_missed_calls`, fine, but the naive/aware
  mix (`local_now.replace(...)`) yields an aware datetime compared against naive
  `QueueLog.time` if the DB rows ever arrive naive; QueueLog.time is nullable and
  written by Asterisk directly — verify TZ consistency of that pipeline.

---

## Summary table

> C1–C7 (Critical) are fixed — see git history on `feature/agi_slack`.

| # | Severity | Area | One-liner |
|---|----------|------|-----------|
| H1 | High | Conf | WebRTC custom settings dropped when ending with newline |
| H2 | High | Dashboard | any logged-in user can hang up calls / pause agents |
| H3 | High | Admin | Apply Changes defaults to `core restart now` |
| H4 | High | Widgets | password widget XSS / secrets in HTML source |
| H5 | High | Conf | config injection via free-text fields; dialplan validated only in form |
| H6 | High | Admin | `apply_to_fs` path traversal; first-run backup crash; ignores `ASTERISK_CONFIG_DIR` |
| H7 | High | Services | CLI args never override env (both daemons) |
| H8 | High | Models | `unique=True` on password fields = password oracle |
| H9 | High | Settings | DEBUG on VPS, staging without secure cookies, default DB creds |
| M1–M16 | Medium | — | see above |
| L1–L10 | Low | — | see above |
