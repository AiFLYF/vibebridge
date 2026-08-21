# 配置

```bash
python core/vb.py config
python core/vb.py config --set growth.quiet_days_after_declines=14
```

配置文件：`~/.vibebridge/config.json`

## privacy

| 键 | 默认 | 说明 |
|---|---|---|
| `local_only` | `true` | 仅本地存储。改成 false 不会启用任何上传，只是取消断言 |
| `store_raw_excerpts` | `true` | 是否保存原文片段 |
| `excerpt_max_chars` | `240` | 片段长度上限 |

关闭原文片段会让证据浏览器只显示中性描述，追溯能力下降但隐私性更强。

## growth

| 键 | 默认 | 说明 |
|---|---|---|
| `enabled` | `true` | 关掉之后系统只观察，永不提出任何机会 |
| `max_offers_per_session` | `1` | 每会话最多提议次数 |
| `min_hours_between_offers` | `20` | 两次提议的最小间隔 |
| `decline_streak_trigger` | `2` | 连续拒绝多少次进入静默期 |
| `quiet_days_after_declines` | `7` | 静默期天数 |

想彻底安静：

```bash
python core/vb.py config --set growth.enabled=false
```

想更保守（拒绝一次就静默两周）：

```bash
python core/vb.py config --set growth.decline_streak_trigger=1
python core/vb.py config --set growth.quiet_days_after_declines=14
```

**只应该往更安静的方向调。** 调高 `max_offers_per_session` 或调低 `min_hours_between_offers` 会削弱不打扰原则，不建议。

## confidence

| 键 | 默认 | 说明 |
|---|---|---|
| `promote_confidence` | `0.75` | 晋升为已验证的置信度门槛 |
| `promote_evidence` | `3` | 最少证据条数 |
| `promote_sessions` | `2` | 最少不同会话数 |
| `demote_confidence` | `0.50` | 跌破此值降级为 weakened |
| `half_life_days` | `120` | 时间衰减半衰期 |

`promote_sessions` **不要设为 1**。它是防止单次对话自我强化的核心机制，设为 1 会让系统从一句话里编出长期结论。

改动这些不影响已有数据，重算即可生效：

```bash
python core/vb.py memory rebuild
```

## report

| 键 | 默认 | 说明 |
|---|---|---|
| `default_window` | `"30D"` | 报告默认时间窗口 |

## 代码内常量

需要改行为时在源码里调整，不通过配置暴露，避免误操作：

| 常量 | 位置 | 默认 |
|---|---|---|
| `SAME_SESSION_DAMPING` | `core/memory.py` | `0.25` |
| `SATURATION_RATE` | `core/memory.py` | `0.9` |
| `CONTRADICT_WEIGHT` | `core/memory.py` | `1.15` |
| `STABILITY_ON_SUCCESS` | `core/growth.py` | `0.35` |
| `PROMOTE_STABILITY` | `core/growth.py` | `0.60` |
| `COOLDOWN_HOURS_AFTER_LEVEL_UP` | `core/growth.py` | `48` |
| `MIN_CONFIDENCE_FOR_PROFILE` | `core/profile.py` | `0.35` |
| `MIN_SAMPLES_FOR_INFERENCE` | `core/insight.py` | `4` |
| `FORBIDDEN_PATTERNS` | `core/safety.py` | 见 references/safety.md |

## 环境变量

| 变量 | 说明 |
|---|---|
| `VIBEBRIDGE_HOME` | 数据目录，默认 `~/.vibebridge` |
| `PYTHONIOENCODING=utf-8` | Windows 上管道处理中文时建议设置 |

## 备份策略

自动快照发生在：迁移前、重建前、成长重置前、彻底删除前、手动 `vb backup create`。

保留最近 20 个，更旧的自动清理。隔离的损坏文件存放在 `backups/quarantine/`，**永不自动删除**。

