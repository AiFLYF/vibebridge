# 斜杠命令

这些是可选的。装不装，VibeBridge 都会在正常对话中自动工作。

## 为什么带 vb- 前缀

`/init` 和 `/memory` 是 Claude Code 的**内置命令**。如果把 VibeBridge 的命令也叫这个名字，敲下去只会触发内置行为，永远调不到本项目。

所以统一用 `vb-` 前缀。副作用是好的：在输入框敲 `/vb` 就能看到全部命令。

## 安装

macOS / Linux：

```bash
mkdir -p ~/.claude/commands
cp skills/vibebridge/commands/vb-*.md ~/.claude/commands/
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME\.claude\commands" | Out-Null
Copy-Item skills\vibebridge\commands\vb-*.md "$HOME\.claude\commands\"
```

重开 Claude Code 后生效。

## 命令

| 命令 | 用途 |
|---|---|
| `/vb-init` | 初始化。只建基础设施，不问任何问题 |
| `/vb-report` | 生成交互式 HTML 报告 |
| `/vb-dashboard` | 生成并在浏览器打开 |
| `/vb-profile` | 自动形成的画像 + 对你有效的交互方式 |
| `/vb-memory` | 长期记忆与证据链 |
| `/vb-grow` | 当前最自然的下一步（可能是"现在什么都不适合"） |
| `/vb-reflect` | 低压力复盘，不需要回答任何问题 |
| `/vb-reset` | 降低当前难度 |
| `/vb-doctor` | 数据完整性与安全自检 |

## 卸载

```bash
rm ~/.claude/commands/vb-*.md
```

删掉命令不影响 skill 本身，也不会动 `~/.vibebridge/` 里的任何数据。

## 路径假设

命令文件里写死了 `$HOME/.claude/skills/vibebridge/scripts/vb.py`。如果你把 skill 装在别处，改一下这些文件里的路径即可。

