#!/usr/bin/env python3
"""VibeBridge command line interface.

This is the only sanctioned way to read or write VibeBridge data. The model
layer never edits JSON by hand. Every write goes through:

    schema validation -> atomic write -> backup when needed -> index -> log

All output is UTF-8 JSON so it can be parsed reliably, including on Windows
consoles that default to a legacy code page.
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import paths
import schema
import store


def emit(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.exit(code)


def fail(msg, **extra):
    emit({"ok": False, "error": msg, **extra}, code=1)


def require_init():
    if not paths.p("version").exists():
        fail("VibeBridge 尚未初始化，请先运行: vb init")


def parse_json_arg(value, what="payload"):
    if not value:
        return None
    if os.path.exists(value):
        with open(value, "r", encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        fail("无法解析 " + what + " 的 JSON: " + str(e))


# ---------------------------------------------------------------- init
def cmd_init(args):
    """Infrastructure only. Asks the user nothing. Safe to run repeatedly."""
    home = paths.home()
    existed = paths.p("version").exists()
    created, kept = [], []

    home.mkdir(parents=True, exist_ok=True)
    for sub in paths.DIRS:
        d = home / sub
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(sub + "/")

    for key in ["version", "config", "profile", "candidates", "verified",
                "conflicts", "strategies", "sessions", "projects",
                "experiments", "milestones", "growth", "analytics"]:
        fp = paths.p(key)
        if fp.exists():
            kept.append(key)
        else:
            store.write_json(fp, schema.DEFAULTS[key]())
            created.append(key)

    obs = paths.p("observations")
    if not obs.exists():
        obs.parent.mkdir(parents=True, exist_ok=True)
        obs.touch()
        created.append("observations")
    else:
        kept.append("observations")

    import migrate
    mig = migrate.status()
    if not mig["up_to_date"]:
        mig["result"] = migrate.run()

    checks = {
        "python": sys.version.split()[0],
        "data_root": str(home),
        "writable": os.access(str(home), os.W_OK),
        "utf8_output": str(getattr(sys.stdout, "encoding", "") or "utf-8"
                           ).lower().replace("-", "") == "utf8",
    }
    safety_ok = None
    try:
        import safety
        safety_ok = all(v for _, v in safety.self_test())
    except ImportError:
        safety_ok = False

    store.log_event("INIT", "reinit" if existed else "first_init")
    emit({
        "ok": True,
        "already_initialized": existed,
        "data_root": str(home),
        "created": created,
        "kept": kept,
        "schema_version": schema.SCHEMA_VERSION,
        "skill_version": schema.SKILL_VERSION,
        "migration": mig,
        "environment": checks,
        "safety_self_test": safety_ok,
        "note": "初始化只建立基础设施，不收集任何个人信息，不提任何问题。",
    })


def cmd_doctor(args):
    import safety
    import migrate
    repair = None
    if getattr(args, "repair", False):
        repair = store.compact_observations()
        if repair.get("repaired"):
            import memory
            import profile as profile_mod
            repair["rebuilt"] = memory.rebuild()
            profile_mod.rebuild()
    res = store.integrity_check()
    res["migration"] = migrate.status()
    res["safety_self_test"] = [{"check": k, "pass": v} for k, v in safety.self_test()]
    res["backups"] = store.list_backups()[-5:]
    res["healthy"] = not res["issues"] and all(v for _, v in safety.self_test())
    if repair is not None:
        res["repair"] = repair
    if res["issues"] and not repair:
        res["hint"] = "如果问题来自损坏的日志行，可运行 vb doctor --repair 进行显式修复。"
    emit(res)


# ---------------------------------------------------------------- observe
def cmd_observe(args):
    require_init()
    import observe
    payload = parse_json_arg(args.json, "observations")
    if payload is None:
        if not (args.category and args.key and args.statement):
            fail("需要 --json，或同时提供 --category --key --statement")
        payload = [{
            "category": args.category, "key": args.key,
            "statement": args.statement, "polarity": args.polarity,
            "strength": args.strength,
            "domains": args.domains.split(",") if args.domains else [],
            "excerpt": args.excerpt or "",
        }]
    if isinstance(payload, dict):
        payload = [payload]

    sid = args.session
    if sid == "auto":
        import session as session_mod
        sid = session_mod.ensure_open(project=args.project)["session_id"]
    try:
        res = observe.record(payload, session_id=sid, project_id=args.project,
                             experiment_id=args.experiment, ts=args.ts)
    except schema.ValidationError as e:
        fail("观察数据未通过校验: " + str(e))

    import profile as profile_mod
    profile_mod.rebuild()
    res["ok"] = True
    res["session_id"] = sid
    emit(res)


def cmd_memory(args):
    require_init()
    import observe
    import memory
    if args.action == "list":
        cands = store.load("candidates")["items"]
        rows = []
        for k, v in cands.items():
            if args.status and v["status"] != args.status:
                continue
            if v["confidence"] < args.min_confidence:
                continue
            rows.append({"key": k, "category": v["category"],
                         "statement": v["statement"], "confidence": v["confidence"],
                         "status": v["status"], "evidence_count": v["evidence_count"],
                         "contradict_count": v.get("contradict_count", 0),
                         "sessions": len(v.get("sessions", [])),
                         "first_seen": v["first_seen"], "last_seen": v["last_seen"]})
        rows.sort(key=lambda r: -r["confidence"])
        emit({"ok": True, "total": len(rows), "items": rows[:args.limit]})
    elif args.action == "show":
        if not args.key:
            fail("show 需要 --key")
        ev = observe.evidence_for(args.key)
        if not ev:
            fail("未找到该记忆键: " + args.key)
        emit({"ok": True, "memory": ev})
    elif args.action == "conflicts":
        emit({"ok": True, "conflicts": store.load("conflicts")["items"][-args.limit:]})
    elif args.action == "rebuild":
        store.snapshot("pre_rebuild")
        res = memory.rebuild()
        import profile as profile_mod
        profile_mod.rebuild()
        emit({"ok": True, "rebuilt": res,
              "note": "已从不可变的 observations.jsonl 完整重建全部派生记忆。"})
    elif args.action == "decay":
        cands = store.load("candidates")
        changed = memory.refresh_decay(cands)
        store.save("candidates", cands)
        store.save("verified", memory.project_verified(cands))
        import profile as profile_mod
        profile_mod.rebuild()
        emit({"ok": True, "changed": [{"key": c[0], "event": c[1],
                                       "from": round(c[2], 4), "to": round(c[3], 4)}
                                      for c in changed]})


def cmd_profile(args):
    require_init()
    import profile as profile_mod
    if args.rebuild:
        profile_mod.rebuild()
    if args.strategies:
        emit({"ok": True, "strategies": profile_mod.strategies()})
    emit({"ok": True, "profile": profile_mod.view(min_confidence=args.min_confidence,
                                                  include_evidence=args.evidence)})


# ---------------------------------------------------------------- session
def cmd_session(args):
    require_init()
    import session as session_mod
    if args.action == "open":
        emit({"ok": True, "session": session_mod.open_session(project=args.project,
                                                              ts=args.ts)})
    elif args.action == "ensure":
        emit({"ok": True, "session": session_mod.ensure_open(project=args.project,
                                                             ts=args.ts)})
    elif args.action == "close":
        sid = args.id or (session_mod.current() or {}).get("session_id")
        if not sid:
            fail("没有可关闭的会话")
        res = session_mod.close_session(sid, summary=args.summary or "",
                                        task_in_progress=args.task_in_progress,
                                        ts=args.ts)
        emit({"ok": True, "result": res})
    elif args.action == "update":
        if not args.id:
            fail("update 需要 --id")
        fields = parse_json_arg(args.json, "session fields") or {}
        if args.summary:
            fields["summary"] = args.summary
        emit({"ok": True, "session": session_mod.update(args.id, **fields)})
    elif args.action == "show":
        sid = args.id or (session_mod.current() or {}).get("session_id")
        if not sid:
            fail("没有会话可显示")
        emit({"ok": True, "session": session_mod.load_session(sid)})
    elif args.action == "list":
        emit({"ok": True, "current": session_mod.current(),
              "pending_summaries": session_mod.pending_summaries(),
              "sessions": session_mod.listing(limit=args.limit)})


# ---------------------------------------------------------------- project
def cmd_project(args):
    require_init()
    import project as project_mod
    if args.action == "create":
        if not args.name:
            fail("create 需要 --name")
        emit({"ok": True, "project": project_mod.create(
            args.name, idea=args.idea or "",
            stack=args.stack.split(",") if args.stack else [], ts=args.ts)})
    elif args.action == "update":
        if not args.id:
            fail("update 需要 --id")
        fields = parse_json_arg(args.json, "project fields") or {}
        if args.stage:
            fields["stage"] = args.stage
        try:
            rec = project_mod.update(args.id, ts=args.ts, event=args.event, **fields)
        except ValueError as e:
            fail(str(e))
        if rec is None:
            fail("未找到项目: " + args.id)
        emit({"ok": True, "project": rec})
    elif args.action == "bump":
        if not (args.id and args.field):
            fail("bump 需要 --id 和 --field")
        emit({"ok": True, "project": project_mod.bump(args.id, args.field,
                                                      amount=args.amount, ts=args.ts)})
    elif args.action == "list":
        emit({"ok": True, "summary": project_mod.summary(),
              "projects": project_mod.listing()})
    elif args.action == "timeline":
        emit({"ok": True, "timeline": project_mod.timeline()})


# ---------------------------------------------------------------- growth
def cmd_grow(args):
    require_init()
    import growth as growth_mod
    if args.action == "state":
        emit({"ok": True, "growth": growth_mod.state()})
    elif args.action == "opportunities":
        emit({"ok": True, "opportunities": growth_mod.opportunities(
            session_id=args.session, task_in_progress=args.task_in_progress,
            now_ts=args.ts, limit=args.limit)})
    elif args.action == "decline":
        emit({"ok": True, "result": growth_mod.decline(reason=args.reason or "",
                                                       session_id=args.session,
                                                       now_ts=args.ts)})
    elif args.action == "ease":
        emit({"ok": True, "result": growth_mod.ease(domain=args.domain,
                                                    steps=args.steps, now_ts=args.ts)})
    elif args.action == "pause":
        emit({"ok": True, "result": growth_mod.pause(True)})
    elif args.action == "resume":
        emit({"ok": True, "result": growth_mod.pause(False)})


def cmd_experiment(args):
    require_init()
    import experiment as experiment_mod
    if args.action == "propose":
        if not args.objective:
            fail("propose 需要 --objective")
        try:
            res = experiment_mod.propose(
                args.objective, context=args.context or "",
                domain=args.domain or "expression", difficulty=args.difficulty,
                suggested_action=args.action_text or "", session_id=args.session,
                project_id=args.project, now_ts=args.ts, force=args.force)
        except (ValueError, KeyError) as e:
            fail(str(e))
        emit({"ok": True, **res})
    elif args.action == "accept":
        emit({"ok": True, "experiment": experiment_mod.accept(args.id)})
    elif args.action == "decline":
        emit({"ok": True, **experiment_mod.decline(args.id, reason=args.reason or "",
                                                   session_id=args.session, now_ts=args.ts)})
    elif args.action == "complete":
        if not (args.id and args.result):
            fail("complete 需要 --id 和 --result")
        try:
            res = experiment_mod.complete(
                args.id, args.result, outcome=args.outcome or "",
                stress=args.stress, engagement=args.engagement,
                recovery_time=args.recovery, repeat_interest=args.repeat,
                notes=args.notes or "", now_ts=args.ts)
        except ValueError as e:
            fail(str(e))
        if res is None:
            fail("未找到实验: " + str(args.id))
        emit({"ok": True, **res})
    elif args.action == "list":
        emit({"ok": True, "stats": experiment_mod.stats(),
              "experiments": experiment_mod.listing(limit=args.limit,
                                                    result=args.result,
                                                    domain=args.domain)})
    elif args.action == "what-works":
        emit({"ok": True, "analysis": experiment_mod.what_works()})


# ---------------------------------------------------------------- analytics
def cmd_analytics(args):
    require_init()
    import analytics
    emit({"ok": True, "analytics": analytics.compute(window=args.window,
                                                     persist=not args.no_save)})


def cmd_insight(args):
    require_init()
    import insight
    emit({"ok": True, "insights": insight.generate(window=args.window)})


def cmd_reflect(args):
    require_init()
    import insight
    emit({"ok": True, "reflection": insight.reflect(window=args.window)})


def cmd_report(args):
    require_init()
    import report
    res = report.build(window=args.window, open_after=args.open)
    emit({"ok": True, **res})


def cmd_milestone(args):
    require_init()
    data = store.load("milestones")
    if args.action == "add":
        if not args.title:
            fail("add 需要 --title")
        import safety
        safety.assert_clean(args.title, "milestone.title")
        rec = {"id": "ms_" + str(len(data["items"]) + 1).zfill(4),
               "ts": args.ts or schema.now(), "title": args.title,
               "detail": args.detail or "", "kind": args.kind or "growth_signal",
               "project_id": args.project, "session_id": args.session,
               "evidence": (args.evidence.split(",") if args.evidence else [])}
        data["items"].append(rec)
        store.save("milestones", data)
        emit({"ok": True, "milestone": rec})
    else:
        emit({"ok": True, "milestones": data["items"]})


# ---------------------------------------------------------------- data ops
def cmd_backup(args):
    require_init()
    if args.action == "create":
        emit({"ok": True, "snapshot": store.snapshot(args.tag or "manual").name})
    elif args.action == "list":
        emit({"ok": True, "backups": store.list_backups()})
    elif args.action == "restore":
        if not args.name:
            fail("restore 需要 --name")
        emit({"ok": store.restore(args.name), "restored": args.name})


def cmd_migrate(args):
    import migrate
    if args.action == "status":
        emit({"ok": True, **migrate.status()})
    elif args.action == "run":
        emit({"ok": True, **migrate.run(dry_run=args.dry_run)})
    elif args.action == "rollback":
        emit({"ok": True, **migrate.rollback(args.name)})


def cmd_export(args):
    require_init()
    import shutil
    import zipfile
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = paths.d("exports") / ("vibebridge_export_" + stamp + ".zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    home = paths.home()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(home):
            dirs[:] = [d for d in dirs if d not in ("exports", "backups")]
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, home))
    emit({"ok": True, "export": str(out),
          "note": "导出文件包含全部本地数据，请自行决定是否分享。"})


def cmd_reset(args):
    require_init()
    import growth as growth_mod
    if args.scope == "difficulty":
        emit({"ok": True, "result": growth_mod.ease(domain=args.domain,
                                                    steps=args.steps,
                                                    reason="用户主动重置当前难度")})
    elif args.scope == "growth":
        snap = store.snapshot("pre_growth_reset")
        store.save("growth", schema.default_growth())
        emit({"ok": True, "reset": "growth", "backup": snap.name,
              "note": "只重置成长状态，记忆与观察完整保留。"})
    elif args.scope == "all":
        if not args.confirm:
            emit({"ok": False, "requires_confirmation": True,
                  "warning": "这将永久删除全部本地数据，包括不可变的观察日志。",
                  "how_to": "确认后重新执行并加上 --confirm"})
        import shutil
        home = paths.home()
        snap = None
        if not args.no_backup:
            snap = str(store.snapshot("pre_full_reset"))
        target = str(home)
        keep = paths.d("backups")
        for entry in home.iterdir():
            if args.no_backup or entry != keep:
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
        emit({"ok": True, "deleted": target, "backup_kept": snap,
              "note": "数据已删除。运行 vb init 可重新开始。"})


def cmd_config(args):
    require_init()
    cfg = store.load("config")
    if args.set:
        path, _, value = args.set.partition("=")
        if not _:
            fail("格式应为 --set key.path=value")
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
        node = cfg
        parts = path.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
        store.save("config", cfg)
    emit({"ok": True, "config": cfg})


def cmd_safety(args):
    import safety
    if args.text:
        emit({"ok": True, "forbidden_terms": safety.lint(args.text),
              "crisis": safety.scan_crisis(args.text)})
    emit({"ok": True, "rules": safety.RULES,
          "prohibited_actions": safety.PROHIBITED_ACTIONS,
          "self_test": [{"check": k, "pass": v} for k, v in safety.self_test()]})


# ---------------------------------------------------------------- parser
def build_parser():
    ap = argparse.ArgumentParser(prog="vb", description="VibeBridge 数据层命令行")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化基础设施，不询问任何个人信息").set_defaults(fn=cmd_init)
    p = sub.add_parser("doctor", help="数据完整性与安全自检")
    p.add_argument("--repair", action="store_true",
                   help="显式修复被截断的日志行，原文件仍会保留在 quarantine")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("observe", help="记录行为观察")
    p.add_argument("--json", help="观察对象或数组，也可以是文件路径")
    p.add_argument("--category")
    p.add_argument("--key")
    p.add_argument("--statement")
    p.add_argument("--polarity", default="support", choices=schema.POLARITIES)
    p.add_argument("--strength", type=float, default=0.5)
    p.add_argument("--domains")
    p.add_argument("--excerpt")
    p.add_argument("--session", default="auto")
    p.add_argument("--project")
    p.add_argument("--experiment")
    p.add_argument("--ts")
    p.set_defaults(fn=cmd_observe)

    p = sub.add_parser("memory", help="查看与管理长期记忆")
    p.add_argument("action", choices=["list", "show", "conflicts", "rebuild", "decay"])
    p.add_argument("--key")
    p.add_argument("--status", choices=["candidate", "verified", "weakened", "retired"])
    p.add_argument("--min-confidence", dest="min_confidence", type=float, default=0.0)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_memory)

    p = sub.add_parser("profile", help="查看自动形成的用户画像")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--strategies", action="store_true")
    p.add_argument("--evidence", action="store_true")
    p.add_argument("--min-confidence", dest="min_confidence", type=float, default=0.0)
    p.set_defaults(fn=cmd_profile)

    p = sub.add_parser("session", help="会话记录")
    p.add_argument("action", choices=["open", "ensure", "close", "update", "show", "list"])
    p.add_argument("--id")
    p.add_argument("--project")
    p.add_argument("--summary")
    p.add_argument("--json")
    p.add_argument("--task-in-progress", dest="task_in_progress", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--ts")
    p.set_defaults(fn=cmd_session)

    p = sub.add_parser("project", help="Vibe Coding 项目追踪")
    p.add_argument("action", choices=["create", "update", "bump", "list", "timeline"])
    p.add_argument("--id")
    p.add_argument("--name")
    p.add_argument("--idea")
    p.add_argument("--stack")
    p.add_argument("--stage")
    p.add_argument("--field")
    p.add_argument("--amount", type=int, default=1)
    p.add_argument("--event")
    p.add_argument("--json")
    p.add_argument("--ts")
    p.set_defaults(fn=cmd_project)

    p = sub.add_parser("grow", help="成长状态与自然机会")
    p.add_argument("action", choices=["state", "opportunities", "decline",
                                      "ease", "pause", "resume"])
    p.add_argument("--session")
    p.add_argument("--domain", choices=schema.DOMAINS)
    p.add_argument("--steps", type=int, default=1)
    p.add_argument("--reason")
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--task-in-progress", dest="task_in_progress", action="store_true")
    p.add_argument("--ts")
    p.set_defaults(fn=cmd_grow)

    p = sub.add_parser("experiment", help="成长实验")
    p.add_argument("action", choices=["propose", "accept", "decline",
                                      "complete", "list", "what-works"])
    p.add_argument("--id")
    p.add_argument("--objective")
    p.add_argument("--context")
    p.add_argument("--domain", choices=schema.DOMAINS)
    p.add_argument("--difficulty", type=int, default=2)
    p.add_argument("--action-text", dest="action_text")
    p.add_argument("--session")
    p.add_argument("--project")
    p.add_argument("--result", choices=schema.EXPERIMENT_RESULTS)
    p.add_argument("--outcome")
    p.add_argument("--stress", type=float, default=0.0)
    p.add_argument("--engagement", type=float, default=0.0)
    p.add_argument("--recovery", type=int)
    p.add_argument("--repeat", type=lambda v: v.lower() in ("1", "true", "yes"))
    p.add_argument("--notes")
    p.add_argument("--reason")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--force", action="store_true",
                   help="仅用于测试，绕过安全闸门")
    p.add_argument("--ts")
    p.set_defaults(fn=cmd_experiment)

    p = sub.add_parser("milestone", help="成长里程碑")
    p.add_argument("action", choices=["add", "list"])
    p.add_argument("--title")
    p.add_argument("--detail")
    p.add_argument("--kind")
    p.add_argument("--project")
    p.add_argument("--session")
    p.add_argument("--evidence")
    p.add_argument("--ts")
    p.set_defaults(fn=cmd_milestone)

    for name, fn, helptext in [("analytics", cmd_analytics, "长期指标"),
                               ("insight", cmd_insight, "自动分析"),
                               ("reflect", cmd_reflect, "低压力复盘")]:
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--window", default="30D",
                       choices=["7D", "30D", "90D", "6M", "ALL"])
        p.add_argument("--no-save", dest="no_save", action="store_true")
        p.set_defaults(fn=fn)

    p = sub.add_parser("report", help="生成交互式 HTML 报告")
    p.add_argument("--window", default="30D",
                   choices=["7D", "30D", "90D", "6M", "ALL"])
    p.add_argument("--open", action="store_true")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("backup", help="备份与恢复")
    p.add_argument("action", choices=["create", "list", "restore"])
    p.add_argument("--name")
    p.add_argument("--tag")
    p.set_defaults(fn=cmd_backup)

    p = sub.add_parser("migrate", help="schema 迁移")
    p.add_argument("action", choices=["status", "run", "rollback"])
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p.add_argument("--name")
    p.set_defaults(fn=cmd_migrate)

    sub.add_parser("export", help="导出全部本地数据").set_defaults(fn=cmd_export)

    p = sub.add_parser("reset", help="降低难度或重置状态")
    p.add_argument("scope", choices=["difficulty", "growth", "all"])
    p.add_argument("--domain", choices=schema.DOMAINS)
    p.add_argument("--steps", type=int, default=1)
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--no-backup", dest="no_backup", action="store_true")
    p.set_defaults(fn=cmd_reset)

    p = sub.add_parser("config", help="查看或修改配置")
    p.add_argument("--set")
    p.set_defaults(fn=cmd_config)

    p = sub.add_parser("safety", help="安全规则与文本检查")
    p.add_argument("--text")
    p.set_defaults(fn=cmd_safety)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except SystemExit:
        raise
    except Exception as e:
        store.log_event("CLI_ERROR", type(e).__name__ + ": " + str(e))
        fail(type(e).__name__ + ": " + str(e))


if __name__ == "__main__":
    main()

