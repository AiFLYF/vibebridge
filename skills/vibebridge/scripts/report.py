"""Report engine.

Produces one self contained HTML file. No server, no CDN, no network access,
no external fonts. All data is embedded, so the file keeps working years later
and can be opened from a USB stick with the machine offline.

Every string that reaches the page is run through the safety linter first.
"""
import json
import shutil
import webbrowser
from datetime import datetime, timezone

import analytics
import experiment as experiment_mod
import insight as insight_mod
import paths
import profile as profile_mod
import project as project_mod
import safety
import schema
import session as session_mod
import store

WINDOWS = ["7D", "30D", "90D", "6M", "ALL"]

DISCLAIMER = ("本报告基于用户与系统交互过程中产生的行为数据，"
              "仅用于长期自我观察、个性化支持和成长复盘，"
              "不构成医学诊断、临床评估或治愈程度判断。")


def _template_path():
    return paths.skill_root() / "assets" / "dashboard.html"


def _compact_observations(limit=4000):
    """Evidence index: enough to show provenance, trimmed to keep the file small."""
    recs = store.observations()[-limit:]
    out = {}
    for r in recs:
        out[r["id"]] = {
            "ts": r.get("ts"), "session": r.get("session_id"),
            "category": r.get("category"), "key": r.get("key"),
            "statement": r.get("statement"), "polarity": r.get("polarity"),
            "strength": r.get("strength"), "domains": r.get("domains", []),
            "project": r.get("project_id"), "excerpt": r.get("excerpt", ""),
        }
    return out


def collect(window="30D", now=None):
    now = now or datetime.now(timezone.utc)
    profile_mod.rebuild()

    windows = {}
    for w in WINDOWS:
        try:
            windows[w] = analytics.compute(w, now=now, persist=(w == window))
        except (ValueError, KeyError, TypeError) as e:
            store.log_event("REPORT_WINDOW_FAIL", w + ": " + str(e))
            windows[w] = {"window": w, "error": str(e), "metrics": {},
                          "behavior": {}, "series": {"buckets": [], "metrics": {}}}

    insights = {}
    for w in ("7D", "30D", "90D"):
        try:
            insights[w] = insight_mod.generate(window=w, now=now)
        except (ValueError, KeyError, TypeError) as e:
            store.log_event("REPORT_INSIGHT_FAIL", w + ": " + str(e))
            insights[w] = {"window": w, "groups": {"observed": [], "inference": [],
                                                   "suggestion": []},
                           "items": [], "low_data": True, "error": str(e)}

    cands = store.load("candidates").get("items", {})
    payload = {
        "meta": {
            "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "default_window": window,
            "schema_version": schema.SCHEMA_VERSION,
            "skill_version": schema.SKILL_VERSION,
            "disclaimer": DISCLAIMER,
            "windows": WINDOWS,
            "domain_labels": schema.DOMAIN_LABELS,
            "ladders": schema.LADDERS,
        },
        "windows": windows,
        "insights": insights,
        "profile": store.load("profile"),
        "strategies": store.load("strategies"),
        "memory": {"items": cands},
        "conflicts": store.load("conflicts").get("items", []),
        "observations": _compact_observations(),
        "projects": project_mod.listing(),
        "project_timeline": project_mod.timeline(),
        "experiments": experiment_mod.listing(),
        "experiment_fit": experiment_mod.what_works(),
        "milestones": store.load("milestones").get("items", []),
        "sessions": session_mod.listing(limit=200),
        "growth": windows.get(window, {}).get("growth", {}),
    }
    _safety_scan(payload)
    return payload


def _safety_scan(payload):
    """Fail loudly rather than publish clinical framing into a report."""
    blob = json.dumps(payload, ensure_ascii=False)
    hits = safety.lint(blob)
    ignorable = {"diagnosis", "diagnose"}
    hard = [h for h in hits if h.lower() not in ignorable]
    if hard:
        store.log_event("REPORT_SAFETY", "terms=" + ", ".join(hard))
        raise ValueError("报告内容含有禁用措辞，已阻止生成: " + ", ".join(hard))


def render(payload):
    tpl_path = _template_path()
    if not tpl_path.exists():
        raise FileNotFoundError("缺少模板: " + str(tpl_path))
    tpl = tpl_path.read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")
    return tpl.replace("__VIBEBRIDGE_DATA__", data)


def build(window="30D", now=None, open_after=False):
    now = now or datetime.now(timezone.utc)
    payload = collect(window=window, now=now)
    html = render(payload)

    reports = paths.d("reports")
    history = reports / "history"
    reports.mkdir(parents=True, exist_ok=True)
    history.mkdir(parents=True, exist_ok=True)

    stamp = now.strftime("%Y-%m-%d")
    hist_fp = history / (stamp + ".html")
    if hist_fp.exists():
        hist_fp = history / (now.strftime("%Y-%m-%d_%H%M%S") + ".html")
    store.atomic_write_text(hist_fp, html)

    latest = reports / "latest.html"
    store.atomic_write_text(latest, html)

    index = _write_history_index(history, reports)
    store.log_event("REPORT", str(latest))

    result = {
        "report": str(latest),
        "history_entry": str(hist_fp),
        "history_index": str(index),
        "size_kb": round(len(html.encode("utf-8")) / 1024, 1),
        "window": window,
        "observation_count": payload["windows"][window].get("observation_count", 0),
        "offline": True,
        "disclaimer": DISCLAIMER,
    }
    if open_after:
        try:
            webbrowser.open(latest.as_uri())
            result["opened"] = True
        except (OSError, ValueError):
            result["opened"] = False
    return result


def _write_history_index(history, reports):
    entries = sorted([p.name for p in history.glob("*.html")], reverse=True)
    rows = "\n".join(
        '    <li><a href="history/' + n + '">' + n.replace(".html", "") + "</a></li>"
        for n in entries)
    html = ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>VibeBridge 历史报告</title>"
            "<style>body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;"
            "background:#faf9f7;color:#2f2c28;max-width:640px;margin:64px auto;"
            "padding:0 24px;line-height:1.8}h1{font-weight:600;font-size:20px}"
            "a{color:#5b7c68;text-decoration:none}a:hover{text-decoration:underline}"
            "li{list-style:none;padding:6px 0;border-bottom:1px solid #ece9e4}"
            "ul{padding:0}</style></head><body>"
            "<h1>历史报告</h1><p><a href=\"latest.html\">最新报告</a></p><ul>\n"
            + rows + "\n</ul></body></html>")
    fp = reports / "index.html"
    store.atomic_write_text(fp, html)
    return fp

