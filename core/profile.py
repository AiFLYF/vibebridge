"""Long term user model.

The profile is a projection, never a source of truth. It is rebuilt from
memory, which is itself rebuilt from observations. Nothing here is a
diagnosis, a score of a person, or a clinical category.

    observations -> memory -> profile

never the other way round.
"""
import schema
import store
import project as project_mod
import experiment as experiment_mod
import growth as growth_mod

CATEGORY_TO_FIELD = {
    "interest": "interests",
    "strength": "strengths",
    "communication_preference": "communication_preferences",
    "interaction_preference": "interaction_preferences",
    "support_preference": "support_preferences",
    "behavior_pattern": "behavior_patterns",
    "engagement_pattern": "engagement_patterns",
    "potential_stressor": "potential_stressors",
    "successful_strategy": "successful_strategies",
    "unsuccessful_strategy": "unsuccessful_strategies",
    "social_experience": "social_experiences",
    "self_advocacy": "self_advocacy_patterns",
    "growth_signal": "growth_opportunities",
}

MIN_CONFIDENCE_FOR_PROFILE = 0.35


def _entry(item):
    return {
        "key": item["key"],
        "statement": item["statement"],
        "confidence": item["confidence"],
        "evidence_count": item["evidence_count"],
        "contradict_count": item.get("contradict_count", 0),
        "sessions": len(item.get("sessions", [])),
        "status": item["status"],
        "first_seen": item["first_seen"],
        "last_seen": item["last_seen"],
        "last_verified": item.get("last_verified"),
        "domains": item.get("domains", []),
        "evidence": item.get("evidence", [])[-8:],
    }


def rebuild():
    """Regenerate profile.json from the current belief table."""
    cands = store.load("candidates").get("items", {})
    prof = schema.default_profile()

    counts = {"verified": 0, "candidate": 0, "weakened": 0, "retired": 0}
    for item in cands.values():
        counts[item["status"]] = counts.get(item["status"], 0) + 1
        if item["status"] == "retired":
            continue
        if item["confidence"] < MIN_CONFIDENCE_FOR_PROFILE:
            continue
        field = CATEGORY_TO_FIELD.get(item["category"])
        if not field:
            continue
        prof[field].append(_entry(item))

    for field in CATEGORY_TO_FIELD.values():
        prof[field].sort(key=lambda e: (-e["confidence"], e["key"]))

    prof["counts"] = counts
    prof["counts"]["beliefs_total"] = len(cands)
    prof["updated_at"] = schema.now()
    store.save("profile", prof)
    _rebuild_strategies(cands)
    return prof


def _rebuild_strategies(cands):
    """Personalised interaction guide. Every line keeps its evidence."""
    preferred, difficult = [], []
    for item in cands.values():
        if item["status"] == "retired" or item["confidence"] < MIN_CONFIDENCE_FOR_PROFILE:
            continue
        row = {
            "statement": item["statement"], "key": item["key"],
            "confidence": item["confidence"],
            "evidence_count": item["evidence_count"],
            "last_verified": item.get("last_verified") or item["last_seen"],
            "evidence": item.get("evidence", [])[-6:],
        }
        if item["category"] in ("communication_preference", "interaction_preference",
                                "support_preference", "successful_strategy"):
            preferred.append(row)
        elif item["category"] in ("potential_stressor", "unsuccessful_strategy"):
            difficult.append(row)
    preferred.sort(key=lambda r: -r["confidence"])
    difficult.sort(key=lambda r: -r["confidence"])

    exp = experiment_mod.what_works()
    store.save("strategies", {
        "schema_version": schema.SCHEMA_VERSION,
        "generated_at": schema.now(),
        "preferred": preferred,
        "potentially_difficult": difficult,
        "experiment_fit": exp,
        "disclaimer": "以上为交互偏好总结，来源于行为观察，不是对个人的评价或分类。",
        "items": preferred + difficult,
    })


def view(min_confidence=0.0, include_evidence=False):
    prof = store.load("profile")
    out = {"updated_at": prof.get("updated_at"), "note": prof.get("note"),
           "counts": prof.get("counts", {}), "sections": {}}
    for field in CATEGORY_TO_FIELD.values():
        rows = [e for e in prof.get(field, []) if e["confidence"] >= min_confidence]
        if not include_evidence:
            rows = [{k: v for k, v in e.items() if k != "evidence"} for e in rows]
        if rows:
            out["sections"][field] = rows
    out["growth"] = growth_mod.state()
    out["projects"] = project_mod.summary()
    out["experiments"] = experiment_mod.stats()
    return out


def strategies():
    return store.load("strategies")

