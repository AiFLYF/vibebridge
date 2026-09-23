"""Session records.

A session is written in the background at a natural boundary. It must never
interrupt work in progress. If the current task has not reached a natural end,
summarisation is deferred to the next suitable moment via the pending flag.
"""
from datetime import datetime, timezone

import paths
import schema
import store


def _index():
    return store.load("sessions")


def _save_index(idx):
    store.save("sessions", idx)


def _new_id(ts):
    stamp = ts.replace("-", "").replace(":", "").replace("Z", "")
    return "sess_" + stamp


def open_session(project=None, ts=None):
    ts = ts or schema.now()
    sid = _new_id(ts)
    rec = {
        "schema_version": schema.SCHEMA_VERSION,
        "session_id": sid,
        "timestamp": ts,
        "ended_at": None,
        "project": project,
        "summary": "",
        "observations": [],
        "candidate_memories": [],
        "experiments": [],
        "milestones": [],
        "user_feedback": [],
        "interaction_style": {},
        "stress_signals": [],
        "system_adaptation": [],
        "status": "open",
        "summary_pending": False,
    }
    store.write_json(paths.session_file(sid, ts), rec)
    idx = _index()
    idx["items"].append({"session_id": sid, "timestamp": ts, "project": project,
                         "status": "open", "summary": "", "observation_count": 0})
    _save_index(idx)
    store.log_event("SESSION_OPEN", sid)
    return rec


def load_session(sid):
    idx = _index()
    for it in idx["items"]:
        if it["session_id"] == sid:
            fp = paths.session_file(sid, it["timestamp"])
            return store.read_json(fp)
    return None


def _write(rec):
    store.write_json(paths.session_file(rec["session_id"], rec["timestamp"]), rec)


def attach_observations(sid, obs_ids):
    rec = load_session(sid)
    if not rec:
        return None
    for oid in obs_ids:
        if oid not in rec["observations"]:
            rec["observations"].append(oid)
    _write(rec)
    idx = _index()
    for it in idx["items"]:
        if it["session_id"] == sid:
            it["observation_count"] = len(rec["observations"])
    _save_index(idx)
    return rec


def update(sid, **fields):
    rec = load_session(sid)
    if not rec:
        return None
    listy = ("experiments", "milestones", "user_feedback",
             "stress_signals", "system_adaptation", "candidate_memories")
    for k, v in fields.items():
        if v is None:
            continue
        if k in listy:
            cur = rec.get(k, [])
            cur.extend(v if isinstance(v, list) else [v])
            rec[k] = cur
        elif k == "interaction_style" and isinstance(v, dict):
            rec["interaction_style"].update(v)
        else:
            rec[k] = v
    _write(rec)
    idx = _index()
    for it in idx["items"]:
        if it["session_id"] == sid:
            it["summary"] = rec.get("summary", "")[:160]
            it["status"] = rec.get("status", "open")
            it["project"] = rec.get("project")
    _save_index(idx)
    return rec


def close_session(sid, summary="", task_in_progress=False, ts=None):
    """Close a session. If work is still in flight, defer the summary instead
    of forcing an interruption."""
    rec = load_session(sid)
    if not rec:
        return None
    if task_in_progress:
        rec["summary_pending"] = True
        rec["status"] = "open"
        _write(rec)
        store.log_event("SESSION_DEFER", sid + " summary deferred, task in progress")
        return {"session_id": sid, "deferred": True,
                "note": "任务尚未自然结束，总结已延迟，不打断当前工作。"}
    rec["summary"] = summary or rec.get("summary", "")
    rec["summary_pending"] = False
    rec["status"] = "closed"
    rec["ended_at"] = ts or schema.now()
    _write(rec)
    idx = _index()
    for it in idx["items"]:
        if it["session_id"] == sid:
            it["status"] = "closed"
            it["summary"] = rec["summary"][:160]
    _save_index(idx)

    g = store.load("growth")
    if sid in g.get("offers_this_session", {}):
        g["offers_this_session"].pop(sid, None)
        store.save("growth", g)

    store.log_event("SESSION_CLOSE", sid)
    return {"session_id": sid, "deferred": False, "summary": rec["summary"]}


def current():
    idx = _index()
    open_ones = [it for it in idx["items"] if it.get("status") == "open"]
    return open_ones[-1] if open_ones else None


def ensure_open(project=None, ts=None):
    """Idempotent: reuse the open session if there is one, else start a new one."""
    cur = current()
    if cur:
        rec = load_session(cur["session_id"])
        if rec:
            return rec
    return open_session(project=project, ts=ts)


def listing(limit=20):
    idx = _index()
    items = sorted(idx["items"], key=lambda x: x["timestamp"])
    return items[-limit:] if limit else items


def pending_summaries():
    out = []
    for it in _index()["items"]:
        rec = load_session(it["session_id"])
        if rec and rec.get("summary_pending"):
            out.append(it["session_id"])
    return out

