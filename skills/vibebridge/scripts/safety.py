"""Safety engine. These are hard constraints enforced in code, not suggestions.

Three jobs:
  1. Gate growth offers, so the system can never nag, escalate after refusal,
     or interrupt work in progress.
  2. Lint every generated string for clinical or curative framing.
  3. Detect explicit crisis language and hand off to human support instead of
     inventing a plan.
"""
from datetime import datetime, timedelta, timezone

import schema
import store

# Vocabulary that must never appear in any generated artifact.
FORBIDDEN_PATTERNS = [
    "治愈率", "治愈", "治疗自闭", "康复率", "病情", "severity", "严重程度",
    "症状减轻", "恢复正常", "正常人", "缺陷", "矫正", "患者", "病人",
    "cure rate", "cured", "diagnosis", "diagnose", "disorder severity",
    "改善百分比", "痊愈",
]

# Disclaimers legitimately need to name what the system is NOT. These exact
# phrasings are stripped before linting, so a negation is never mistaken for a
# claim. Anything not on this list is still blocked.
DISCLAIMER_ALLOWLIST = [
    "不构成医学诊断、临床评估或治愈程度判断",
    "不构成医学诊断、临床评估或任何形式的疗效判断",
    "不是医学量表，也不代表任何能力评级或治疗效果",
    "不是医学评估，也不构成任何诊断",
    "不判断治愈程度",
    "不诊断、不评估严重程度、不判断治愈程度",
    "不构成医学诊断",
    "not a diagnosis",
    "does not diagnose",
]


def strip_allowed(text):
    """Remove allowlisted disclaimer phrasings before checking for violations."""
    out = str(text or "")
    for phrase in DISCLAIMER_ALLOWLIST:
        out = out.replace(phrase, " ")
    return out


# Behaviours the system is never allowed to push.
PROHIBITED_ACTIONS = [
    "force_eye_contact", "suppress_stimming", "mandatory_social",
    "forced_disclosure", "pressure_after_refusal", "goal_substitution",
    "manufactured_stress", "covert_manipulation",
]

CRISIS_MARKERS = [
    "自杀", "想死", "不想活", "结束生命", "自残", "伤害自己",
    "kill myself", "suicide", "self harm", "end my life", "want to die",
]

CRISIS_RESPONSE = (
    "检测到可能的高风险表达。系统已停止一切成长实验与建议生成。\n"
    "这超出了本工具的适用范围，请优先联系可信任的人或专业支持资源。\n"
    "中国大陆心理援助热线：12356；紧急情况请拨打 120 或当地急救电话。"
)


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def lint(text):
    """Return the list of forbidden terms found. Empty list means clean."""
    if not text:
        return []
    low = strip_allowed(text).lower()
    return [p for p in FORBIDDEN_PATTERNS if p.lower() in low]


def assert_clean(text, where="output"):
    hits = lint(text)
    if hits:
        store.log_event("SAFETY_BLOCK", where + " contained " + ", ".join(hits))
        raise ValueError("安全引擎拦截: " + where + " 含有禁用措辞 " + ", ".join(hits))
    return text


def scan_crisis(text):
    if not text:
        return {"crisis": False}
    low = str(text).lower()
    hits = [m for m in CRISIS_MARKERS if m.lower() in low]
    if hits:
        store.log_event("CRISIS_FLAG", "markers=" + str(len(hits)))
        return {"crisis": True, "action": "halt_experiments_and_refer",
                "message": CRISIS_RESPONSE}
    return {"crisis": False}


def can_offer(session_id=None, now_ts=None, task_in_progress=False):
    """Decide whether a growth opportunity may be surfaced right now.

    Refusal is never punished. It only makes the system quieter.
    """
    cfg = store.load("config")["growth"]
    g = store.load("growth")
    now = _parse(now_ts) or datetime.now(timezone.utc)

    if not cfg.get("enabled", True):
        return {"allowed": False, "reason": "成长机会功能已被用户关闭。"}
    if g.get("paused"):
        return {"allowed": False, "reason": "系统处于暂停状态，由用户主动恢复。"}

    quiet = _parse(g.get("quiet_until"))
    if quiet and now < quiet:
        return {"allowed": False, "reason": "处于静默期，至 " + g["quiet_until"] + " 之前不提出任何机会。",
                "quiet_until": g["quiet_until"]}

    if task_in_progress:
        return {"allowed": False, "reason": "当前任务尚未到自然完成点，不打断。"}

    last = _parse(g.get("last_offer_at"))
    min_gap = float(cfg.get("min_hours_between_offers", 20))
    if last and (now - last) < timedelta(hours=min_gap):
        nxt = (last + timedelta(hours=min_gap)).isoformat()
        return {"allowed": False, "reason": "距离上次提议不足 " + str(min_gap) + " 小时。",
                "next_allowed_at": nxt}

    if session_id:
        used = g.get("offers_this_session", {}).get(session_id, 0)
        if used >= int(cfg.get("max_offers_per_session", 1)):
            return {"allowed": False, "reason": "本次会话的提议额度已用完。"}

    return {"allowed": True, "reason": "满足全部安全条件。"}


RULES = [
    "不诊断、不评估严重程度、不判断治愈程度。",
    "不要求用户隐藏自闭特征，不把 stimming 视为需要消除的行为。",
    "不强迫眼神交流、不强迫社交、不强迫自我暴露。",
    "拒绝不是失败，未完成不是能力下降，两者都不降低任何评分。",
    "不在用户明确拒绝后继续推动同一件事。",
    "不为了训练目的制造压力。",
    "不偷偷替换用户目标，成长目标只能从用户目标中自然派生。",
    "用户随时可以暂停、降低难度、退出实验、更换方式。",
    "出现严重心理危机时停止自行设计方案，转向专业支持。",
]


def rules_text():
    return "\n".join("- " + r for r in RULES)


def self_test():
    """Verify the guard rails actually fire. Used by the doctor command."""
    results = []
    results.append(("forbidden lint", bool(lint("本月治愈率提升"))))
    results.append(("clean text passes", not lint("本月主动分享次数增加")))
    results.append(("crisis detect", scan_crisis("我想死")["crisis"]))
    results.append(("normal text safe", not scan_crisis("今天有点累")["crisis"]))
    return results
