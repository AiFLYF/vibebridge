"""Memory engine: Observation -> Candidate -> Verified -> Profile.

Confidence is a function of four independent factors:

    confidence = saturation(evidence_weight)
               * consistency(support vs contradict)
               * cross_session_factor(distinct sessions)
               * recency(time decay)

Repeated evidence inside a single session is deliberately damped so that one
talkative conversation cannot manufacture a verified long term belief.

Beliefs are never overwritten. Contradicting evidence produces a revision
record holding the previous belief, the new evidence, the confidence before
and after, and the reason.
"""
import math
from datetime import datetime, timezone

import paths
import schema
import store

SAME_SESSION_DAMPING = 0.25
SATURATION_RATE = 0.9
CONTRADICT_WEIGHT = 1.15


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _days_between(a, b):
    return max(0.0, (b - a).total_seconds() / 86400.0)


def compute_confidence(item, ref_time=None):
    """Pure function of accumulated weights. Returns confidence within 0.02..0.97."""
    cfg = store.load("config")["confidence"]
    ref = ref_time or datetime.now(timezone.utc)
    sup = item.get("support_w", 0.0)
    con = item.get("contradict_w", 0.0)
    if sup <= 0 and con <= 0:
        return 0.02

    saturation = 1.0 - math.exp(-SATURATION_RATE * sup)
    total = sup + con * CONTRADICT_WEIGHT
    consistency = (sup / total) if total > 0 else 0.0
    n_sessions = len(item.get("sessions", []))
    session_factor = min(1.0, 0.45 + 0.275 * n_sessions)
    half_life = cfg.get("half_life_days", schema.HALF_LIFE_DAYS)
    age_days = _days_between(_parse(item.get("last_seen")), ref)
    recency = 0.5 ** (age_days / half_life) if half_life > 0 else 1.0

    conf = saturation * consistency * session_factor * recency
    return round(max(0.02, min(0.97, conf)), 4)


def _blank(obs):
    return {
        "id": None,
        "key": obs["key"],
        "category": obs["category"],
        "statement": obs["statement"],
        "domains": list(obs.get("domains") or []),
        "support_w": 0.0, "contradict_w": 0.0,
        "evidence_count": 0, "contradict_count": 0,
        "sessions": [], "evidence": [], "contradict_evidence": [],
        "first_seen": obs["ts"], "last_seen": obs["ts"],
        "confidence": 0.0, "status": "candidate",
        "last_verified": None, "verified_at": None,
        "history": [],
    }


def _weight_for(item, obs):
    """Full weight the first time a key appears in a session, damped afterwards."""
    sid = obs.get("session_id") or "no_session"
    seen_here = sid in item.get("sessions", [])
    w = float(obs.get("strength", 0.5))
    return w * (SAME_SESSION_DAMPING if seen_here else 1.0), sid, seen_here


