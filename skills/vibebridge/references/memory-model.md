# 记忆模型

> 下文 `scripts/vb.py` 指 `<skill-dir>/scripts/vb.py`（典型值
> `~/.claude/skills/vibebridge/scripts/vb.py`），执行时展开为绝对路径。

## 四层结构

```
observations.jsonl      不可变、只追加、唯一真相源
        ↓
candidates.json         全部信念及其证据累积
        ↓
verified.json           达到验证门槛的信念（派生视图）
        ↓
profile.json            长期用户模型（派生视图）
```

下面三层**全部是派生物**。任何时候都可以删掉，然后从 observations 完整重算：

```bash
python scripts/vb.py memory rebuild
```

这既是恢复机制，也意味着一条铁律：**profile 永远不能反过来成为事实来源。** 系统不允许"根据画像推测过去发生过什么"。

## 置信度

```
confidence = saturation × consistency × cross_session × recency
```

| 因子 | 公式 | 作用 |
|---|---|---|
| saturation | `1 - exp(-0.9 × 支持权重)` | 证据越多越接近 1，但边际递减 |
| consistency | `支持 / (支持 + 1.15 × 反对)` | 反向证据略微加权 |
| cross_session | `min(1, 0.45 + 0.275 × 会话数)` | 单一会话最高只能到 0.725 |
| recency | `0.5 ^ (距今天数 / 120)` | 半衰期 120 天 |

结果钳制在 `[0.02, 0.97]`。**系统永远不会 100% 确信任何关于一个人的事。**

### 同会话降权

同一会话内对同一 key 的第 2 条及以后的证据，权重乘以 **0.25**。

配合 `cross_session` 因子，这意味着：**一次话多的对话在数学上不可能制造出一条已验证的长期信念。** 这是刻意的——防止系统从一次偶然的表达里编出一个"人格"。

### 晋升门槛

三个条件必须同时满足：

```
confidence      >= 0.75
evidence_count  >= 3
distinct sessions >= 2
```

### 状态流转

```
candidate ──晋升──> verified ──反向证据/衰减──> weakened ──新证据──> verified
                                    │
                                    └── confidence<0.12 且有反向证据 ──> retired
```

`retired` 也不会被删除，只是不再进入画像。

## 冲突：修订，不是覆盖

出现反向证据时，系统**不覆盖**旧信念，而是写一条修订记录：

```json
{
  "key": "async_text_pref",
  "previous_belief": "用户在新会话中再次表示偏好异步文字",
  "previous_status": "verified",
  "new_evidence": "用户这次主动发起了一次语音通话",
  "confidence_before": 0.842,
  "confidence_after": 0.5812,
  "reason": "出现方向相反的新证据。旧信念未被删除，只是重新计算置信度。",
  "observation_ids": ["obs_000005"]
}
```

两个方向的证据同时保留，置信度重算。人本来就会变化，也本来就不一致——系统必须能表示这一点，而不是强行选一个答案。

```bash
python scripts/vb.py memory conflicts
```

## 时间衰减

半衰期 120 天。长期没有再出现的信念会自然淡出，跌破 0.5 的已验证信念降级为 `weakened`。

```bash
python scripts/vb.py memory decay
```

这防止系统拿三年前的一句话当成"这个人就是这样"。

## 证据追溯

任何一条记忆都能回到原始观察和会话：

```bash
python scripts/vb.py memory show --key async_text_pref
```

返回完整证据链：每条 observation 的 id、时间、会话、原文、方向，以及置信度的逐步变化历史。

HTML 报告里所有数字都可点击展开到这一层。**不能追溯到原始观察的结论，不应该出现在报告里。**

