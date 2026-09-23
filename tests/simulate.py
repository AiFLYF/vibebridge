#!/usr/bin/env python3
"""Simulate several weeks of natural usage for five very different people.

All personas are fictional. No real user data is used anywhere in this repo.

The point is not to prove the numbers go up. It is to prove the system never
pushes, never punishes a refusal, and never manufactures progress.
"""
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "skills" / "vibebridge" / "scripts"
sys.path.insert(0, str(CORE))


def fresh(home):
    if os.path.exists(home):
        shutil.rmtree(home, ignore_errors=True)
    os.environ["VIBEBRIDGE_HOME"] = str(home)
    for m in list(sys.modules):
        if m in ("paths", "store", "schema", "memory", "observe", "session",
                 "project", "experiment", "growth", "safety", "profile",
                 "analytics", "insight", "report", "migrate", "vb"):
            del sys.modules[m]
    import contextlib
    import io as _io
    import vb
    sys.argv = ["vb", "init"]
    with contextlib.redirect_stdout(_io.StringIO()):
        try:
            vb.cmd_init(type("A", (), {})())
        except SystemExit:
            pass


def iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- personas
PERSONAS = {
    "A": {
        "name": "偏技术、享受创造的人",
        "weeks": 8, "sessions_per_week": 4,
        "projects": [("音乐可视化网页", ["html", "js", "canvas"]),
                     ("个人作品集站点", ["html", "css"]),
                     ("ESP32 温湿度记录器", ["c", "esp-idf"])],
        "observations": [
            ("interest", "audio_visual_creation", "用户主动提出想做音乐可视化效果", ["expression"], 0.8),
            ("strength", "debugging_persistence", "用户独立定位并修复了一个渲染问题", ["independence"], 0.7),
            ("interest", "hardware_projects", "用户对硬件与传感器项目表现出持续兴趣", ["expression"], 0.7),
            ("behavior_pattern", "iterates_until_satisfied", "用户会反复调整细节直到满意", ["independence"], 0.6),
            ("communication_preference", "concrete_questions", "用户对具体、分步的问题回应更充分", ["communication"], 0.6),
        ],
        "experiments": [("expression", "successful", 0.15), ("expression", "successful", 0.2),
                        ("social", "partial", 0.35), ("social", "successful", 0.25),
                        ("independence", "successful", 0.1)],
    },
    "B": {
        "name": "偏好文字、不适应实时交流的人",
        "weeks": 8, "sessions_per_week": 3,
        "projects": [("命令行笔记工具", ["python"]), ("静态博客生成器", ["python", "jinja"])],
        "observations": [
            ("communication_preference", "async_text_pref", "用户提到不太喜欢突然的语音或电话", ["communication"], 0.7),
            ("communication_preference", "async_text_pref", "用户希望把讨论改成文字形式", ["communication"], 0.7),
            ("potential_stressor", "realtime_pressure", "用户提到需要立刻回应时会感到吃力", ["communication"], 0.6),
            ("support_preference", "advance_notice", "用户希望提前知道流程再开始", ["communication"], 0.6),
            ("self_advocacy", "requests_more_time", "用户主动说明自己需要更多时间", ["self_advocacy"], 0.7),
            ("interest", "tooling_and_automation", "用户偏好做能自己用得上的小工具", ["expression"], 0.7),
        ],
        "experiments": [("communication", "successful", 0.2), ("communication", "successful", 0.25),
                        ("social", "not_suitable", 0.5), ("self_advocacy", "successful", 0.2)],
    },
    "C": {
        "name": "行为节奏不稳定的人",
        "weeks": 10, "sessions_per_week": 2,
        "projects": [("像素画编辑器", ["js"]), ("待办清单", ["python"]), ("聊天机器人", ["python"])],
        "observations": [
            ("engagement_pattern", "bursty_activity", "用户的活跃时间集中在少数几天", ["expression"], 0.6),
            ("behavior_pattern", "starts_many_projects", "用户同时开启多个项目", ["independence"], 0.6),
            ("potential_stressor", "long_task_fatigue", "用户在长任务中途表示需要休息", ["expression"], 0.5),
            ("behavior_pattern", "resume_after_pause", "用户在停顿数天后重新回到项目", ["independence"], 0.6),
            ("interest", "visual_tools", "用户对可视化编辑类工具有兴趣", ["expression"], 0.6),
        ],
        "experiments": [("expression", "partial", 0.4), ("expression", "unsuccessful", 0.75),
                        ("expression", "successful", 0.2), ("social", "cancelled", 0.0),
                        ("independence", "partial", 0.3)],
    },
    "D": {
        "name": "持续拒绝任何成长实验的人",
        "weeks": 6, "sessions_per_week": 3,
        "projects": [("本地音乐播放器", ["python", "qt"])],
        "observations": [
            ("interest", "music_software", "用户想做一个自己用的音乐播放器", ["expression"], 0.8),
            ("interaction_preference", "prefers_no_suggestions", "用户表示只想专注在功能本身", ["communication"], 0.7),
            ("strength", "clear_requirements", "用户能清楚描述自己想要的功能", ["expression"], 0.7),
            ("behavior_pattern", "focused_single_project", "用户长期只推进一个项目", ["independence"], 0.6),
        ],
        "experiments": [("social", "declined", 0.0), ("social", "declined", 0.0),
                        ("expression", "declined", 0.0), ("communication", "declined", 0.0)],
    },
    "E": {
        "name": "先失败后重新尝试的人",
        "weeks": 9, "sessions_per_week": 3,
        "projects": [("开源小组件库", ["ts", "react"])],
        "observations": [
            ("interest", "ui_components", "用户想做一套自己的界面组件", ["expression"], 0.7),
            ("potential_stressor", "public_exposure", "用户在准备公开发布时表示紧张", ["social"], 0.7),
            ("behavior_pattern", "retry_after_setback", "用户在一次不顺利之后重新尝试", ["independence"], 0.7),
            ("social_experience", "first_public_release", "用户完成了第一次公开发布", ["social"], 0.8),
            ("self_advocacy", "sets_own_pace", "用户说明自己想按自己的节奏来", ["self_advocacy"], 0.7),
        ],
        "experiments": [("social", "unsuccessful", 0.8), ("social", "cancelled", 0.0),
                        ("social", "partial", 0.35), ("social", "successful", 0.2),
                        ("social", "successful", 0.15)],
    },
}


