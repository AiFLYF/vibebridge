"""Experiment engine.

Every possible growth step is a small optional experiment, never a task and
never an assignment. Proposing one requires clearance from the safety gate.
Declining one is free: it is recorded as a choice, never as a failure.

The engine also learns which kinds of experiment actually suit this person,
which is the real long term output.
"""
import schema
import store
import safety
import growth as growth_mod

TERMINAL = ("successful", "partial", "unsuccessful", "not_suitable", "cancelled")


def _all():
    return store.load("experiments")


def propose(objective, context="", domain="expression", difficulty=2,
            suggested_action="", session_id=None, project_id=None,
            now_ts=None, force=False):
    """Create an experiment offer. Refuses to run when the safety gate says no."""
    gate = safety.can_offer(session_id=session_id, now_ts=now_ts)
    if not gate["allowed"] and not force:
        return {"created": False, "blocked_by_safety": True, "gate": gate}
    if domain not in schema.DOMAINS:
        raise ValueError("未知维度: " + str(domain))

    safety.assert_clean(objective, "experiment.objective")
    safety.assert_clean(suggested_action, "experiment.suggested_action")

    data = _all()
    eid = "experiment_" + str(len(data["items"]) + 1).zfill(3)
    rec = {
        "id": eid,
        "created_at": now_ts or schema.now(),
        "objective": objective,
        "context": context,
        "domain": domain,
        "difficulty": int(difficulty),
        "suggested_action": suggested_action,
        "session_id": session_id,
        "project_id": project_id,
        "offered": True,
        "accepted": None,
        "outcome": "",
        "stress_estimate": 0.0,
        "engagement": 0.0,
        "recovery_time": None,
        "repeat_interest": None,
        "result": "pending",
        "notes": "",
        "closed_at": None,
    }
    data["items"].append(rec)
    store.save("experiments", data)
    growth_mod.record_offer(session_id=session_id, now_ts=now_ts, experiment_id=eid)
    if session_id:
        try:
            import session as session_mod
            session_mod.update(session_id, experiments=[eid])
        except (ImportError, OSError):
            pass
    store.log_event("EXPERIMENT_PROPOSE", eid + " domain=" + domain)
    return {"created": True, "experiment": rec, "gate": gate}


def get(eid):
    for r in _all()["items"]:
        if r["id"] == eid:
            return r
    return None


def _mutate(eid, fn):
    data = _all()
    for r in data["items"]:
        if r["id"] == eid:
            fn(r)
            store.save("experiments", data)
            return r
    return None


def accept(eid, now_ts=None):
    return _mutate(eid, lambda r: r.update({"accepted": True}))


def decline(eid, reason="", session_id=None, now_ts=None):
    """Record a refusal. No score changes. The system only becomes quieter."""
    rec = _mutate(eid, lambda r: r.update({
        "accepted": False, "result": "cancelled",
        "notes": reason, "closed_at": now_ts or schema.now(),
        "outcome": "用户选择不参与，这是一个正当选择。",
    }))
    g = growth_mod.decline(reason=reason, session_id=session_id, now_ts=now_ts)
    return {"experiment": rec, "growth": g, "penalty_applied": False}


def complete(eid, result, outcome="", stress=0.0, engagement=0.0,
             recovery_time=None, repeat_interest=None, notes="", now_ts=None):
    """Close an experiment and fold the outcome into the matching growth domain."""
    if result not in schema.EXPERIMENT_RESULTS:
        raise ValueError("未知结果: " + str(result) + "，可用: " +
                         ", ".join(schema.EXPERIMENT_RESULTS))
    rec = get(eid)
    if not rec:
        return None
    safety.assert_clean(outcome, "experiment.outcome")
    safety.assert_clean(notes, "experiment.notes")

    def apply(r):
        r.update({
            "result": result, "outcome": outcome,
            "stress_estimate": float(stress), "engagement": float(engagement),
            "recovery_time": recovery_time, "repeat_interest": repeat_interest,
            "notes": notes, "closed_at": now_ts or schema.now(),
        })
        if r.get("accepted") is None:
            r["accepted"] = result not in ("cancelled",)

    rec = _mutate(eid, apply)
    g = growth_mod.record_outcome(rec["domain"], result, stress=stress,
                                  now_ts=now_ts, note=outcome)
    store.log_event("EXPERIMENT_COMPLETE", eid + " " + result + " -> " + g["change"])
    return {"experiment": rec, "growth": g}


def listing(limit=None, result=None, domain=None):
    items = _all()["items"]
    if result:
        items = [r for r in items if r["result"] == result]
    if domain:
        items = [r for r in items if r["domain"] == domain]
    items = sorted(items, key=lambda r: r["created_at"])
    return items[-limit:] if limit else items


def stats():
    items = _all()["items"]
    by_result = {}
    for r in items:
        by_result[r["result"]] = by_result.get(r["result"], 0) + 1
    closed = [r for r in items if r["result"] in TERMINAL]
    accepted = [r for r in items if r.get("accepted") is True]
    return {
        "total": len(items),
        "offered": sum(1 for r in items if r.get("offered")),
        "accepted": len(accepted),
        "declined": sum(1 for r in items if r.get("accepted") is False),
        "pending": sum(1 for r in items if r["result"] == "pending"),
        "by_result": by_result,
        "acceptance_rate": round(len(accepted) / len(items), 3) if items else 0.0,
        "success_rate": (round(by_result.get("successful", 0) / len(closed), 3)
                         if closed else 0.0),
    }


def what_works():
    """Which experiment shapes suit this person. Descriptive, not prescriptive."""
    items = [r for r in _all()["items"] if r["result"] in TERMINAL]
    if not items:
        return {"samples": 0, "by_domain": [], "by_difficulty": [], "notes": []}

    def bucket(items_, keyfn):
        agg = {}
        for r in items_:
            k = keyfn(r)
            a = agg.setdefault(k, {"n": 0, "good": 0, "stress": 0.0, "engagement": 0.0})
            a["n"] += 1
            if r["result"] in ("successful", "partial"):
                a["good"] += 1
            a["stress"] += float(r.get("stress_estimate") or 0.0)
            a["engagement"] += float(r.get("engagement") or 0.0)
        out = []
        for k, a in agg.items():
            out.append({
                "value": k, "samples": a["n"],
                "success_rate": round(a["good"] / a["n"], 3),
                "avg_stress": round(a["stress"] / a["n"], 3),
                "avg_engagement": round(a["engagement"] / a["n"], 3),
                "confidence": round(min(0.95, 0.25 + 0.15 * a["n"]), 3),
            })
        out.sort(key=lambda x: (-x["success_rate"], x["avg_stress"]))
        return out

    by_domain = bucket(items, lambda r: r["domain"])
    by_diff = bucket(items, lambda r: r.get("difficulty", 0))

    notes = []
    if by_domain:
        best = by_domain[0]
        notes.append("样本内成功率最高的维度是 " +
                     schema.DOMAIN_LABELS.get(best["value"], best["value"]) +
                     "（" + str(best["samples"]) + " 个样本）。")
    low_stress = [d for d in by_domain if d["avg_stress"] <= 0.3 and d["samples"] >= 2]
    if low_stress:
        notes.append("压力最低的方式集中在: " +
                     ", ".join(schema.DOMAIN_LABELS.get(d["value"], d["value"])
                               for d in low_stress) + "。")
    return {"samples": len(items), "by_domain": by_domain,
            "by_difficulty": by_diff, "notes": notes}

