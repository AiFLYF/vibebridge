"""Durable, corruption-resistant storage layer.

Guarantees:
  * All writes are atomic (temp file -> fsync -> os.replace).
  * All files are UTF-8, regardless of the Windows console code page.
  * A corrupt JSON file never crashes the system: it is quarantined, then
    recovered from the newest good backup, else reset to schema default.
  * observations.jsonl is append-only. Damaged lines are skipped on read but
    never removed from disk, so raw evidence is never silently destroyed.
"""
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import paths
import schema


def _ensure_parent(fp):
    fp.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_text(fp, text):
    _ensure_parent(fp)
    fd, tmp = tempfile.mkstemp(dir=str(fp.parent), prefix=".tmp_", suffix=".swap")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, fp)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def write_json(fp, data):
    atomic_write_text(fp, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def log_event(kind, detail):
    try:
        fp = paths.d("logs") / "vibebridge.log"
        fp.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        with open(fp, "a", encoding="utf-8") as fh:
            fh.write("[" + stamp + "] " + kind + ": " + detail + "\n")
    except OSError:
        pass


def quarantine(fp, reason):
    """Copy an unreadable file aside instead of overwriting it. Nothing is lost."""
    qdir = paths.d("backups") / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest = qdir / (fp.name + "." + stamp + ".corrupt")
    try:
        shutil.copy2(fp, dest)
    except OSError:
        pass
    log_event("QUARANTINE", str(fp) + " -> " + str(dest) + " (" + reason + ")")
    return dest


def read_json(fp, default_factory=None):
    """Read JSON, self-healing on corruption."""
    if not fp.exists():
        return default_factory() if default_factory else None
    try:
        raw = fp.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        quarantine(fp, "unreadable: " + str(e))
        return default_factory() if default_factory else None
    if not raw.strip():
        quarantine(fp, "empty file")
        return _try_recover_from_backup(fp, default_factory)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        quarantine(fp, "invalid json: " + str(e))
        return _try_recover_from_backup(fp, default_factory)


def _try_recover_from_backup(fp, default_factory):
    """Look for the newest good snapshot of this file before giving up."""
    bdir = paths.d("backups")
    if bdir.exists():
        cands = sorted(bdir.glob("*/" + fp.name), reverse=True)
        for c in cands:
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            log_event("RECOVER", str(fp) + " restored from " + str(c))
            write_json(fp, data)
            return data
    log_event("RESET", str(fp) + " reset to schema default (no usable backup)")
    return default_factory() if default_factory else None


def load(key):
    return read_json(paths.p(key), schema.DEFAULTS.get(key))


def save(key, data):
    if "schema_version" not in data:
        data["schema_version"] = schema.SCHEMA_VERSION
    write_json(paths.p(key), data)


def append_jsonl(fp, obj):
    _ensure_parent(fp)
    with open(fp, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(fp):
    """Return (records, damaged_line_count). Tolerates truncated writes."""
    out, bad = [], 0
    if not fp.exists():
        return out, bad
    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                bad += 1
    if bad:
        log_event("JSONL_SKIP", str(fp) + " skipped " + str(bad) + " damaged line(s)")
    return out, bad


def observations():
    recs, _ = read_jsonl(paths.p("observations"))
    return recs


SNAPSHOT_KEYS = ["version", "config", "profile", "candidates", "verified",
                 "conflicts", "strategies", "sessions", "projects",
                 "experiments", "milestones", "growth", "analytics"]


def snapshot(tag="auto"):
    """Point in time copy of every derived file plus the immutable log."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest = paths.d("backups") / (stamp + "_" + tag)
    dest.mkdir(parents=True, exist_ok=True)
    for k in SNAPSHOT_KEYS:
        src = paths.p(k)
        if src.exists():
            shutil.copy2(src, dest / src.name)
    obs = paths.p("observations")
    if obs.exists():
        shutil.copy2(obs, dest / obs.name)
    log_event("SNAPSHOT", str(dest))
    prune_backups()
    return dest


def prune_backups(keep=20):
    bdir = paths.d("backups")
    if not bdir.exists():
        return
    snaps = sorted([q for q in bdir.iterdir() if q.is_dir() and q.name != "quarantine"])
    for old in snaps[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def list_backups():
    bdir = paths.d("backups")
    if not bdir.exists():
        return []
    return sorted([q.name for q in bdir.iterdir() if q.is_dir() and q.name != "quarantine"])


def restore(snapshot_name):
    src = paths.d("backups") / snapshot_name
    if not src.is_dir():
        return False
    snapshot("pre_restore")
    names = {paths.p(k).name: paths.p(k) for k in SNAPSHOT_KEYS}
    names[paths.p("observations").name] = paths.p("observations")
    for f in src.iterdir():
        target = names.get(f.name)
        if target:
            _ensure_parent(target)
            shutil.copy2(f, target)
    log_event("RESTORE", snapshot_name)
    return True


def compact_observations():
    """Explicit, user initiated repair of a damaged append only log.

    The original file is copied into quarantine first, so the damaged bytes
    remain inspectable forever. Only then is a clean log written containing
    exactly the lines that parse. This is never automatic: silently dropping
    raw evidence is not something the system is allowed to decide on its own.
    """
    fp = paths.p("observations")
    if not fp.exists():
        return {"repaired": False, "reason": "日志文件不存在"}
    recs, bad = read_jsonl(fp)
    if not bad:
        return {"repaired": False, "reason": "没有损坏行，无需修复",
                "kept": len(recs)}
    backup = quarantine(fp, "pre_compact, " + str(bad) + " damaged line(s)")
    snapshot("pre_compact")
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs)
    atomic_write_text(fp, text)
    log_event("COMPACT", "kept=" + str(len(recs)) + " dropped=" + str(bad))
    return {"repaired": True, "kept": len(recs), "dropped": bad,
            "original_preserved_at": str(backup)}


def integrity_check():
    """Report only, never mutate. Used by the doctor command."""
    issues, ok = [], []
    if not paths.home().exists():
        return {"initialized": False, "issues": ["数据目录不存在，请先运行 /init"], "ok": []}
    for k in SNAPSHOT_KEYS:
        fp = paths.p(k)
        if not fp.exists():
            issues.append("缺失文件: " + k)
            continue
        try:
            json.loads(fp.read_text(encoding="utf-8"))
            ok.append(k)
        except (OSError, json.JSONDecodeError) as e:
            issues.append("损坏文件: " + k + " -> " + str(e))
    obs_fp = paths.p("observations")
    if obs_fp.exists():
        recs, bad = read_jsonl(obs_fp)
        ok.append("observations(" + str(len(recs)) + ")")
        if bad:
            issues.append("observations.jsonl 有 " + str(bad) + " 行损坏（已跳过，原文件保留）")
        ids = [r.get("id") for r in recs]
        if len(ids) != len(set(ids)):
            issues.append("observations 存在重复 id")
    else:
        issues.append("缺失 observations.jsonl")
    return {"initialized": True, "issues": issues, "ok": ok}
