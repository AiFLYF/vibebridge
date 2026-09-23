"""Adaptive growth engine.

Growth is tracked per domain, never as a single aggregate score, so a state
like "collaboration level 7, voice communication level 2" is perfectly legal
and is not treated as an inconsistency.

Core rules enforced here in code, not merely suggested in a prompt:
  * Declining an offer changes no score, no level, no stability.
  * Two consecutive declines start a quiet period with zero further offers.
  * Difficulty may never rise as a consequence of a decline.
  * Levels may go down as well as up. Going down is a valid adaptation.
"""
from datetime import datetime, timedelta, timezone

import safety
import schema
import store

STABILITY_ON_SUCCESS = 0.35
STABILITY_ON_PARTIAL = 0.12
STABILITY_ON_UNSUCCESSFUL = -0.20
PROMOTE_STABILITY = 0.60
COOLDOWN_HOURS_AFTER_LEVEL_UP = 48


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dom(g, name):
    if name not in g["domains"]:
        g["domains"][name] = {
            "level": 0, "stability": 0.0, "attempts": 0, "successes": 0,
            "last_change": None, "last_change_reason": "init",
            "cooldown_until": None, "history": [],
        }
    return g["domains"][name]


def _ladder(domain, level):
    lad = schema.LADDERS.get(domain, [])
    if not lad:
        return ""
    return lad[max(0, min(level, len(lad) - 1))]


def _record(d, domain, level_from, level_to, reason, ts):
    d["history"].append({"ts": ts, "from": level_from, "to": level_to,
                         "reason": reason, "label": _ladder(domain, level_to)})
    if len(d["history"]) > 100:
        d["history"] = d["history"][-100:]


def trend(d):
    hist = d.get("history", [])[-4:]
    if len(hist) < 2:
        return "stable"
    delta = hist[-1]["to"] - hist[0]["from"]
    if delta > 0:
        return "rising"
    if delta < 0:
        return "easing"
    return "stable"


def state():
    g = store.load("growth")
    out = {"updated_at": g.get("updated_at"), "paused": g.get("paused", False),
           "decline_streak": g.get("decline_streak", 0),
           "quiet_until": g.get("quiet_until"), "domains": {}}
    for name in schema.DOMAINS:
        d = _dom(g, name)
        out["domains"][name] = {
            "label": schema.DOMAIN_LABELS.get(name, name),
            "level": d["level"],
            "level_label": _ladder(name, d["level"]),
            "stability": round(d["stability"], 3),
            "attempts": d["attempts"], "successes": d["successes"],
            "trend": trend(d),
            "cooldown_until": d.get("cooldown_until"),
            "last_change_reason": d.get("last_change_reason"),
            "history": d.get("history", [])[-10:],
        }
    return out


def record_offer(session_id=None, now_ts=None, experiment_id=None):
    """Mark that an opportunity was surfaced. Called only after safety allows."""
    g = store.load("growth")
    now = _parse(now_ts) or datetime.now(timezone.utc)
    g["last_offer_at"] = _iso(now)
    if session_id:
        g.setdefault("offers_this_session", {})
        g["offers_this_session"][session_id] = g["offers_this_session"].get(session_id, 0) + 1
    g["updated_at"] = _iso(now)
    store.save("growth", g)
    return {"ok": True, "last_offer_at": g["last_offer_at"], "experiment_id": experiment_id}


def decline(reason="", session_id=None, now_ts=None):
    """A refusal. Costs the user nothing and only makes the system quieter."""
    cfg = store.load("config")["growth"]
    g = store.load("growth")
    now = _parse(now_ts) or datetime.now(timezone.utc)
    g["decline_streak"] = g.get("decline_streak", 0) + 1
    quiet_started = False
    if g["decline_streak"] >= int(cfg.get("decline_streak_trigger", 2)):
        days = int(cfg.get("quiet_days_after_declines", 7))
        g["quiet_until"] = _iso(now + timedelta(days=days))
        quiet_started = True
    g["updated_at"] = _iso(now)
    store.save("growth", g)
    store.log_event("DECLINE", "streak=" + str(g["decline_streak"]) + " reason=" + str(reason))
    return {
        "ok": True,
        "decline_streak": g["decline_streak"],
        "quiet_until": g.get("quiet_until"),
        "quiet_period_started": quiet_started,
        "penalty_applied": False,
        "note": "拒绝不计为失败，未改变任何等级、稳定度或评分。",
    }


