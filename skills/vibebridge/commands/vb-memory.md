---
description: 查看 VibeBridge 长期记忆与证据链
allowed-tools: Bash(python:*)
---
$ARGUMENTS 若是一个 key，则展示该条记忆的完整证据链；否则列出全部。

```bash
python "$HOME/.claude/skills/vibebridge/scripts/vb.py" memory list --limit 50
python "$HOME/.claude/skills/vibebridge/scripts/vb.py" memory conflicts
```

查看单条：

```bash
python "$HOME/.claude/skills/vibebridge/scripts/vb.py" memory show --key <key>
```

展示时保留状态（候选/已验证/已减弱）、置信度、证据条数、跨会话数。
如果有信念修订记录，说明旧信念没有被删除，只是重算了置信度。
