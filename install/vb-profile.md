---
description: 查看 VibeBridge 自动形成的用户画像与交互策略
allowed-tools: Bash(python:*)
---
```bash
python "$HOME/.claude/skills/vibebridge/core/vb.py" profile --rebuild
python "$HOME/.claude/skills/vibebridge/core/vb.py" profile --strategies
```

用平实的语言复述。每条都要带上置信度和证据条数。
明确说明这是行为观察的聚合，不是对这个人的评价或分类。
置信度低于 0.5 的内容要说清楚"证据还很少"。
