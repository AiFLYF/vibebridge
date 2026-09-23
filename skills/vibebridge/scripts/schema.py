"""Schema definitions, defaults and validation for VibeBridge.

Design rule: observations.jsonl is append-only and immutable -- it is the single
source of truth. Everything else (candidates, verified, profile, analytics) is a
derived artifact and can be rebuilt from observations at any time.
"""
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0.0"
SKILL_VERSION = "1.1.0"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# Observation taxonomy
# --------------------------------------------------------------------------
CATEGORIES = [
    "interest",
    "strength",
    "communication_preference",
    "interaction_preference",
    "support_preference",
    "behavior_pattern",
    "engagement_pattern",
    "potential_stressor",
    "successful_strategy",
    "unsuccessful_strategy",
    "social_experience",
    "self_advocacy",
    "project_event",
    "growth_signal",
]

POLARITIES = ["support", "contradict", "neutral"]

DOMAINS = ["expression", "communication", "social", "collaboration",
           "independence", "self_advocacy"]

DOMAIN_LABELS = {
    "expression": "自我表达",
    "communication": "沟通",
    "social": "社会互动",
    "collaboration": "协作",
    "independence": "独立性",
    "self_advocacy": "自我倡导",
}

LADDERS = {
    "social": [
        "与 AI 表达",
        "解释自己的作品",
        "发布作品",
        "阅读外部反馈",
        "回复一条公开评论",
        "一对一异步交流",
        "小规模群体交流",
        "项目协作",
        "语音交流",
        "现实场景",
        "学习 / 工作 / 长期协作",
    ],
    "expression": [
        "最短回应", "描述需求", "描述想法", "描述感受", "解释选择理由",
        "主动分享进展", "主动展示作品", "向他人解释作品", "公开表达观点",
        "回应不同意见", "持续公开创作",
    ],
    "communication": [
        "被动回应", "简短主动提问", "完整描述问题", "澄清误解", "异步文字往来",
        "多轮往复", "面向陌生人的文字沟通", "结构化说明", "实时文字",
        "语音", "面对面",
    ],
    "independence": [
        "全程依赖引导", "能选择方案", "能提出修改", "能独立完成小片段",
        "能独立调试", "能独立完成模块", "能独立完成项目", "能自定义目标",
        "能规划多步骤", "能自主发布", "能长期自主推进",
    ],
    "self_advocacy": [
        "不表达需求", "表达简单偏好", "表达不适", "请求更多时间", "请求换沟通方式",
        "解释自己的困难", "提前说明需求", "主动设定边界", "与他人协商条件",
        "在正式场合说明需求", "稳定自我倡导",
    ],
    "collaboration": [
        "独自创作", "接受他人建议", "使用他人的代码或素材", "向他人提问",
        "回应他人的 issue", "提交一次改动", "与一人共同完成小任务",
        "参与多人项目", "承担一个明确模块", "协调他人工作", "长期共同维护",
    ],
}

EXPERIMENT_RESULTS = [
    "successful", "partial", "unsuccessful", "not_suitable",
    "cancelled", "paused", "pending",
]

# --------------------------------------------------------------------------
# Confidence model
# --------------------------------------------------------------------------
PROMOTE_CONFIDENCE = 0.75
PROMOTE_EVIDENCE = 3
PROMOTE_SESSIONS = 2
DEMOTE_CONFIDENCE = 0.50
RETIRE_CONFIDENCE = 0.12
HALF_LIFE_DAYS = 120.0


def default_config():
    return {
        "schema_version": SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "created_at": now(),
        "locale": "zh-CN",
        "privacy": {
            "local_only": True,
            "store_raw_excerpts": True,
            "excerpt_max_chars": 240,
        },
        "growth": {
            "enabled": True,
            "max_offers_per_session": 1,
            "min_hours_between_offers": 20,
            "quiet_days_after_declines": 7,
            "decline_streak_trigger": 2,
        },
        "confidence": {
            "promote_confidence": PROMOTE_CONFIDENCE,
            "promote_evidence": PROMOTE_EVIDENCE,
            "promote_sessions": PROMOTE_SESSIONS,
            "demote_confidence": DEMOTE_CONFIDENCE,
            "half_life_days": HALF_LIFE_DAYS,
        },
        "report": {"default_window": "30D"},
    }


def default_version():
    return {
        "schema_version": SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "created_at": now(),
        "last_migration": None,
        "migrations": [],
    }


def default_profile():
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now(),
        "note": "本画像由行为观察自动聚合生成，不是医学评估，也不构成任何诊断。",
        "interests": [], "strengths": [],
        "communication_preferences": [], "interaction_preferences": [],
        "support_preferences": [], "behavior_patterns": [],
        "engagement_patterns": [], "potential_stressors": [],
        "successful_strategies": [], "unsuccessful_strategies": [],
        "social_experiences": [], "self_advocacy_patterns": [],
        "growth_opportunities": [],
        "counts": {},
    }


def default_growth():
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now(),
        "domains": {
            dm: {
                "level": 0, "stability": 0.0, "attempts": 0, "successes": 0,
                "last_change": None, "last_change_reason": "init",
                "cooldown_until": None, "history": [],
            } for dm in DOMAINS
        },
        "decline_streak": 0,
        "quiet_until": None,
        "last_offer_at": None,
        "offers_this_session": {},
        "paused": False,
    }


def default_analytics():
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now(),
        "metrics": {}, "windows": {}, "series": {},
    }


DEFAULTS = {
    "version": default_version,
    "config": default_config,
    "profile": default_profile,
    "growth": default_growth,
    "analytics": default_analytics,
    "candidates": lambda: {"schema_version": SCHEMA_VERSION, "items": {}},
    "verified": lambda: {"schema_version": SCHEMA_VERSION, "items": {}},
    "conflicts": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
    "strategies": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
    "sessions": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
    "projects": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
    "experiments": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
    "milestones": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
}


class ValidationError(Exception):
    pass


def validate_observation(o):
    """Validate and normalise one observation. Raises ValidationError on bad input."""
    if not isinstance(o, dict):
        raise ValidationError("observation must be an object")
    cat = o.get("category")
    if cat not in CATEGORIES:
        raise ValidationError("category must be one of " + ", ".join(CATEGORIES) + " (got: " + str(cat) + ")")
    key = (o.get("key") or "").strip()
    if not key:
        raise ValidationError("key is required (a stable snake_case belief identifier)")
    if not (o.get("statement") or "").strip():
        raise ValidationError("statement is required (neutral behavioural description)")
    pol = o.get("polarity", "support")
    if pol not in POLARITIES:
        raise ValidationError("polarity must be one of " + ", ".join(POLARITIES))
    try:
        strength = float(o.get("strength", 0.5))
    except (TypeError, ValueError):
        raise ValidationError("strength must be a number in [0,1]")
    if not 0.0 <= strength <= 1.0:
        raise ValidationError("strength must be within [0,1]")
    doms = o.get("domains") or []
    if not isinstance(doms, list):
        raise ValidationError("domains must be a list")
    bad = [x for x in doms if x not in DOMAINS]
    if bad:
        raise ValidationError("unknown domains: " + ", ".join(bad))
    return {
        "id": o.get("id"),
        "ts": o.get("ts") or now(),
        "session_id": o.get("session_id"),
        "project_id": o.get("project_id"),
        "experiment_id": o.get("experiment_id"),
        "category": cat,
        "key": key,
        "statement": o["statement"].strip(),
        "polarity": pol,
        "strength": strength,
        "domains": doms,
        "excerpt": (o.get("excerpt") or "")[:240],
        "source": o.get("source", "conversation"),
    }
