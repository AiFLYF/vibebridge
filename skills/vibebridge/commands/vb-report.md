---
description: 生成 VibeBridge 交互式 HTML 成长报告
allowed-tools: Bash(python:*)
---
生成报告。$ARGUMENTS 可以是时间窗口（7D / 30D / 90D / 6M / ALL），默认 30D。

```bash
python "$HOME/.claude/skills/vibebridge/scripts/vb.py" report --window 30D
```

告诉用户报告路径和大小。呈现数字时说明它们来自行为频率而非能力评分，
主动指出样本量小的地方。不要庆祝，也不要表现出担忧。
