#!/usr/bin/env python3
"""Build the shipped demo dataset.

The example user is entirely fictional. No real person's data is ever used in
this repository. Running this script regenerates examples/example_user from
scratch plus a ready to open demo report.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tests"))

OUT = ROOT / "examples" / "example_user"
DEMO_REPORT = ROOT / "examples" / "demo_report.html"


def main():
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)

    import simulate
    simulate.run("A", OUT, verbose=True)

    env = dict(os.environ)
    env["VIBEBRIDGE_HOME"] = str(OUT)
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run([sys.executable, str(ROOT / "core" / "vb.py"),
                    "report", "--window", "30D"],
                   check=True, capture_output=True, env=env)

    latest = OUT / "reports" / "latest.html"
    shutil.copy2(latest, DEMO_REPORT)

    # backups and exports are noise in a repo
    for junk in ("backups", "exports"):
        shutil.rmtree(OUT / junk, ignore_errors=True)

    readme = OUT / "README.md"
    readme.write_text(
        "# 示例数据集\n\n"
        "这是一个**完全虚构**的用户，模拟了大约 8 周的自然使用。\n"
        "本仓库不包含任何真实个人数据。\n\n"
        "## 如何查看\n\n"
        "直接打开 `../demo_report.html`，或者：\n\n"
        "```bash\n"
        "export VIBEBRIDGE_HOME=$(pwd)/examples/example_user\n"
        "python core/vb.py report --open\n"
        "```\n\n"
        "Windows PowerShell：\n\n"
        "```powershell\n"
        "$env:VIBEBRIDGE_HOME = \"$PWD\\examples\\example_user\"\n"
        "python core\\vb.py report --open\n"
        "```\n\n"
        "## 重新生成\n\n"
        "```bash\n"
        "python scripts/build_examples.py\n"
        "```\n",
        encoding="utf-8")

    size = DEMO_REPORT.stat().st_size / 1024
    print("\n示例数据集: " + str(OUT))
    print("Demo 报告  : %s (%.0f KB)" % (DEMO_REPORT, size))


if __name__ == "__main__":
    main()

