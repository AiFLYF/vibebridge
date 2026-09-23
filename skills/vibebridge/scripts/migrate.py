"""Schema migration with mandatory pre-migration backup and rollback.

A skill upgrade must never damage months of accumulated memory. Every
migration is: snapshot -> transform -> record. If a step raises, the snapshot
is restored automatically and the original data survives untouched.
"""
import schema
import store

MIGRATIONS = []


def migration(from_v, to_v):
    def deco(fn):
        MIGRATIONS.append({"from": from_v, "to": to_v, "fn": fn, "name": fn.__name__})
        return fn
    return deco


def _vtuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0, 0, 0)


def current_version():
    ver = store.load("version")
    return ver.get("schema_version", "0.0.0")


def pending():
    cur = current_version()
    out, v = [], cur
    changed = True
    while changed:
        changed = False
        for m in MIGRATIONS:
            if m["from"] == v:
                out.append(m)
                v = m["to"]
                changed = True
                break
    return out


def status():
    cur = current_version()
    return {
        "data_schema_version": cur,
        "code_schema_version": schema.SCHEMA_VERSION,
        "up_to_date": _vtuple(cur) >= _vtuple(schema.SCHEMA_VERSION),
        "pending": [m["from"] + " -> " + m["to"] + " (" + m["name"] + ")" for m in pending()],
    }


def run(dry_run=False):
    todo = pending()
    if not todo:
        return {"applied": [], "message": "已是最新 schema，无需迁移。",
                "version": current_version()}
    if dry_run:
        return {"applied": [], "dry_run": True,
                "would_apply": [m["name"] for m in todo]}

    snap = store.snapshot("pre_migration")
    applied = []
    try:
        for m in todo:
            m["fn"]()
            ver = store.load("version")
            ver["schema_version"] = m["to"]
            ver["last_migration"] = schema.now()
            ver.setdefault("migrations", []).append({
                "name": m["name"], "from": m["from"], "to": m["to"],
                "at": schema.now(), "backup": snap.name,
            })
            store.save("version", ver)
            applied.append(m["name"])
            store.log_event("MIGRATE", m["name"] + " " + m["from"] + " -> " + m["to"])
    except Exception as e:
        store.log_event("MIGRATE_FAIL", str(e) + " ; rolling back to " + snap.name)
        store.restore(snap.name)
        return {"applied": applied, "error": str(e), "rolled_back_to": snap.name}
    return {"applied": applied, "version": current_version(), "backup": snap.name}


def rollback(snapshot_name=None):
    if snapshot_name is None:
        snaps = [s for s in store.list_backups() if "pre_migration" in s or "pre_restore" in s]
        if not snaps:
            return {"ok": False, "error": "没有可用的迁移前备份。"}
        snapshot_name = snaps[-1]
    ok = store.restore(snapshot_name)
    return {"ok": ok, "restored_from": snapshot_name}


# ---------------------------------------------------------------------------
# Example forward migration, kept as a working template for future versions.
# ---------------------------------------------------------------------------
@migration("0.9.0", "1.0.0")
def m_0_9_to_1_0():
    """Backfill fields introduced in 1.0.0 without discarding legacy records."""
    cands = store.load("candidates")
    for item in cands.get("items", {}).values():
        item.setdefault("contradict_w", 0.0)
        item.setdefault("contradict_count", 0)
        item.setdefault("contradict_evidence", [])
        item.setdefault("sessions", [])
        item.setdefault("history", [])
        item.setdefault("status", "candidate")
        item.setdefault("domains", [])
    store.save("candidates", cands)

    growth = store.load("growth")
    for dm in schema.DOMAINS:
        growth.setdefault("domains", {}).setdefault(dm, {
            "level": 0, "stability": 0.0, "attempts": 0, "successes": 0,
            "last_change": None, "last_change_reason": "migrated",
            "cooldown_until": None, "history": [],
        })
    growth.setdefault("decline_streak", 0)
    growth.setdefault("quiet_until", None)
    store.save("growth", growth)
