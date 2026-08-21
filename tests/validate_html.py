#!/usr/bin/env python3
"""Validate a generated report is genuinely self contained and offline safe."""
import json
import re
import sys
from pathlib import Path


def validate(fp):
    html = Path(fp).read_text(encoding="utf-8")
    problems, checks = [], []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))
        if not ok:
            problems.append(name + (" -> " + detail if detail else ""))

    check("模板占位符已替换", "__VIBEBRIDGE_DATA__" not in html)
    check("有 DOCTYPE", html.lstrip().lower().startswith("<!doctype html"))
    check("声明 UTF-8", 'charset="utf-8"' in html.lower())

    remote = re.findall(r'(?:src|href)\s*=\s*["\'](https?://|//)[^"\']*', html)
    check("无外部资源引用", not remote, str(remote[:3]))
    for bad in ("fetch(", "XMLHttpRequest", "WebSocket(", "importScripts",
                "cdn.", "googleapis", "unpkg", "jsdelivr"):
        check("不含网络调用 " + bad, bad not in html)

    m = re.search(r"const DATA = (\{.*?\});\n", html, re.DOTALL)
    check("找到内嵌数据", bool(m))
    if not m:
        return checks, problems, None

    raw = m.group(1).replace("<\\/", "</")
    try:
        data = json.loads(raw)
        check("内嵌 JSON 可解析", True)
    except json.JSONDecodeError as e:
        check("内嵌 JSON 可解析", False, str(e))
        return checks, problems, None

    for key in ("meta", "windows", "insights", "profile", "memory",
                "observations", "projects", "experiments", "growth",
                "strategies", "conflicts", "milestones"):
        check("数据含 " + key, key in data)

    check("含全部时间窗口",
          all(w in data["windows"] for w in ["7D", "30D", "90D", "6M", "ALL"]),
          str(list(data["windows"].keys())))
    check("有免责声明", "不构成医学诊断" in data["meta"].get("disclaimer", ""))

    # every insight evidence id must resolve to a real observation
    dangling = []
    for w, ins in data["insights"].items():
        for it in ins.get("items", []):
            for ev in it.get("evidence", []):
                if ev not in data["observations"]:
                    dangling.append(ev)
    check("洞察证据可追溯", not dangling, str(sorted(set(dangling))[:5]))

    # every memory evidence id must resolve as well
    dangling_m = []
    for k, mem in data["memory"]["items"].items():
        for ev in (mem.get("evidence", []) + mem.get("contradict_evidence", [])):
            if ev not in data["observations"]:
                dangling_m.append(ev)
    check("记忆证据可追溯", not dangling_m, str(sorted(set(dangling_m))[:5]))

    # every insight item must be tagged with exactly one kind
    kinds = set()
    for w, ins in data["insights"].items():
        for it in ins.get("items", []):
            kinds.add(it.get("kind"))
    check("洞察严格分类", kinds.issubset({"observed", "inference", "suggestion"}),
          str(kinds))

    banned = ["治愈率", "康复率", "严重程度", "恢复正常", "患者", "病情"]
    body = html
    for phrase in ["不构成医学诊断、临床评估或治愈程度判断",
                   "不构成医学诊断、临床评估或任何形式的疗效判断",
                   "不是医学量表，也不代表任何能力评级或治疗效果",
                   "不是医学评估，也不构成任何诊断"]:
        body = body.replace(phrase, " ")
    found = [b for b in banned if b in body]
    check("无临床或治愈类措辞", not found, str(found))

    return checks, problems, data


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "reports/latest.html"
    checks, problems, data = validate(target)
    for name, ok, detail in checks:
        print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail and not ok else ""))
    print()
    if data:
        print("文件大小: %.1f KB" % (Path(target).stat().st_size / 1024))
        print("观察条目: %d" % len(data["observations"]))
        print("记忆条目: %d" % len(data["memory"]["items"]))
    print(("全部通过 (%d 项)" % len(checks)) if not problems
          else ("失败 %d 项: %s" % (len(problems), problems)))
    sys.exit(1 if problems else 0)