def run(pid, home, verbose=False):
    spec = PERSONAS[pid]
    fresh(home)
    import experiment as experiment_mod
    import growth as growth_mod
    import observe
    import profile as profile_mod
    import project as project_mod
    import session as session_mod
    import store

    now = datetime.now(timezone.utc)
    start = now - timedelta(weeks=spec["weeks"])

    for i, (pname, stack) in enumerate(spec["projects"]):
        project_mod.create(pname, idea="用户自己提出的想法", stack=stack,
                           ts=iso(start + timedelta(days=i * 5 + 1)))

    obs_pool = spec["observations"]
    total_sessions = spec["weeks"] * spec["sessions_per_week"]
    exp_queue = list(spec["experiments"])

    for n in range(total_sessions):
        ts = start + timedelta(days=(n * 7.0) / spec["sessions_per_week"],
                               hours=(n * 3) % 12)
        sid = session_mod.open_session(project=spec["projects"][0][0], ts=iso(ts))["session_id"]

        picks = [obs_pool[(n + j) % len(obs_pool)] for j in range(2)]
        payload = []
        for cat, key, stmt, doms, strength in picks:
            payload.append({"category": cat, "key": key, "statement": stmt,
                            "domains": doms, "strength": strength,
                            "polarity": "support", "ts": iso(ts)})
        observe.record(payload, session_id=sid, ts=iso(ts), ref_time=ts)

        # an opportunity may only appear every few sessions, and only if allowed
        if exp_queue and n % 5 == 4:
            domain, outcome, stress = exp_queue.pop(0)
            if outcome == "declined":
                res = experiment_mod.propose(
                    "一个完全可选的小尝试", domain=domain, difficulty=2,
                    session_id=sid, now_ts=iso(ts), force=True)
                if res.get("created"):
                    experiment_mod.decline(res["experiment"]["id"], reason="现在不想",
                                           session_id=sid, now_ts=iso(ts))
            else:
                res = experiment_mod.propose(
                    "一个完全可选的小尝试", domain=domain, difficulty=2,
                    session_id=sid, now_ts=iso(ts), force=True)
                if res.get("created"):
                    experiment_mod.accept(res["experiment"]["id"])
                    experiment_mod.complete(res["experiment"]["id"], outcome,
                                            outcome="模拟结果", stress=stress,
                                            engagement=0.7, now_ts=iso(ts))

        session_mod.close_session(sid, summary="正常的一次创作会话。", ts=iso(ts))

    # project lifecycle progression, only for personas that got that far
    pl = project_mod.listing()
    if pid in ("A", "E") and pl:
        project_mod.update(pl[0]["id"], stage="completed", completion=1.0,
                           ts=iso(now - timedelta(days=6)), event="completed")
        project_mod.update(pl[0]["id"], stage="published", published=True,
                           ts=iso(now - timedelta(days=4)), event="published")
        project_mod.bump(pl[0]["id"], "feedback_received", 3,
                         ts=iso(now - timedelta(days=3)), event="feedback")
    if pid == "A" and len(pl) > 1:
        project_mod.update(pl[1]["id"], stage="completed", completion=1.0,
                           ts=iso(now - timedelta(days=2)), event="completed")

    if pid == "E":
        data = store.load("milestones")
        data["items"].append({
            "id": "ms_0001", "ts": iso(now - timedelta(days=4)),
            "title": "第一次把作品公开发布", "detail": "在一次不顺利之后重新尝试并完成。",
            "kind": "first_time", "project_id": pl[0]["id"] if pl else None,
            "session_id": None, "evidence": []})
        store.save("milestones", data)

    profile_mod.rebuild()
    g = growth_mod.state()
    if verbose:
        print("  " + pid + " " + spec["name"])
        print("     观察 %d 条 | 记忆 %d 条 | 项目 %d 个 | 实验 %d 个" % (
            len(store.observations()),
            len(store.load("candidates")["items"]),
            len(project_mod.listing()),
            len(experiment_mod.listing())))
    return {"persona": pid, "growth": g}


if __name__ == "__main__":
    base = Path(os.environ.get("TEMP", "/tmp")) / "vb_personas"
    for pid in PERSONAS:
        run(pid, base / pid, verbose=True)

