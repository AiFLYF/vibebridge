"""Insight generation.

Hard rule: an inference is never written as a fact. Every produced item is
tagged with exactly one of three kinds.

    observed     something that is literally in the data, with evidence ids
    inference    a possible reading of that data, always hedged, with confidence
    suggestion   an optional next step the user may ignore at zero cost

Everything generated here passes through the safety linter before it is
returned, so curative or clinical framing cannot leak into a report.
"""
from datetime import datetime, timezone

import analytics
import experiment as experiment_mod
import growth as growth_mod
import project as project_mod
import safety
import schema
import store

OBSERVED = "observed"
INFERENCE = "inference"
SUGGESTION = "suggestion"

KIND_LABELS = {OBSERVED: "观察到的事实", INFERENCE: "可能的解读",
               SUGGESTION: "可选的下一步"}

MIN_SAMPLES_FOR_INFERENCE = 4
MEANINGFUL_DELTA = 8.0


def _item(kind, text, confidence=None, evidence=None, source=""):
    safety.assert_clean(text, "insight." + kind)
    return {"kind": kind, "kind_label": KIND_LABELS[kind], "text": text,
            "confidence": confidence, "evidence": evidence or [], "source": source}


def _facts(cmp_data, ana):
    out = []
    ordered = sorted(cmp_data["deltas"].values(), key=lambda d: -abs(d["delta"]))
    for d in ordered[:6]:
        if d["current_samples"] == 0 and d["previous_samples"] == 0:
            continue
        direction = "增加" if d["delta"] > 0 else ("减少" if d["delta"] < 0 else "基本持平")
        out.append(_item(
            OBSERVED,
            d["label"] + " 相关行为记录本期 " + str(d["current_samples"]) +
            " 次，上一同等周期 " + str(d["previous_samples"]) + " 次，" + direction + "。",
            confidence=d["confidence"],
            evidence=ana["metrics"].get(_key_of(cmp_data, d), {}).get("sources", [])[-5:],
            source="analytics.compare",
        ))

    beh = ana["behavior"]
    for name in ("projects_started", "projects_completed", "works_published",
                 "feedback_received", "collaborations"):
        v = beh.get(name, {}).get("value", 0)
        if v:
            out.append(_item(OBSERVED, beh[name]["label"] + "：本期 " + str(v) + " 次。",
                             confidence=0.9, source="analytics.behavior"))

    exps = ana["experiments"]
    if exps["total"]:
        out.append(_item(
            OBSERVED,
            "本期共提出 " + str(exps["total"]) + " 个可选机会，选择尝试 " +
            str(exps["accepted"]) + " 个，选择不参与 " + str(exps["declined"]) +
            " 个。不参与本身不计为失败。",
            confidence=0.95, source="experiments.stats"))
    return out


def _key_of(cmp_data, d):
    for k, v in cmp_data["deltas"].items():
        if v is d:
            return k
    return ""


def _inferences(cmp_data, ana):
    out = []
    for name, d in cmp_data["deltas"].items():
        m = ana["metrics"].get(name, {})
        if m.get("sample_count", 0) < MIN_SAMPLES_FOR_INFERENCE:
            continue
        if abs(d["delta"]) < MEANINGFUL_DELTA:
            continue
        if d["delta"] > 0:
            text = (d["label"] + " 相关行为出现得比上一周期更频繁，"
                    "这可能意味着当前的方式让这类行为更容易发生，但也可能只是"
                    "最近的项目内容不同导致的。")
        else:
            text = (d["label"] + " 相关行为出现得比上一周期更少。"
                    "这不一定代表能力变化，也可能是最近的关注点转移了。")
        out.append(_item(INFERENCE, text, confidence=round(d["confidence"] * 0.8, 3),
                         evidence=m.get("sources", [])[-5:], source="analytics.compare"))

    fit = ana.get("experiment_fit", {})
    if fit.get("samples", 0) >= 3 and fit.get("by_domain"):
        best = fit["by_domain"][0]
        out.append(_item(
            INFERENCE,
            "在已有样本中，" + schema.DOMAIN_LABELS.get(best["value"], best["value"]) +
            " 方向的尝试成功率较高（" + str(best["samples"]) + " 个样本），"
            "这可能是目前压力较低的方向。样本量仍然很小，只能作为参考。",
            confidence=best["confidence"], source="experiments.what_works"))

    g = ana["growth"]
    eased = [v["label"] for v in g["domains"].values() if v["trend"] == "easing"]
    if eased:
        out.append(_item(
            INFERENCE,
            "，".join(eased) + " 方向最近下调了难度。下调是系统的正常自适应，"
            "通常说明之前的步子偏大，而不是能力下降。",
            confidence=0.6, source="growth.state"))

    strat = store.load("strategies")
    if strat.get("preferred"):
        top = strat["preferred"][0]
        out.append(_item(
            INFERENCE,
            "目前证据最充分的有效方式是：" + top["statement"] +
            "（置信度 " + str(top["confidence"]) + "，" +
            str(top["evidence_count"]) + " 条证据）。",
            confidence=top["confidence"], evidence=top.get("evidence", []),
            source="strategies.preferred"))
    return out


