"""Analytics engine.

Every metric here is a description of observable activity over time. None of
them is a clinical scale, a severity index, or a measure of a person. They
exist so that long term behavioural trends can be looked at, nothing else.

Each metric carries:
  * an explicit definition of what is counted
  * the raw sample count it was computed from
  * a confidence value that reflects how much data backs it
  * the observation ids it came from, so any number can be traced back
"""
import math
from datetime import datetime, timedelta, timezone

import experiment as experiment_mod
import growth as growth_mod
import project as project_mod
import schema
import store

WINDOWS = {"7D": 7, "30D": 30, "90D": 90, "6M": 182, "ALL": None}

# rate_k is the events-per-week rate that maps to roughly 63 on the 0..100 axis.
METRIC_SPECS = {
    "engagement": {
        "label": "参与度",
        "definition": "窗口内产生的全部行为观察与会话活动频率。",
        "all_observations": True, "rate_k": 10.0,
    },
    "self_expression": {
        "label": "自我表达",
        "definition": "涉及表达维度的观察频率，例如描述想法、解释选择、分享进展。",
        "domains": ["expression"], "rate_k": 4.0,
    },
    "initiative": {
        "label": "主动性",
        "definition": "用户主动发起的项目与首次出现的新行为频率。",
        "categories": ["growth_signal", "project_event"], "rate_k": 3.0,
    },
    "communication": {
        "label": "沟通",
        "definition": "涉及沟通维度的观察频率，例如提问、澄清、往复交流。",
        "domains": ["communication"], "rate_k": 4.0,
    },
    "social_interaction": {
        "label": "社会互动",
        "definition": "涉及与外部世界互动的观察频率，例如发布、回复、外部反馈。",
        "domains": ["social"], "rate_k": 2.0,
    },
    "collaboration": {
        "label": "协作",
        "definition": "涉及与他人共同推进事情的观察频率。",
        "domains": ["collaboration"], "rate_k": 1.5,
    },
    "self_advocacy": {
        "label": "自我倡导",
        "definition": "表达需求、边界、困难或请求调整方式的观察频率。",
        "domains": ["self_advocacy"], "categories": ["self_advocacy"], "rate_k": 1.5,
    },
    "independence": {
        "label": "独立性",
        "definition": "独立完成、独立决策、自主推进相关的观察频率。",
        "domains": ["independence"], "rate_k": 2.5,
    },
    "persistence": {
        "label": "坚持度",
        "definition": "在遇到困难后重新尝试、继续修改、继续推进的观察频率。",
        "categories": ["behavior_pattern"], "keys_contain": ["retry", "persist", "resume", "continue"],
        "rate_k": 1.5,
    },
}


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def window_bounds(window="30D", now=None):
    now = now or datetime.now(timezone.utc)
    days = WINDOWS.get(window, 30)
    if days is None:
        return None, now, None
    return now - timedelta(days=days), now, days


def _in_window(rec, start, end):
    t = _parse(rec.get("ts") or rec.get("created_at") or rec.get("timestamp"))
    if t is None:
        return False
    if start and t < start:
        return False
    return t <= end


def _matches(spec, obs):
    if spec.get("all_observations"):
        return True
    doms = set(obs.get("domains") or [])
    if spec.get("domains") and doms.intersection(spec["domains"]):
        return True
    if spec.get("categories") and obs.get("category") in spec["categories"]:
        kc = spec.get("keys_contain")
        if kc:
            return any(s in str(obs.get("key", "")) for s in kc)
        return True
    return False


def _score(count, days, rate_k):
    """Saturating map from events-per-week to a 0..100 axis. Never a percentile."""
    if days is None or days <= 0:
        days = 1
    weeks = max(days / 7.0, 1e-6)
    rate = count / weeks
    return round(100.0 * (1.0 - math.exp(-rate / max(rate_k, 1e-6))), 1)


def _confidence(count, distinct_days):
    """How much this number can be leaned on. Low sample, low confidence."""
    if count == 0:
        return 0.0
    base = 1.0 - math.exp(-count / 6.0)
    spread = min(1.0, 0.4 + 0.15 * distinct_days)
    return round(min(0.95, base * spread), 3)