def record_outcome(domain, result, stress=0.0, now_ts=None, note=""):
    """Fold an experiment outcome into one domain."""
    if domain not in schema.DOMAINS:
        raise ValueError("未知维度: " + str(domain))
    if result not in schema.EXPERIMENT_RESULTS:
        raise ValueError("未知结果: " + str(result))

    g = store.load("growth")
    now = _parse(now_ts) or datetime.now(timezone.utc)
    d = _dom(g, domain)
    lvl_before = d["level"]
    change = "unchanged"

    if result in ("cancelled", "paused", "pending"):
        g["updated_at"] = _iso(now)
        store.save("growth", g)
        return {"domain": domain, "level_before": lvl_before, "level": d["level"],
                "change": "unchanged", "note": "取消、暂停或未完成都不影响任何状态。"}

    d["attempts"] += 1
    if result == "successful":
        d["successes"] += 1
        d["stability"] = min(1.0, d["stability"] + STABILITY_ON_SUCCESS)
        g["decline_streak"] = 0
        cd = _parse(d.get("cooldown_until"))
        if d["stability"] >= PROMOTE_STABILITY and (cd is None or now >= cd):
            top = len(schema.LADDERS.get(domain, [])) - 1
            if d["level"] < top:
                d["level"] += 1
                d["stability"] = 0.25
                d["cooldown_until"] = _iso(now + timedelta(hours=COOLDOWN_HOURS_AFTER_LEVEL_UP))
                change = "level_up"
    elif result == "partial":
        d["stability"] = min(1.0, d["stability"] + STABILITY_ON_PARTIAL)
        g["decline_streak"] = 0
    elif result == "unsuccessful":
        d["stability"] = max(-1.0, d["stability"] + STABILITY_ON_UNSUCCESSFUL)
        if stress >= 0.7 and d["level"] > 0:
            d["level"] -= 1
            d["stability"] = 0.0
            change = "level_down"
    elif result == "not_suitable":
        d["stability"] = max(-1.0, d["stability"] - 0.05)
        change = "route_change"

    if change != "unchanged":
        reason = {"level_up": "连续成功且稳定度达标",
                  "level_down": "压力信号偏高，主动降低难度以回到舒适区",
                  "route_change": "该方式不适合，换一条路线而不是加压"}[change]
        d["last_change"] = _iso(now)
        d["last_change_reason"] = reason
        _record(d, domain, lvl_before, d["level"], reason, _iso(now))

    d["stability"] = round(d["stability"], 3)
    g["updated_at"] = _iso(now)
    store.save("growth", g)
    return {"domain": domain, "level_before": lvl_before, "level": d["level"],
            "level_label": _ladder(domain, d["level"]), "stability": d["stability"],
            "change": change, "note": note}


def ease(domain=None, steps=1, reason="用户请求降低难度", now_ts=None):
    """Deliberate downgrade. A lower level is a valid, safe resting state."""
    g = store.load("growth")
    now = _parse(now_ts) or datetime.now(timezone.utc)
    targets = [domain] if domain else list(schema.DOMAINS)
    out = []
    for name in targets:
        d = _dom(g, name)
        before = d["level"]
        d["level"] = max(0, d["level"] - int(steps))
        d["stability"] = 0.0
        d["cooldown_until"] = _iso(now + timedelta(hours=24))
        d["last_change"] = _iso(now)
        d["last_change_reason"] = reason
        if before != d["level"]:
            _record(d, name, before, d["level"], reason, _iso(now))
        out.append({"domain": name, "from": before, "to": d["level"],
                    "label": _ladder(name, d["level"])})
    g["quiet_until"] = _iso(now + timedelta(days=2))
    g["updated_at"] = _iso(now)
    store.save("growth", g)
    return {"eased": out, "quiet_until": g["quiet_until"],
            "note": "降低难度不是退步，是让系统回到当前真正舒适的位置。"}


def pause(on=True):
    g = store.load("growth")
    g["paused"] = bool(on)
    g["updated_at"] = schema.now()
    store.save("growth", g)
    return {"paused": g["paused"]}


def opportunities(session_id=None, task_in_progress=False, now_ts=None, limit=3):
    """Find the next natural step per domain, ordered by lowest friction.

    Returns candidates plus the safety gate result. The gate is authoritative:
    when it says no, nothing may be surfaced to the user at all.
    """
    gate = safety.can_offer(session_id=session_id, now_ts=now_ts,
                            task_in_progress=task_in_progress)
    g = store.load("growth")
    now = _parse(now_ts) or datetime.now(timezone.utc)
    verified = store.load("verified").get("items", {})
    interests = [v["statement"] for v in verified.values()
                 if v.get("category") == "interest"][:3]

    cands = []
    for name in schema.DOMAINS:
        d = _dom(g, name)
        top = len(schema.LADDERS.get(name, [])) - 1
        if d["level"] >= top:
            continue
        cd = _parse(d.get("cooldown_until"))
        cooling = bool(cd and now < cd)
        friction = 0.0
        friction += 0.4 if cooling else 0.0
        friction += max(0.0, -d["stability"]) * 0.5
        friction += 0.15 if d["attempts"] == 0 else 0.0
        friction -= min(0.3, max(0.0, d["stability"]) * 0.3)
        cands.append({
            "domain": name,
            "label": schema.DOMAIN_LABELS.get(name, name),
            "current_level": d["level"],
            "current_label": _ladder(name, d["level"]),
            "next_level": d["level"] + 1,
            "next_label": _ladder(name, d["level"] + 1),
            "estimated_difficulty": round(min(1.0, 0.25 + 0.06 * d["level"] + friction), 3),
            "cooling_down": cooling,
            "friction": round(friction, 3),
        })
    cands.sort(key=lambda c: c["estimated_difficulty"])
    return {
        "gate": gate,
        "anchor_interests": interests,
        "candidates": cands[:limit],
        "principle": "成长目标只能从用户当前目标中自然派生，不得替换用户目标。",
    }

