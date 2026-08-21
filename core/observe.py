"""Observation engine.

An observation is a low inference, behavioural fact. It records what happened,
never what it supposedly means about the person.

Allowed:
    "本次会话中用户婉拒了继续交流"
Not allowed:
    "用户社交能力下降"

Observations are appended to an immutable JSONL log. That log is the single
source of truth; every other artifact in the system is rebuildable from it.
"""
import schema
import store
import paths
import memory


def _next_seq(n=1):
    """Allocate observation sequence numbers without rescanning the whole log."""
    ver = store.load("version")
    seq = ver.get("obs_seq")
    if seq is None:
        seq = len(store.observations())
    start = seq + 1
    ver["obs_seq"] = seq + n
    store.save("version", ver)
    return start


# Phrases that indicate the caller drifted from observation into interpretation.
INFERENCE_MARKERS = [
    "能力下降", "变得更差", "退步了", "说明他", "证明用户是",
    "性格", "人格", "病", "障碍程度", "不合作", "不配合",
]


def screen_statement(text):
    """Warn when a statement reads like a verdict rather than an observation."""
    hits = [m for m in INFERENCE_MARKERS if m in str(text)]
    return hits


def record(items, session_id=None, project_id=None, experiment_id=None,
           ts=None, ref_time=None):
    """Validate, persist and fold a batch of observations into memory.

    Returns a per item result including the resulting belief confidence, so the
    caller can see the full Observation to Memory chain in one call.
    """
    if isinstance(items, dict):
        items = [items]
    if not items:
        return {"recorded": 0, "results": [], "warnings": []}

    prepared, warnings = [], []
    start = _next_seq(len(items))
    for i, raw in enumerate(items):
        raw = dict(raw)
        raw.setdefault("session_id", session_id)
        raw.setdefault("project_id", project_id)
        raw.setdefault("experiment_id", experiment_id)
        if ts:
            raw.setdefault("ts", ts)
        obs = schema.validate_observation(raw)
        obs["id"] = "obs_" + str(start + i).zfill(6)
        flagged = screen_statement(obs["statement"])
        if flagged:
            warnings.append({"id": obs["id"], "statement": obs["statement"],
                             "issue": "疑似推断而非观察", "markers": flagged})
        prepared.append(obs)

    fp = paths.p("observations")
    for obs in prepared:
        store.append_jsonl(fp, obs)

    results = memory.ingest(prepared, ref_time=ref_time)

    if session_id:
        try:
            import session as session_mod
            session_mod.attach_observations(session_id, [o["id"] for o in prepared])
        except (ImportError, KeyError, OSError):
            pass

    store.log_event("OBSERVE", str(len(prepared)) + " observation(s) session=" + str(session_id))
    return {"recorded": len(prepared),
            "ids": [o["id"] for o in prepared],
            "results": results,
            "warnings": warnings}


def query(limit=50, category=None, key=None, session_id=None, since=None, until=None):
    recs = store.observations()
    out = []
    for r in recs:
        if category and r.get("category") != category:
            continue
        if key and r.get("key") != key:
            continue
        if session_id and r.get("session_id") != session_id:
            continue
        if since and str(r.get("ts", "")) < since:
            continue
        if until and str(r.get("ts", "")) > until:
            continue
        out.append(r)
    out.sort(key=lambda r: str(r.get("ts", "")))
    return out[-limit:] if limit else out


def by_ids(ids):
    want = set(ids or [])
    return [r for r in store.observations() if r.get("id") in want]


def evidence_for(key):
    """Full provenance chain for one belief: observations plus their sessions."""
    cands = store.load("candidates").get("items", {})
    item = cands.get(key)
    if not item:
        return None
    ids = list(item.get("evidence", [])) + list(item.get("contradict_evidence", []))
    obs = by_ids(ids)
    return {
        "key": key,
        "statement": item.get("statement"),
        "category": item.get("category"),
        "status": item.get("status"),
        "confidence": item.get("confidence"),
        "evidence_count": item.get("evidence_count"),
        "contradict_count": item.get("contradict_count"),
        "sessions": item.get("sessions", []),
        "first_seen": item.get("first_seen"),
        "last_seen": item.get("last_seen"),
        "observations": obs,
        "history": item.get("history", []),
    }

