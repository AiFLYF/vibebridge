---
description: 查看当前最自然的下一步机会（可能是没有）
allowed-tools: Bash(python:*)
---
```bash
python "$HOME/.claude/skills/vibebridge/scripts/vb.py" grow state
python "$HOME/.claude/skills/vibebridge/scripts/vb.py" grow opportunities
```

**如实转述 gate 状态。** 如果 gate.allowed 为 false，就直接告诉用户
现在什么都不适合提，并说明原因（静默期 / 间隔不足 / 任务进行中）。
不要因为用户主动问了就绕过闸门。

展示六个维度时强调：维度之间不对称是完全正常的状态，不需要拉平。