def compute_metrics(observations, start, end, days):
    out = {}
    for name, spec in METRIC_SPECS.items():
        hits = [o for o in observations if _matches(spec, o)]
        distinct_days = len({str(o.get("ts", ""))[:10] for o in hits})
        out[name] = {
            "label": spec["label"],
            "definition": spec["definition"],
            "value": _score(len(hits), days, spec["rate_k"]),
            "sample_count": len(hits),
            "distinct_days": distinct_days,
            "confidence": _confidence(len(hits), distinct_days),
            "sources": [o["id"] for o in hits][-25:],
            "not_a_clinical_scale": True,
        }
    return out


def compute_behavior(observations, start, end):
    projects = project_mod.listing()
    inwin = [p for p in projects if _in_window(p, start, end)]
    events = [e for e in project_mod.timeline() if _in_window(e, start, end)]
    exps = [e for e in experiment_mod.listing() if _in_window(e, start, end)]

    def count_key(fragment):
        return sum(1 for o in observations if fragment in str(o.get("key", "")))

    return {
        "projects_started": {"value": len(inwin), "label": "项目发起"},
        "projects_completed": {
            "value": sum(1 for p in inwin if p["stage"] in
                         ("completed", "published", "feedback_received",
                          "communicating", "collaborating")),
            "label": "项目完成"},
        "completion_rate": {"value": project_mod.summary()["completion_rate"],
                            "label": "完成率"},
        "works_published": {"value": sum(1 for e in events if e["type"] == "published"),
                            "label": "作品发布"},
        "works_shared": {"value": sum(1 for p in inwin if p.get("shared")),
                         "label": "作品分享"},
        "feedback_received": {"value": sum(p.get("feedback_received", 0) for p in inwin),
                              "label": "收到反馈"},
        "external_conversations": {"value": sum(p.get("external_conversations", 0) for p in inwin),
                                   "label": "外部交流"},
        "collaborations": {"value": sum(p.get("collaborators", 0) for p in inwin),
                           "label": "协作"},
        "help_requests": {"value": count_key("help"), "label": "主动求助"},
        "self_initiated_expression": {
            "value": sum(1 for o in observations
                         if "expression" in (o.get("domains") or [])
                         and o.get("polarity") == "support"),
            "label": "主动表达"},
        "experiments_offered": {"value": len(exps), "label": "机会提出"},
        "experiments_accepted": {"value": sum(1 for e in exps if e.get("accepted") is True),
                                 "label": "选择尝试"},
        "experiments_declined": {"value": sum(1 for e in exps if e.get("accepted") is False),
                                 "label": "选择不参与"},
    }


