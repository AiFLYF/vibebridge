---
description: VibeBridge 数据完整性与安全自检
allowed-tools: Bash(python:*)
---
```bash
python "$HOME/.claude/skills/vibebridge/core/vb.py" doctor
```

如果报告有损坏的日志行，提示可以用 doctor --repair 显式修复
（原始文件会保留在 quarantine 目录，不会丢失）。