def _suggestions(ana, session_id=None):
    out = []
    opp = growth_mod.opportunities(session_id=session_id, limit=2)
    gate = opp["gate"]
    if not gate["allowed"]:
        out.append(_item(SUGGESTION,
                         "当前不适合提出任何新的尝试（" + gate["reason"] + "）。"
                         "保持现状即可，系统会安静等待。",
                         confidence=1.0, source="safety.can_offer"))
        return out

    for c in opp["candidates"]:
        out.append(_item(
            SUGGESTION,
            "如果哪天正好合适，" + c["label"] + " 方向的下一个自然步骤可能是「" +
            c["next_label"] + "」。完全可选，不做也没有任何影响。",
            confidence=round(1.0 - c["estimated_difficulty"], 3),
            source="growth.opportunities"))

    strat = store.load("strategies")
    if strat.get("potentially_difficult"):
        d = strat["potentially_difficult"][0]
        out.append(_item(SUGGESTION,
                         "可以继续避开的方式：" + d["statement"] + "。"
                         "没有必要为了练习而强迫自己适应它。",
                         confidence=d["confidence"], source="strategies.difficult"))

    pending = [p for p in project_mod.listing()
               if p["stage"] in ("building", "improving")]
    if pending:
        out.append(_item(SUGGESTION,
                         "进行中的项目：" + "、".join(p["name"] for p in pending[:3]) +
                         "。优先把它们做成自己想要的样子，其他都是次要的。",
                         confidence=0.9, source="projects"))
    return out


def generate(window="30D", now=None, session_id=None):
    now = now or datetime.now(timezone.utc)
    ana = analytics.compute(window, now=now, persist=False)
    cmp_data = analytics.compare(window, now=now)

    items = _facts(cmp_data, ana) + _inferences(cmp_data, ana) + _suggestions(ana, session_id)
    grouped = {OBSERVED: [], INFERENCE: [], SUGGESTION: []}
    for it in items:
        grouped[it["kind"]].append(it)

    return {
        "generated_at": ana["generated_at"],
        "window": window,
        "sample_size": ana["observation_count"],
        "low_data": ana["observation_count"] < 10,
        "groups": grouped,
        "items": items,
        "rules": ["推断永远不写成事实。", "建议永远可以忽略，且不产生任何后果。",
                  "样本量不足时只呈现事实，不做解读。"],
        "disclaimer": ("本分析基于交互过程中产生的行为数据，用于长期自我观察与个性化支持，"
                       "不构成医学诊断、临床评估或任何形式的疗效判断。"),
    }


def reflect(window="7D", now=None):
    """Low pressure review. Descriptive, short, and free of any demand."""
    ins = generate(window=window, now=now)
    ana = analytics.compute(window, now=now, persist=False)
    lines = []
    if ana["observation_count"] == 0:
        lines.append("这段时间没有记录到什么，也完全没有关系。")
    else:
        for it in ins["groups"][OBSERVED][:3]:
            lines.append(it["text"])
    projects = [p for p in project_mod.listing() if p["stage"] != "created"][-3:]
    return {
        "window": window,
        "what_happened": lines,
        "recent_projects": [{"name": p["name"], "stage": p["stage"]} for p in projects],
        "milestones": store.load("milestones")["items"][-3:],
        "open_questions": [],
        "tone": "无需回答，无需评分，看看就好。",
        "no_action_required": True,
    }

