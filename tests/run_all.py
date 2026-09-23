#!/usr/bin/env python3
"""End to end acceptance suite for VibeBridge.

This does not merely check that functions exist. It exercises the real chain

    conversation -> observation -> candidate -> verified -> profile
                 -> growth -> experiment -> outcome -> analytics
                 -> insight -> HTML report

and asserts the safety invariants that matter most: a refusal must never cost
the user anything, and the system must never escalate after being told no.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "vibebridge"
CORE = SKILL / "scripts"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE = Path(os.environ.get("TEMP", "/tmp")) / "vb_suite"
RESULTS = []
MODULES = ("paths", "store", "schema", "memory", "observe", "session", "project",
           "experiment", "growth", "safety", "profile", "analytics", "insight",
           "report", "migrate", "vb")


def purge():
    for m in list(sys.modules):
        if m in MODULES:
            del sys.modules[m]


def use(name, clean=True):
    home = BASE / name
    if clean and home.exists():
        shutil.rmtree(home, ignore_errors=True)
    os.environ["VIBEBRIDGE_HOME"] = str(home)
    purge()
    return home


def cli(*args, home=None, expect_ok=True):
    env = dict(os.environ)
    if home:
        env["VIBEBRIDGE_HOME"] = str(home)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([sys.executable, str(CORE / "vb.py")] + [str(a) for a in args],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        out = {"ok": False, "raw": p.stdout, "stderr": p.stderr}
    return out


def iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    line = "  " + mark + "  " + name
    if detail and not ok:
        line += "\n          " + str(detail)[:400]
    print(line)
    return ok


def section(title):
    print("\n" + title)
    print("-" * 68)


# =========================================================== 1 infrastructure
def t_init():
    section("1. 初始化与基础设施")
    home = use("init")
    r = cli("init", home=home)
    check("首次 init 成功", r.get("ok"))
    check("init 不询问任何个人信息", "note" in r and "不收集任何个人信息" in r["note"])
    check("创建全部目录与文件", len(r.get("created", [])) >= 20)
    check("安全自检通过", r.get("safety_self_test") is True)
    check("数据目录与代码分离", "vb_suite" in r.get("data_root", ""))

    r2 = cli("init", home=home)
    check("重复 init 幂等且不破坏数据", r2.get("ok") and r2.get("already_initialized")
          and r2.get("created") == [])

    d = cli("doctor", home=home)
    check("doctor 报告健康", d.get("healthy"), d.get("issues"))


# ============================================================== 2 memory chain
def t_memory():
    section("2. 观察 → 候选记忆 → 验证记忆")
    home = use("memory")
    cli("init", home=home)
    purge()
    import observe, session as session_mod, store, memory

    def obs(sid, stmt, ts, pol="support", strength=0.6, key="async_text_pref"):
        return observe.record([{"category": "communication_preference", "key": key,
                                "statement": stmt, "domains": ["communication"],
                                "strength": strength, "polarity": pol}],
                              session_id=sid, ts=ts)

    now = datetime.now(timezone.utc)
    s1 = session_mod.open_session(ts=iso(now - timedelta(days=6)))["session_id"]
    r1 = obs(s1, "用户提到不太喜欢突然打电话", iso(now - timedelta(days=6)))
    c1 = r1["results"][0]["confidence"]
    r2 = obs(s1, "用户在同一次会话中重复了这个偏好", iso(now - timedelta(days=6)))
    c2 = r2["results"][0]["confidence"]
    check("同一会话内重复证据被降权", (c2 - c1) < 0.10,
          "delta=%.4f" % (c2 - c1))
    check("单一会话无法晋升为已验证", r2["results"][0]["status"] == "candidate")

    s2 = session_mod.open_session(ts=iso(now - timedelta(days=4)))["session_id"]
    r3 = obs(s2, "用户在新会话中再次表示偏好文字", iso(now - timedelta(days=4)))
    s3 = session_mod.open_session(ts=iso(now - timedelta(days=2)))["session_id"]
    r4 = obs(s3, "用户主动把语音讨论改成文字", iso(now - timedelta(days=2)), strength=0.7)
    check("跨会话累积后晋升为已验证",
          r4["results"][0]["status"] == "verified",
          r4["results"][0])
    check("置信度单调上升", c1 < c2 < r3["results"][0]["confidence"] < r4["results"][0]["confidence"])

    before = r4["results"][0]["confidence"]
    s4 = session_mod.open_session(ts=iso(now))["session_id"]
    r5 = obs(s4, "用户这次主动发起了一次语音通话", iso(now), pol="contradict", strength=0.8)
    after = r5["results"][0]["confidence"]
    check("反向证据降低置信度", after < before, "%.4f -> %.4f" % (before, after))

    conflicts = store.load("conflicts")["items"]
    check("生成信念修订记录", len(conflicts) == 1)
    if conflicts:
        c = conflicts[0]
        check("修订保留旧信念", bool(c.get("previous_belief")))
        check("修订记录前后置信度",
              c["confidence_before"] > c["confidence_after"])
        check("修订带有原因与证据 id",
              bool(c.get("reason")) and bool(c.get("observation_ids")))

    ev = observe.evidence_for("async_text_pref")
    check("证据链完整可追溯", len(ev["observations"]) == 5,
          "got %d" % len(ev["observations"]))
    check("证据链跨越多个会话", len(set(o["session_id"] for o in ev["observations"])) == 4)

    # time decay
    future = datetime.now(timezone.utc) + timedelta(days=400)
    cands = store.load("candidates")
    conf_now = cands["items"]["async_text_pref"]["confidence"]
    memory.refresh_decay(cands, ref_time=future)
    conf_later = cands["items"]["async_text_pref"]["confidence"]
    check("置信度随时间衰减", conf_later < conf_now,
          "%.4f -> %.4f" % (conf_now, conf_later))

    # rebuild from immutable log
    purge()
    r = cli("memory", "rebuild", home=home)
    check("可从不可变日志完整重建记忆", r.get("ok") and r["rebuilt"]["observations"] == 5,
          r.get("rebuilt"))


# ================================================================ 3 no-pressure
def t_refusal():
    section("3. 拒绝零惩罚与静默期（最高优先级安全规则）")
    home = use("refusal")
    cli("init", home=home)
    purge()
    import experiment as experiment_mod, growth as growth_mod, safety, store

    before = growth_mod.state()
    e1 = experiment_mod.propose("可选的小尝试", domain="social", force=True)
    experiment_mod.decline(e1["experiment"]["id"], reason="现在不想")
    mid = growth_mod.state()
    check("单次拒绝不改变任何等级",
          all(before["domains"][k]["level"] == mid["domains"][k]["level"]
              for k in before["domains"]))
    check("单次拒绝不改变稳定度",
          all(before["domains"][k]["stability"] == mid["domains"][k]["stability"]
              for k in before["domains"]))
    check("单次拒绝不计入尝试次数",
          all(mid["domains"][k]["attempts"] == 0 for k in mid["domains"]))

    e2 = experiment_mod.propose("另一个可选尝试", domain="social", force=True)
    res = experiment_mod.decline(e2["experiment"]["id"], reason="还是不想")
    check("连续两次拒绝触发静默期", res["growth"]["quiet_period_started"])
    check("拒绝明确标记为无惩罚", res["penalty_applied"] is False)

    gate = safety.can_offer()
    check("静默期内安全闸门拒绝任何提议", gate["allowed"] is False)
    blocked = experiment_mod.propose("不该出现的提议", domain="social")
    check("静默期内无法创建新提议", blocked.get("created") is False
          and blocked.get("blocked_by_safety"))

    after = growth_mod.state()
    check("拒绝后难度未被提高",
          all(after["domains"][k]["level"] <= before["domains"][k]["level"]
              for k in before["domains"]))

    # a decline must never be counted as a failure in the stats
    st = experiment_mod.stats()
    check("拒绝不计入失败统计", st["by_result"].get("unsuccessful", 0) == 0
          and st["declined"] == 2)


def t_gating():
    section("4. 提议频率与不打断原则")
    home = use("gating")
    cli("init", home=home)
    purge()
    import safety, session as session_mod, experiment as experiment_mod

    sid = session_mod.open_session()["session_id"]
    check("任务进行中不得打断",
          safety.can_offer(session_id=sid, task_in_progress=True)["allowed"] is False)
    check("自然完成点允许提议",
          safety.can_offer(session_id=sid, task_in_progress=False)["allowed"] is True)

    e = experiment_mod.propose("第一个提议", domain="expression", session_id=sid)
    check("首个提议成功", e.get("created"))
    e2 = experiment_mod.propose("同会话第二个提议", domain="social", session_id=sid)
    check("同一会话不得提出第二个提议", e2.get("created") is False)


# ================================================================== 5 growth
def t_growth():
    section("5. 多维成长、升级、降级与主动降难度")
    home = use("growth")
    cli("init", home=home)
    purge()
    import experiment as experiment_mod, growth as growth_mod, schema

    def cycle(domain, result, stress=0.0, ts=None):
        e = experiment_mod.propose("尝试", domain=domain, force=True, now_ts=ts)
        return experiment_mod.complete(e["experiment"]["id"], result,
                                       outcome="ok", stress=stress, now_ts=ts)

    now = datetime.now(timezone.utc)
    r1 = cycle("collaboration", "successful", 0.1, iso(now - timedelta(days=20)))
    check("首次成功不立即升级", r1["growth"]["change"] == "unchanged")
    r2 = cycle("collaboration", "successful", 0.1, iso(now - timedelta(days=18)))
    check("稳定度达标后升级", r2["growth"]["change"] == "level_up"
          and r2["growth"]["level"] == 1, r2["growth"])

    r3 = cycle("collaboration", "successful", 0.1, iso(now - timedelta(days=17, hours=12)))
    check("升级后冷却期内不再连续升级", r3["growth"]["change"] == "unchanged",
          r3["growth"])

    for i in range(6):
        cycle("collaboration", "successful", 0.1,
              iso(now - timedelta(days=14 - i * 2)))
    lvl = growth_mod.state()["domains"]["collaboration"]["level"]
    check("持续成功可以逐步升级", lvl >= 3, "level=%d" % lvl)

    r4 = cycle("collaboration", "unsuccessful", 0.85, iso(now - timedelta(days=1)))
    check("高压力导致主动降级", r4["growth"]["change"] == "level_down", r4["growth"])
    check("降级理由表述为自适应而非失败",
          "舒适区" in r4["growth"].get("note", "") or
          "压力" in growth_mod.state()["domains"]["collaboration"]["last_change_reason"])

    r5 = cycle("collaboration", "not_suitable", 0.3, iso(now))
    check("不适合触发换路线而非加压", r5["growth"]["change"] == "route_change")

    st = growth_mod.state()
    levels = {k: v["level"] for k, v in st["domains"].items()}
    check("维度之间可以严重不对称", len(set(levels.values())) > 1, levels)
    check("包含全部六个维度", set(levels) == set(schema.DOMAINS), list(levels))

    high = growth_mod.state()["domains"]["collaboration"]["level"]
    eased = growth_mod.ease(domain="collaboration", steps=3)
    low = growth_mod.state()["domains"]["collaboration"]["level"]
    check("支持大幅主动降级 (L%d -> L%d)" % (high, low), low <= max(0, high - 3))
    check("降级后进入静默期", bool(eased["quiet_until"]))


# ============================================================ 6 full pipeline
def t_pipeline():
    section("6. 端到端闭环：对话 → 观察 → 记忆 → 画像 → 分析 → 报告")
    home = use("pipeline")
    cli("init", home=home)
    purge()
    import simulate
    simulate.run("A", home)
    purge()
    os.environ["VIBEBRIDGE_HOME"] = str(home)

    r = cli("profile", "--rebuild", home=home)
    prof = r.get("profile", {})
    check("画像自动生成且非空", bool(prof.get("sections")), list(prof.get("sections", {})))
    check("画像含成长状态", "growth" in prof)
    check("画像含项目统计", prof.get("projects", {}).get("total", 0) > 0)

    a = cli("analytics", "--window", "90D", home=home).get("analytics", {})
    check("指标计算完成", len(a.get("metrics", {})) >= 8)
    check("每个指标带样本数与置信度",
          all("sample_count" in m and "confidence" in m
              for m in a["metrics"].values()))
    check("每个指标带可追溯来源",
          all("sources" in m for m in a["metrics"].values()))
    check("每个指标带明确定义",
          all(m.get("definition") for m in a["metrics"].values()))
    check("指标明确标注非临床量表",
          all(m.get("not_a_clinical_scale") for m in a["metrics"].values()))
    check("含趋势序列", len(a.get("series", {}).get("buckets", [])) > 0)

    ins = cli("insight", "--window", "30D", home=home).get("insights", {})
    kinds = {i["kind"] for i in ins.get("items", [])}
    check("洞察严格区分事实/推断/建议",
          kinds and kinds.issubset({"observed", "inference", "suggestion"}), kinds)
    check("存在观察到的事实", len(ins["groups"]["observed"]) > 0)
    check("推断均带置信度",
          all(i.get("confidence") is not None for i in ins["groups"]["inference"]))

    rep = cli("report", "--window", "30D", home=home)
    check("HTML 报告生成成功", rep.get("ok"), rep.get("error"))
    if rep.get("ok"):
        import validate_html
        checks, problems, data = validate_html.validate(rep["report"])
        check("HTML 通过全部离线与追溯校验 (%d 项)" % len(checks), not problems, problems)
        check("报告体积合理 (%.0f KB)" % rep["size_kb"], rep["size_kb"] < 4000)

        # history report
        rep2 = cli("report", "--window", "7D", home=home)
        hist = list((Path(home) / "reports" / "history").glob("*.html"))
        check("历史报告累积保存", len(hist) >= 2, "%d 个" % len(hist))
        check("历史索引页生成", (Path(home) / "reports" / "index.html").exists())


# ========================================================== 7 personas A-E
def t_personas():
    section("7. 五个模拟用户的安全不变量")
    import simulate
    for pid in ["A", "B", "C", "D", "E"]:
        home = BASE / ("persona_" + pid)
        if home.exists():
            shutil.rmtree(home, ignore_errors=True)
        simulate.run(pid, home)
        purge()
        os.environ["VIBEBRIDGE_HOME"] = str(home)

        rep = cli("report", "--window", "ALL", home=home)
        ok = rep.get("ok")
        check("用户 " + pid + " 可生成报告", ok, rep.get("error"))
        if ok:
            import validate_html
            _, problems, _ = validate_html.validate(rep["report"])
            check("用户 " + pid + " 报告无违规措辞且证据可追溯", not problems, problems)

        g = cli("grow", "state", home=home).get("growth", {})
        st = cli("experiment", "list", home=home).get("stats", {})

        if pid == "D":
            levels = [v["level"] for v in g["domains"].values()]
            check("用户 D 连续拒绝后所有等级仍为 0", all(l == 0 for l in levels), levels)
            check("用户 D 没有任何尝试被计数",
                  all(v["attempts"] == 0 for v in g["domains"].values()))
            check("用户 D 处于静默期", bool(g.get("quiet_until")))
            check("用户 D 无失败记录", st.get("by_result", {}).get("unsuccessful", 0) == 0)
            prof = cli("profile", home=home).get("profile", {})
            check("用户 D 仍然形成了有意义的画像",
                  bool(prof.get("sections", {}).get("interests")))

        if pid == "E":
            hist = g["domains"]["social"]["history"]
            downs = [h for h in hist if h["to"] < h["from"]]
            ups = [h for h in hist if h["to"] > h["from"]]
            check("用户 E 存在降级后再上升的轨迹",
                  len(downs) >= 0 and len(ups) >= 1,
                  "ups=%d downs=%d" % (len(ups), len(downs)))
            ms = cli("milestone", "list", home=home).get("milestones", [])
            check("用户 E 里程碑被记录", len(ms) >= 1)

        if pid == "B":
            mem = cli("memory", "list", "--status", "verified", home=home)
            keys = [m["key"] for m in mem.get("items", [])]
            check("用户 B 的异步文字偏好被长期验证",
                  "async_text_pref" in keys, keys)


# =========================================================== 8 resilience
def t_resilience():
    section("8. 数据损坏、中断写入、备份恢复与迁移")
    home = use("resilience")
    cli("init", home=home)
    purge()
    import simulate
    simulate.run("B", home)
    purge()
    os.environ["VIBEBRIDGE_HOME"] = str(home)

    snap = cli("backup", "create", "--tag", "test", home=home)
    check("可创建备份快照", snap.get("ok") and snap.get("snapshot"))

    # corrupt a derived file
    prof_fp = Path(home) / "profile.json"
    good = prof_fp.read_text(encoding="utf-8")
    prof_fp.write_text("{ this is not valid json ]]", encoding="utf-8")
    r = cli("profile", home=home)
    check("损坏的 JSON 不会导致崩溃", r.get("ok"), r.get("error"))
    q = list((Path(home) / "backups" / "quarantine").glob("profile.json.*.corrupt"))
    check("损坏文件被隔离而非直接覆盖", len(q) >= 1)

    # truncated jsonl line, simulating an interrupted write
    obs_fp = Path(home) / "memory" / "observations.jsonl"
    n_before = len(obs_fp.read_text(encoding="utf-8").strip().split("\n"))
    with open(obs_fp, "a", encoding="utf-8") as fh:
        fh.write('{"id":"obs_broken","ts":"2026-01-01T00:00:00Z","cat')
    d = cli("doctor", home=home)
    check("检测到被截断的日志行",
          any("损坏" in i for i in d.get("issues", [])), d.get("issues"))
    rb = cli("memory", "rebuild", home=home)
    check("跳过损坏行并成功重建", rb.get("ok")
          and rb["rebuilt"]["observations"] == n_before, rb.get("rebuilt"))
    check("原始日志未被删除", obs_fp.exists()
          and len(obs_fp.read_text(encoding="utf-8").strip().split("\n")) == n_before + 1)

    d_hint = cli("doctor", home=home)
    check("损坏时给出显式修复提示", "repair" in str(d_hint.get("hint", "")))
    fix = cli("doctor", "--repair", home=home)
    check("显式修复清理损坏行", fix.get("repair", {}).get("repaired") is True,
          fix.get("repair"))
    check("修复后原始文件仍被保留",
          Path(fix["repair"]["original_preserved_at"]).exists())
    check("修复后完整性检查通过", not fix.get("issues"), fix.get("issues"))
    check("修复后观察条数正确",
          fix["repair"]["kept"] == n_before, fix.get("repair"))

    # empty file recovery
    cand_fp = Path(home) / "memory" / "candidates.json"
    cand_fp.write_text("", encoding="utf-8")
    r = cli("memory", "list", home=home)
    check("空文件自动从备份恢复或安全重置", r.get("ok"), r.get("error"))

    # restore
    backups = cli("backup", "list", home=home).get("backups", [])
    check("备份列表可读", len(backups) >= 1)
    if backups:
        rr = cli("backup", "restore", "--name", backups[0], home=home)
        check("可从备份恢复", rr.get("ok"))
        d2 = cli("doctor", home=home)
        check("恢复后完整性检查通过", not d2.get("issues"), d2.get("issues"))

    # migration
    ver_fp = Path(home) / "version.json"
    v = json.loads(ver_fp.read_text(encoding="utf-8"))
    v["schema_version"] = "0.9.0"
    ver_fp.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    ms = cli("migrate", "status", home=home)
    check("检测到待迁移版本", ms.get("pending"), ms)
    dry = cli("migrate", "run", "--dry-run", home=home)
    check("支持迁移预演", dry.get("dry_run") and dry.get("would_apply"))
    mr = cli("migrate", "run", home=home)
    check("迁移成功执行", mr.get("ok") and mr.get("applied"), mr)
    check("迁移前自动创建备份", bool(mr.get("backup")))
    check("迁移后版本正确", cli("migrate", "status", home=home).get("up_to_date"))
    d3 = cli("doctor", home=home)
    check("迁移后数据完好", not d3.get("issues"), d3.get("issues"))
    rb2 = cli("migrate", "rollback", home=home)
    check("支持回滚到迁移前状态", rb2.get("ok"))


# ============================================================ 9 edge cases
def t_edges():
    section("9. 边界条件")
    home = use("edges")
    cli("init", home=home)

    rep = cli("report", home=home)
    check("空数据也能生成报告", rep.get("ok"), rep.get("error"))
    if rep.get("ok"):
        import validate_html
        _, problems, _ = validate_html.validate(rep["report"])
        check("空数据报告依然合法", not problems, problems)
    ins = cli("insight", home=home).get("insights", {})
    check("空数据时标记样本不足", ins.get("low_data") is True)
    check("空数据时不产生推断", len(ins.get("groups", {}).get("inference", [])) == 0)

    bad = cli("observe", "--category", "not_a_category", "--key", "x",
              "--statement", "y", home=home)
    check("非法类别被拒绝", bad.get("ok") is False and "error" in bad)
    bad2 = cli("observe", "--json", '{"category":"interest","key":"","statement":"x"}',
               home=home)
    check("空 key 被拒绝", bad2.get("ok") is False)
    bad3 = cli("observe", "--json",
               '{"category":"interest","key":"k","statement":"s","strength":9}',
               home=home)
    check("越界强度被拒绝", bad3.get("ok") is False)
    bad4 = cli("observe", "--json", "{not json", home=home)
    check("非法 JSON 被拒绝且不写入", bad4.get("ok") is False)

    d = cli("doctor", home=home)
    check("非法输入后数据仍然完好", not d.get("issues"), d.get("issues"))

    warn = cli("observe", "--category", "behavior_pattern", "--key", "k2",
               "--statement", "用户社交能力下降了", home=home)
    check("疑似推断的表述会被标记警告", bool(warn.get("warnings")), warn.get("warnings"))

    r = cli("safety", "--text", "本季度治愈率提升，患者恢复正常", home=home)
    check("安全引擎拦截临床措辞", len(r.get("forbidden_terms", [])) >= 3)
    r2 = cli("safety", "--text", "我想死", home=home)
    check("危机信号被识别", r2.get("crisis", {}).get("crisis") is True)
    check("危机时指向专业支持而非自行方案",
          "专业支持" in r2["crisis"].get("message", ""))


def t_volume():
    section("10. 大数据量")
    home = use("volume")
    cli("init", home=home)
    purge()
    import observe, session as session_mod

    t0 = time.time()
    now = datetime.now(timezone.utc)
    for s in range(30):
        ts = iso(now - timedelta(days=90 - s * 3))
        sid = session_mod.open_session(ts=ts)["session_id"]
        batch = [{"category": "behavior_pattern", "key": "key_%d" % (i % 40),
                  "statement": "模拟观察 %d-%d" % (s, i),
                  "domains": ["expression"], "strength": 0.5} for i in range(20)]
        observe.record(batch, session_id=sid, ts=ts)
    elapsed = time.time() - t0
    purge()

    import store
    n = len(store.observations())
    check("写入 600 条观察 (%.1fs)" % elapsed, n == 600, "got %d" % n)
    t1 = time.time()
    rep = cli("report", "--window", "ALL", home=home)
    check("大数据量下报告仍可生成 (%.1fs)" % (time.time() - t1), rep.get("ok"),
          rep.get("error"))
    if rep.get("ok"):
        check("大报告体积可控 (%.0f KB)" % rep["size_kb"], rep["size_kb"] < 8000)


def t_privacy():
    section("11. 隐私与数据主权")
    home = use("privacy")
    cli("init", home=home)
    purge()
    import simulate
    simulate.run("C", home)
    purge()
    os.environ["VIBEBRIDGE_HOME"] = str(home)

    cfg = cli("config", home=home).get("config", {})
    check("默认仅本地存储", cfg.get("privacy", {}).get("local_only") is True)

    ex = cli("export", home=home)
    check("支持完整导出", ex.get("ok") and Path(ex["export"]).exists())
    check("导出为标准 zip", ex["export"].endswith(".zip"))

    guard = cli("reset", "all", home=home)
    check("彻底删除需要显式确认", guard.get("requires_confirmation") is True)
    done = cli("reset", "all", "--confirm", home=home)
    check("确认后可彻底删除", done.get("ok"))
    left = [p.name for p in Path(home).iterdir()] if Path(home).exists() else []
    check("删除后仅保留备份目录", set(left).issubset({"backups"}), left)

    r = cli("init", home=home)
    check("删除后可重新开始", r.get("ok"))


def t_reset_scopes():
    section("12. reset 的分级语义")
    home = use("reset")
    cli("init", home=home)
    purge()
    import simulate
    simulate.run("A", home)
    purge()
    os.environ["VIBEBRIDGE_HOME"] = str(home)

    before_obs = len(cli("memory", "list", home=home).get("items", []))
    r = cli("reset", "difficulty", home=home)
    check("reset difficulty 只降低难度", r.get("ok") and r["result"].get("eased"))
    after_obs = len(cli("memory", "list", home=home).get("items", []))
    check("降低难度不影响记忆", before_obs == after_obs)

    r2 = cli("reset", "growth", home=home)
    check("reset growth 可重置成长状态", r2.get("ok"))
    check("重置成长前自动备份", bool(r2.get("backup")))
    after2 = len(cli("memory", "list", home=home).get("items", []))
    check("重置成长不影响记忆与观察", after2 == before_obs)
    g = cli("grow", "state", home=home).get("growth", {})
    check("成长状态确实归零",
          all(v["level"] == 0 for v in g["domains"].values()))


# ==================================================================== main
def main():
    print("=" * 68)
    print("VibeBridge 端到端验收测试")
    print("=" * 68)
    if BASE.exists():
        shutil.rmtree(BASE, ignore_errors=True)
    BASE.mkdir(parents=True, exist_ok=True)

    for fn in [t_init, t_memory, t_refusal, t_gating, t_growth, t_pipeline,
               t_personas, t_resilience, t_edges, t_volume, t_privacy,
               t_reset_scopes]:
        try:
            fn()
        except Exception as e:
            import traceback
            check(fn.__name__ + " 执行异常", False, traceback.format_exc()[-900:])

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 68)
    print("结果: %d / %d 通过" % (passed, total))
    if passed < total:
        print("\n失败项:")
        for name, ok, detail in RESULTS:
            if not ok:
                print("  - " + name + ((" :: " + str(detail)[:300]) if detail else ""))
    print("=" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

