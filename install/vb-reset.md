---
description: 降低当前难度，或重置成长状态
allowed-tools: Bash(python:*)
---
默认只降低难度，保留全部记忆：

```bash
python "$HOME/.claude/skills/vibebridge/core/vb.py" reset difficulty
```

如果用户明确说要重置成长状态（记忆仍保留）：

```bash
python "$HOME/.claude/skills/vibebridge/core/vb.py" reset growth
```

只有用户明确表示要删除全部数据时，才提及 reset all --confirm，
并先说明这会永久删除包括不可变观察日志在内的所有内容。

降低难度不是退步。不要安慰，不要询问原因，做完就回到正常对话。