def compute_series(observations, start, end, days, bucket_days=7):
    """Weekly buckets per metric, for trend lines.

    Single pass: every timestamp is parsed once and mapped to its bucket by
    arithmetic, instead of re-parsing and re-scanning per metric per bucket
    (the old shape was O(buckets x metrics x observations) with a fromisoformat
    call for every combination -- seconds of pure waste on a few thousand rows).
    """
    if not observations:
        return {"buckets": [], "metrics": {}}
    prepared = [(o, _parse(o.get("ts"))) for o in observations]
    times = sorted(t for _, t in prepared if t)
    if not times:
        return {"buckets": [], "metrics": {}}
    first = start or times[0]
    span_days = max(1, int((end - first).total_seconds() // 86400) + 1)
    n = max(1, math.ceil(span_days / bucket_days))
    n = min(n, 60)

    buckets, edges = [], []
    for i in range(n):
        b_start = first + timedelta(days=i * bucket_days)
        b_end = min(end, b_start + timedelta(days=bucket_days))
        edges.append((b_start, b_end))
        buckets.append(_iso(b_start)[:10])

    counts = {name: [0] * n for name in METRIC_SPECS}
    bucket_seconds = bucket_days * 86400.0
    for o, t in prepared:
        if t is None:
            continue
        idx = int((t - first).total_seconds() // bucket_seconds)
        if idx < 0 or idx >= n:
            continue
        for name, spec in METRIC_SPECS.items():
            if _matches(spec, o):
                counts[name][idx] += 1

    series = {}
    for name, spec in METRIC_SPECS.items():
        cs = counts[name]
        series[name] = {
            "label": spec["label"],
            "values": [_score(cs[i], bucket_days, spec["rate_k"]) for i in range(n)],
            "counts": cs,
        }
    return {"buckets": buckets, "bucket_days": bucket_days, "metrics": series}


def compute(window="30D", now=None, persist=True):
    now = now or datetime.now(timezone.utc)
    start, end, days = window_bounds(window, now)
    all_obs = store.observations()
    # 每条观察的 ts 只解析一次：窗口过滤、ALL 跨度、序列分桶共用。
    prepared = [(o, _parse(o.get("ts"))) for o in all_obs]
    obs = [o for o, t in prepared
           if t is not None and (start is None or t >= start) and t <= end]
    if days is None:
        first = min((t for _, t in prepared if t is not None), default=now)
        days = max(1, int((now - first).total_seconds() // 86400) + 1)

    result = {
        "schema_version": schema.SCHEMA_VERSION,
        "generated_at": _iso(now),
        "window": window,
        "window_days": days,
        "window_start": _iso(start) if start else None,
        "window_end": _iso(end),
        "observation_count": len(obs),
        "total_observation_count": len(all_obs),
        "metrics": compute_metrics(obs, start, end, days),
        "behavior": compute_behavior(obs, start, end),
        "series": compute_series(obs, start, end, days),
        "growth": growth_mod.state(),
        "projects": project_mod.summary(),
        "experiments": experiment_mod.stats(),
        "experiment_fit": experiment_mod.what_works(),
        "memory_counts": store.load("profile").get("counts", {}),
        "disclaimer": ("以上指标描述的是可观察的行为频率变化，"
                       "不是医学量表，也不代表任何能力评级或治疗效果。"),
    }
    if persist:
        cur = store.load("analytics")
        cur["schema_version"] = schema.SCHEMA_VERSION
        cur["generated_at"] = result["generated_at"]
        cur.setdefault("windows", {})[window] = {
            k: v for k, v in result.items() if k not in ("series",)
        }
        cur["metrics"] = result["metrics"]
        cur["series"] = result["series"]
        store.save("analytics", cur)
    return result


def compare(window_a="30D", window_b=None, now=None):
    """Change between the current window and the immediately preceding one.

    Only metrics are needed here, so this filters both windows directly
    instead of running two full compute() passes (series, behavior, growth
    state were all discarded work).
    """
    now = now or datetime.now(timezone.utc)
    days = WINDOWS.get(window_a)
    all_obs = store.observations()
    prepared = [(o, _parse(o.get("ts"))) for o in all_obs]
    if days is None:
        # ALL 窗口的跨度从最早一条观察算起，与 compute() 的口径保持一致。
        first = min((t for _, t in prepared if t is not None), default=now)
        days = max(1, int((now - first).total_seconds() // 86400) + 1)
    cur_start = now - timedelta(days=days)
    cur_obs = [o for o, t in prepared
               if t is not None and cur_start <= t <= now]
    prev_end = cur_start
    prev_start = prev_end - timedelta(days=days)
    prev_obs = [o for o, t in prepared
                if t is not None and prev_start <= t < prev_end]
    cur_m = compute_metrics(cur_obs, cur_start, now, days)
    prev = compute_metrics(prev_obs, prev_start, prev_end, days)

    deltas = {}
    for name, m in cur_m.items():
        p = prev.get(name, {})
        deltas[name] = {
            "label": m["label"],
            "current": m["value"], "previous": p.get("value", 0.0),
            "delta": round(m["value"] - p.get("value", 0.0), 1),
            "current_samples": m["sample_count"],
            "previous_samples": p.get("sample_count", 0),
            "confidence": min(m["confidence"], p.get("confidence", 0.0)),
        }
    return {"window": window_a, "deltas": deltas,
            "previous_window": {"start": _iso(prev_start), "end": _iso(prev_end)}}

