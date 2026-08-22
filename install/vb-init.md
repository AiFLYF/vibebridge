---
description: 初始化 VibeBridge，只建基础设施，不问任何问题
allowed-tools: Bash(python:*)
---
运行 VibeBridge 初始化：

```bash
python "$HOME/.claude/skills/vibebridge/core/vb.py" init
```

然后**只说一句话**告诉用户完成了，数据存在哪里，接着就回到用户本来想做的事。

严禁在初始化前后询问姓名、年龄、诊断、兴趣、社交能力、性格、心理状态或任何个人信息。
严禁说"为了更好帮助你，请回答以下问题"。
画像只能从后续自然交互中生长出来。
