# PJSIP RealTime: Future Scalability Path

## Context

This document captures architectural analysis and recommendations for scaling PearlPBX2
to 3,000–5,000 SIP users. To be revisited when a real client with such requirements appears.

---

## Current Architecture Limitations

**Current flow:** Django models (staging) → `pjsip.conf` (file) → `module reload res_pjsip`

At 3–5K users:

- `pjsip.conf` grows to 50,000–150,000 lines (~15–20 lines per endpoint)
- Full file regeneration queries all users from DB every time
- `module reload res_pjsip` takes 30 seconds to 3 minutes for 5K endpoints
- After every reload, all phones simultaneously re-register — CPU/network spike
- Changing a single password triggers a full reload

Comfortable range for current architecture: up to ~500 users. Tolerable up to ~1,000. Painful beyond that.

---

## Asterisk Capacity at 3–5K Users

Asterisk with PJSIP can technically handle 3–5K registered endpoints, but requires:

- **RAM:** ~8–20 GB just for the SIP stack (each endpoint held in memory)
- **Concurrent calls:** a typical server handles 500–1,000 concurrent calls; more with no transcoding
- **CPU:** acceptable without transcoding; serious hardware needed with it
- **Registration storms:** major concern after any reload at this scale

---

## Recommended Architecture: PJSIP RealTime (ARA)

Asterisk can read endpoint configuration directly from PostgreSQL via `res_config_pgsql`.

**New flow:** Django models (staging) → Apply Changes → RT tables (`ps_endpoints`, etc.) → no reload

Tables used by Asterisk RealTime: `ps_endpoints`, `ps_auths`, `ps_aors`, `ps_contacts`.

Benefits:
- No `pjsip.conf` for endpoints — no file I/O
- No `module reload` — changes propagate without restart
- Password change = DB row update; Asterisk picks it up on next registration
- Apply is fast (DB writes only, no Asterisk interaction)

**Key concern:** changes apply instantly to live tables — no buffer, no staging by default.

---

## Rollback Mechanism

Instant-apply is dangerous. The solution is to preserve the existing "Apply Changes" workflow
and add explicit versioning.

### Recommended Approach (three layers)

**Layer 1 — django-reversion on Django models**

```python
import reversion

@reversion.register()
class SIPUser(AuditFields):
    ...
```

- Every `save()` automatically stores a version
- Per-object rollback to any previous state from Django admin
- 15-minute integration effort
- Rollback here requires a subsequent Apply to push changes to RT tables

**Layer 2 — RT table snapshot before every Apply**

Before copying staging → RT tables, snapshot current RT state:

```sql
INSERT INTO ps_endpoints_snapshots
SELECT *, NOW() AS snapshot_time FROM ps_endpoints;
```

One-click rollback restores the full previous RT state — equivalent to the current
`ASTERISK_BACKUP_DIR` file backup, but stored in the database.

**Layer 3 — Keep the "Apply Changes" button**

The button remains the control point. It no longer writes a file and triggers a reload —
instead it copies Django model state into RT tables (with a snapshot taken first).

---

## Migration Strategy

1. Keep Django models as the authoritative staging layer — no change to admin workflows
2. Add `django-reversion` to all SIP-related models
3. Create Asterisk RealTime tables alongside existing tables (parallel, not replacing)
4. Modify the "Apply Changes" action to write to RT tables instead of generating a file
5. Add snapshot logic to Apply Changes
6. Test with a non-production Asterisk instance before cutting over
7. Provide a "Rollback" button in the admin that restores from the last snapshot

---

## Summary

| Concern | Solution |
|---|---|
| Slow reload at scale | PJSIP RealTime — no reload needed |
| Instant-apply risk | Snapshot RT tables before every Apply |
| Per-object history | `django-reversion` |
| Familiar UX | Keep "Apply Changes" workflow, change what it does |
| Full config rollback | Restore from RT snapshot (one click) |

Revisit this document when onboarding a client with 1,000+ SIP users.
