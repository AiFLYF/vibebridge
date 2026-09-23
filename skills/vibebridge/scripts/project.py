"""Vibe Coding project tracking.

Projects are the natural entry point of the whole system. The lifecycle
create -> build -> improve -> publish -> feedback -> communicate -> collaborate
is where most growth signals appear organically, without any training frame.

The user goal always comes first. A project is never redirected to serve a
growth metric.
"""
import schema
import store

STAGES = ["created", "building", "improving", "completed",
          "published", "feedback_received", "communicating", "collaborating"]


def _all():
    return store.load("projects")


def create(name, idea="", stack=None, ts=None):
    data = _all()
    pid = "proj_" + str(len(data["items"]) + 1).zfill(4)
    rec = {
        "id": pid,
        "name": name,
        "created_at": ts or schema.now(),
        "updated_at": ts or schema.now(),
        "stack": stack or [],
        "original_idea": idea,
        "stage": "created",
        "user_involvement": 0.0,
        "ai_assistance": 0.0,
        "completion": 0.0,
        "revisions": 0,
        "independent_parts": [],
        "published": False,
        "shared": False,
        "feedback_received": 0,
        "external_conversations": 0,
        "collaborators": 0,
        "events": [{"ts": ts or schema.now(), "type": "created", "detail": idea}],
    }
    data["items"].append(rec)
    store.save("projects", data)
    store.log_event("PROJECT_CREATE", pid + " " + name)
    return rec


def get(pid):
    for r in _all()["items"]:
        if r["id"] == pid or r["name"] == pid:
            return r
    return None


def update(pid, ts=None, event=None, **fields):
    data = _all()
    target = None
    for r in data["items"]:
        if r["id"] == pid or r["name"] == pid:
            target = r
            break
    if target is None:
        return None
    stage = fields.get("stage")
    if stage and stage not in STAGES:
        raise ValueError("未知阶段: " + str(stage) + "，可用: " + ", ".join(STAGES))

    for k, v in fields.items():
        if v is None:
            continue
        if k == "independent_parts":
            cur = target.get(k, [])
            cur.extend(v if isinstance(v, list) else [v])
            target[k] = cur
        elif k in ("revisions", "feedback_received", "external_conversations",
                   "collaborators"):
            target[k] = target.get(k, 0) + int(v) if fields.get("increment") else int(v)
        else:
            target[k] = v
    target.pop("increment", None)
    target["updated_at"] = ts or schema.now()
    target["events"].append({"ts": target["updated_at"],
                             "type": event or "update",
                             "detail": {k: v for k, v in fields.items()
                                        if k != "increment"}})
    if len(target["events"]) > 200:
        target["events"] = target["events"][-200:]
    store.save("projects", data)
    return target


def bump(pid, field, amount=1, ts=None, event=None):
    """Increment a counter such as revisions or feedback_received."""
    data = _all()
    for r in data["items"]:
        if r["id"] == pid or r["name"] == pid:
            r[field] = r.get(field, 0) + amount
            r["updated_at"] = ts or schema.now()
            r["events"].append({"ts": r["updated_at"], "type": event or ("bump_" + field),
                                "detail": {field: r[field]}})
            store.save("projects", data)
            return r
    return None


def listing(limit=None):
    items = sorted(_all()["items"], key=lambda r: r["created_at"])
    return items[-limit:] if limit else items


def summary():
    items = _all()["items"]
    done = [r for r in items if r["stage"] in ("completed", "published",
                                               "feedback_received",
                                               "communicating", "collaborating")]
    return {
        "total": len(items),
        "completed": len(done),
        "published": sum(1 for r in items if r.get("published")),
        "shared": sum(1 for r in items if r.get("shared")),
        "with_feedback": sum(1 for r in items if r.get("feedback_received", 0) > 0),
        "with_collaboration": sum(1 for r in items if r.get("collaborators", 0) > 0),
        "completion_rate": round(len(done) / len(items), 3) if items else 0.0,
    }


def timeline():
    """Flatten every project event into one chronological stream."""
    out = []
    for r in _all()["items"]:
        for e in r.get("events", []):
            out.append({"ts": e["ts"], "project": r["name"], "project_id": r["id"],
                        "type": e["type"], "detail": e.get("detail")})
    out.sort(key=lambda e: str(e["ts"]))
    return out