def apply_observation(cands, conflicts, obs, ref_time=None):
    """Fold one observation into the belief table. Returns (item, transition)."""
    cfg = store.load("config")["confidence"]
    key = obs["key"]
    items = cands["items"]
    item = items.get(key) or _blank(obs)
    before_conf = item.get("confidence", 0.0)
    before_status = item.get("status", "candidate")

    w, sid, seen_here = _weight_for(item, obs)
    if obs["polarity"] == "support":
        item["support_w"] = round(item["support_w"] + w, 4)
        item["evidence_count"] += 1
        item["evidence"].append(obs["id"])
    elif obs["polarity"] == "contradict":
        item["contradict_w"] = round(item["contradict_w"] + w, 4)
        item["contradict_count"] += 1
        item["contradict_evidence"].append(obs["id"])
    else:
        item["evidence"].append(obs["id"])

    if not seen_here:
        item["sessions"].append(sid)
    item["last_seen"] = obs["ts"]
    if _parse(obs["ts"]) < _parse(item["first_seen"]):
        item["first_seen"] = obs["ts"]
    for dm in obs.get("domains") or []:
        if dm not in item["domains"]:
            item["domains"].append(dm)
    if obs["polarity"] == "support" and len(obs["statement"]) > len(item["statement"]):
        item["statement"] = obs["statement"]

    item["confidence"] = compute_confidence(item, ref_time)

    promote_ok = (item["confidence"] >= cfg["promote_confidence"]
                  and item["evidence_count"] >= cfg["promote_evidence"]
                  and len(item["sessions"]) >= cfg["promote_sessions"])
    transition = None
    if item["status"] in ("candidate", "weakened") and promote_ok:
        item["status"] = "verified"
        item["verified_at"] = obs["ts"]
        item["last_verified"] = obs["ts"]
        transition = "promoted"
    elif item["status"] == "verified" and item["confidence"] < cfg["demote_confidence"]:
        item["status"] = "weakened"
        transition = "demoted"
    elif item["status"] == "verified":
        item["last_verified"] = obs["ts"]
    if item["confidence"] < schema.RETIRE_CONFIDENCE and item["contradict_count"] > 0:
        item["status"] = "retired"
        transition = "retired"

    item["history"].append({
        "ts": obs["ts"], "obs": obs["id"], "polarity": obs["polarity"],
        "confidence": item["confidence"], "status": item["status"],
    })
    if len(item["history"]) > 200:
        item["history"] = item["history"][-200:]

    if obs["polarity"] == "contradict" and before_conf > 0:
        conflicts["items"].append({
            "ts": obs["ts"],
            "key": key,
            "previous_belief": item["statement"],
            "previous_status": before_status,
            "new_evidence": obs["statement"],
            "confidence_before": before_conf,
            "confidence_after": item["confidence"],
            "reason": "出现方向相反的新证据。旧信念未被删除，只是重新计算置信度。",
            "observation_ids": list(item["contradict_evidence"])[-5:],
            "transition": transition,
        })
        if len(conflicts["items"]) > 500:
            conflicts["items"] = conflicts["items"][-500:]

    items[key] = item
    return item, transition


def refresh_decay(cands, ref_time=None):
    """Recompute every confidence against the clock so stale beliefs fade."""
    cfg = store.load("config")["confidence"]
    changed = []
    for key, item in cands["items"].items():
        old = item.get("confidence", 0.0)
        new = compute_confidence(item, ref_time)
        if abs(new - old) > 1e-9:
            item["confidence"] = new
            if item["status"] == "verified" and new < cfg["demote_confidence"]:
                item["status"] = "weakened"
                changed.append((key, "demoted_by_decay", old, new))
            else:
                changed.append((key, "decayed", old, new))
    return changed


def project_verified(cands):
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "generated_at": schema.now(),
        "items": {k: v for k, v in cands["items"].items() if v["status"] == "verified"},
    }


def ingest(obs_list, ref_time=None):
    """Public entry: fold a batch of stored observations into memory."""
    cands = store.load("candidates")
    conflicts = store.load("conflicts")
    results = []
    for obs in obs_list:
        item, tr = apply_observation(cands, conflicts, obs, ref_time)
        results.append({"key": item["key"], "confidence": item["confidence"],
                        "status": item["status"], "transition": tr})
    refresh_decay(cands, ref_time)
    store.save("candidates", cands)
    store.save("conflicts", conflicts)
    store.save("verified", project_verified(cands))
    return results


def rebuild(ref_time=None):
    """Replay the immutable observation log to regenerate all derived memory.

    This is the recovery path. Candidates, verified and conflicts may be
    discarded at any time and reconstructed exactly from observations.
    """
    obs = sorted(store.observations(), key=lambda o: (o.get("ts", ""), o.get("id", "")))
    cands = schema.DEFAULTS["candidates"]()
    conflicts = schema.DEFAULTS["conflicts"]()
    for o in obs:
        try:
            apply_observation(cands, conflicts, o, ref_time)
        except (KeyError, TypeError) as e:
            store.log_event("REBUILD_SKIP", str(o.get("id")) + " " + str(e))
    refresh_decay(cands, ref_time)
    store.save("candidates", cands)
    store.save("conflicts", conflicts)
    store.save("verified", project_verified(cands))
    n_ver = sum(1 for v in cands["items"].values() if v["status"] == "verified")
    return {"observations": len(obs), "beliefs": len(cands["items"]), "verified": n_ver}
