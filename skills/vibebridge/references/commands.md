# CLI 完整参考

`scripts/vb.py` 指 `<skill-dir>/scripts/vb.py`，`<skill-dir>` 是本 Skill 的安装目录
（典型值 `~/.claude/skills/vibebridge`）。执行时请展开为绝对路径，不要依赖当前工作目录。

```bash
python scripts/vb.py <command> [action] [options]
```

全部输出为 UTF-8 JSON。失败时 `ok: false` 且退出码 1。
数据目录由 `VIBEBRIDGE_HOME` 覆盖，默认 `~/.vibebridge/`。

## 基础设施

```bash
vb init                     # 只建基础设施，不问任何问题，可重复运行
vb doctor                   # 完整性 + 安全自检
vb doctor --repair          # 显式清理被截断的日志行（原文件保留在 quarantine）
```

## observe

```bash
vb observe --session auto --json '[{...}]'
vb observe --category interest --key k --statement "..." \
           --domains expression,social --strength 0.7 \
           --polarity support|contradict|neutral \
           --excerpt "原文片段" --project proj_0001 --ts 2026-08-01T10:00:00Z
```

`--json` 接受单个对象、数组，或一个文件路径。
`--session auto` 复用当前打开的会话，没有则新建。

## memory

```bash
vb memory list [--status verified|candidate|weakened|retired]
               [--min-confidence 0.5] [--limit 50]
vb memory show --key <key>       # 完整证据链 + 置信度历史
vb memory conflicts [--limit 20] # 信念修订记录
vb memory rebuild                # 从 observations.jsonl 完整重建
vb memory decay                  # 按当前时间重算衰减
```

## profile

```bash
vb profile [--rebuild] [--evidence] [--min-confidence 0.4]
vb profile --strategies          # 个性化交互指南
```

## session

```bash
vb session open   [--project <name>] [--ts <iso>]
vb session ensure                        # 幂等：有就复用，没有才建
vb session close  [--id <sid>] [--summary "..."] [--task-in-progress]
vb session update --id <sid> --json '{"stress_signals":["..."]}'
vb session show   [--id <sid>]
vb session list   [--limit 20]
```

`--task-in-progress` 会延迟总结而不是打断工作。

## project

```bash
vb project create --name "音乐可视化" --idea "..." --stack "html,js"
vb project update --id proj_0001 --stage completed --event completed
vb project update --id proj_0001 --json '{"published":true,"completion":1.0}'
vb project bump   --id proj_0001 --field feedback_received --amount 2
vb project list
vb project timeline
```

阶段：`created building improving completed published feedback_received communicating collaborating`

## grow

```bash
vb grow state                              # 六维当前状态
vb grow opportunities [--session <sid>] [--task-in-progress] [--limit 3]
vb grow decline [--reason "..."]           # 零惩罚
vb grow ease --domain social --steps 2     # 主动降难度
vb grow pause / vb grow resume
```

`opportunities` 返回的 `gate.allowed` 是唯一权威。

## experiment

```bash
vb experiment propose --objective "..." --domain expression --difficulty 2 \
                      --action-text "..." --session <sid> [--force]
vb experiment accept  --id experiment_001
vb experiment decline --id experiment_001 --reason "..."
vb experiment complete --id experiment_001 --result successful \
                       --outcome "..." --stress 0.2 --engagement 0.8 \
                       --recovery 5 --repeat true --notes "..."
vb experiment list [--result successful] [--domain social]
vb experiment what-works
```

`--force` 仅用于测试，会绕过安全闸门。**正常使用中永远不要用它。**

结果：`successful partial unsuccessful not_suitable cancelled paused pending`

## milestone

```bash
vb milestone add --title "第一次公开发布作品" --detail "..." \
                 --kind first_time --evidence obs_000012,obs_000031
vb milestone list
```

## 分析与报告

```bash
vb analytics --window 7D|30D|90D|6M|ALL [--no-save]
vb insight   --window 30D
vb reflect   --window 7D
vb report    --window 30D [--open]
```

报告输出：
```
~/.vibebridge/reports/latest.html
~/.vibebridge/reports/index.html
~/.vibebridge/reports/history/YYYY-MM-DD.html
```

## 数据管理

```bash
vb backup create [--tag manual]
vb backup list
vb backup restore --name 20260821T174500_manual

vb migrate status
vb migrate run [--dry-run]
vb migrate rollback [--name <snapshot>]

vb export                      # 打包全部数据为 zip

vb reset difficulty [--domain social] [--steps 1]   # 只降难度
vb reset growth                                     # 重置成长，保留记忆
vb reset all --confirm                              # 彻底删除

vb config
vb config --set growth.quiet_days_after_declines=14
```

## safety

```bash
vb safety                      # 规则清单 + 自检
vb safety --text "<文本>"      # 措辞检查 + 危机扫描
```

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 校验失败、未初始化、安全拦截或运行错误 |

所有错误都会写入 `~/.vibebridge/logs/vibebridge.log`。

