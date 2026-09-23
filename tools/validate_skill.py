#!/usr/bin/env python3
"""Validate skill directories against the Agent Skills open standard.

Spec: https://agentskills.io/specification

Usage:
    python tools/validate_skill.py skills/*
    python tools/validate_skill.py .            # single-skill repo root

Zero third party dependencies: PyYAML is used when available, otherwise a
minimal frontmatter reader is used instead.
"""
import re
import sys
from pathlib import Path

ALLOWED = {"name", "description", "license", "compatibility", "metadata",
           "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)


def parse_frontmatter(text):
    """Return (mapping, error). The simple fallback understands the subset of
    YAML that skill frontmatter actually uses: scalars and one nested block."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, "frontmatter 必须从文件第一行 --- 开始，并以单独一行 --- 结束"
    raw = m.group(1)
    try:
        import yaml  # noqa: WPS433 - optional dependency
        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            return None, "frontmatter 必须是键值映射"
        return data, None
    except ImportError:
        pass
    except Exception as exc:  # malformed YAML
        return None, "YAML 解析失败: %s" % exc

    data = {}
    current = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if stripped.endswith(":") and not stripped.startswith("-"):
            # Opens a nested block, e.g. "metadata:"
            key = stripped[:-1].strip()
            parent = data if indent == 0 else data.setdefault(current, {})
            parent[key] = {}
            current = key
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if indent == 0:
            data[key] = value
            current = key
        else:
            if not isinstance(data.get(current), dict):
                data[current] = {}
            data[current][key] = value
    return data, None


def check(skill_dir):
    p = Path(skill_dir)
    f = p / "SKILL.md"
    errs = []
    warns = []

    if not f.is_file():
        return ["%s: 缺少 SKILL.md（文件名必须大写）"], []

    text = f.read_text(encoding="utf-8")
    fm, err = parse_frontmatter(text)
    if err:
        return ["%s: %s" % (f, err)], []

    name = fm.get("name")
    desc = fm.get("description")

    if not isinstance(name, str) or not name:
        errs.append("缺少 name")
    else:
        if len(name) > 64 or not NAME_RE.match(name):
            errs.append("name 不合规（仅小写字母/数字/单个连字符，≤64）: %s" % name)
        if name != p.name:
            errs.append("name（%s）与目录名（%s）不一致" % (name, p.name))

    if not isinstance(desc, str) or not desc.strip():
        errs.append("缺少 description")
    elif len(desc) > 1024:
        errs.append("description 超过 1024 字符（当前 %d）" % len(desc))

    compat = fm.get("compatibility")
    if isinstance(compat, str) and len(compat) > 500:
        errs.append("compatibility 超过 500 字符（当前 %d）" % len(compat))

    extra = set(fm) - ALLOWED
    if extra:
        warns.append("含非标准字段（跨 agent 可能被拒绝）: %s" % sorted(extra))

    body = text[FRONTMATTER_RE.match(text).end():]
    lines = body.count("\n") + 1
    if lines > 500:
        warns.append("SKILL.md 正文 %d 行，超过建议的 500 行，长内容应拆进 references/" % lines)

    # Every relative file reference in SKILL.md should resolve.
    for ref in re.findall(r"`([A-Za-z0-9_./-]+\.(?:md|py|html|json|txt))`", body):
        target = p / ref
        if "/" in ref and not target.exists():
            errs.append("SKILL.md 引用了不存在的文件: %s" % ref)
        if ref.count("/") > 1:
            warns.append("引用层级过深（建议一层）: %s" % ref)

    return ["%s: %s" % (f, e) for e in errs], ["%s: %s" % (f, w) for w in warns]


def main():
    # template/ and spec/ are scaffolding, not installable skills, so the
    # default target is the skills/ directory only. (template/ deliberately
    # ships SKILL.example.md rather than SKILL.md for the same reason.)
    targets = sys.argv[1:] or ["skills"]
    bad = 0
    for d in targets:
        p = Path(d)
        if not (p / "SKILL.md").is_file() and p.is_dir():
            for sub in sorted(p.iterdir()):
                if (sub / "SKILL.md").is_file():
                    errs, warns = check(sub)
                    bad += _report(sub, errs, warns)
            continue
        errs, warns = check(p)
        bad += _report(p, errs, warns)
    print("全部通过" if not bad else "共 %d 个错误" % bad)
    return 1 if bad else 0


def _report(path, errs, warns):
    if not errs and not warns:
        print("OK   %s" % path)
    for w in warns:
        print("WARN %s" % w)
    for e in errs:
        print("FAIL %s" % e)
    return len(errs)


if __name__ == "__main__":
    sys.exit(main())
