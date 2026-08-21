# 观察分类与 key 命名

## 唯一原则

观察记录的是**发生了什么**，不是**它意味着什么**。

如果一句话删掉之后无法从原始对话中复原，那它就不是观察，是推断。

| 观察（写） | 推断（不写） |
|---|---|
| 用户本次婉拒了继续讨论 | 用户社交能力下降 |
| 用户在第三次尝试后完成了调试 | 用户很有毅力 |
| 用户要求把语音改成文字 | 用户害怕说话 |
| 用户连续两周只推进同一个项目 | 用户有强迫倾向 |
| 用户说"我需要一点时间" | 用户在自我倡导上进步了 |

最后一行值得注意：**"用户说了什么"是观察，"这说明他进步了"是推断。** 进步的判断由 Analytics 从长期数据中得出，不由单次观察断言。

CLI 会对含有 `能力下降`、`退步了`、`性格`、`不合作` 等词的 statement 返回警告，但它拦不住所有情况，最终由你把关。

## 14 个类别

| category | 用于 | 示例 statement |
|---|---|---|
| `interest` | 被什么吸引 | 用户主动提出想做音乐可视化 |
| `strength` | 展现出的能力 | 用户独立定位并修复了渲染问题 |
| `communication_preference` | 偏好的信息交换方式 | 用户希望把讨论改成文字形式 |
| `interaction_preference` | 节奏、结构、发起方式 | 用户偏好一次只处理一个问题 |
| `support_preference` | 什么样的帮助有效 | 用户希望先看到完整步骤再开始 |
| `behavior_pattern` | 反复出现的可观察行为 | 用户会反复调整细节直到满意 |
| `engagement_pattern` | 参与的节律 | 用户的活跃时间集中在少数几天 |
| `potential_stressor` | 观察到的负荷信号 | 用户在需要立刻回应时表示吃力 |
| `successful_strategy` | 有效的做法 | 提供三个具体选项时用户回应更充分 |
| `unsuccessful_strategy` | 无效的做法 | 开放式提问时用户通常不回应 |
| `social_experience` | 与外部世界的互动 | 用户回复了一条 issue 评论 |
| `self_advocacy` | 表达需求、边界、请求 | 用户主动说明自己需要更多时间 |
| `project_event` | 创作生命周期事件 | 用户完成并发布了作品集站点 |
| `growth_signal` | 首次出现或发生变化的行为 | 用户第一次主动展示了未完成的作品 |

`potential_stressor` 只描述**观察到的信号**（停顿、简短、明说吃力、中止），不推断情绪状态，更不推断原因。

## key 命名

`key` 是信念的稳定标识符，也是证据累积的唯一依据。

规则：
- snake_case，英文，描述**信念本身**而不是这一次的事件
- 同一个信念在任何时候都必须复用同一个 key
- 反向证据用**同一个 key** 加 `"polarity":"contradict"`

```
好： async_text_pref        （信念：偏好异步文字）
坏： user_said_no_to_call   （事件，下次对不上）
坏： async_text_pref_2      （凭空造出第二个 key，证据被劈成两半）
```

key 用错会导致：证据无法累积 → 永远达不到晋升门槛 → 长期画像失效。这是这套系统里最容易犯也最致命的错误。

写入前先查已有的 key：

```bash
python core/vb.py memory list --limit 100
```

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `category` | 是 | 上表 14 选 1 |
| `key` | 是 | 稳定信念标识符 |
| `statement` | 是 | 中性的行为描述 |
| `polarity` | 否 | `support`(默认) / `contradict` / `neutral` |
| `strength` | 否 | 0..1，这一次证据的分量，默认 0.5 |
| `domains` | 否 | `expression` `communication` `social` `collaboration` `independence` `self_advocacy` |
| `excerpt` | 否 | 原文片段，最多 240 字符 |
| `session_id` | 否 | 用 `--session auto` 自动处理 |
| `project_id` | 否 | 关联项目 |

### strength 参考

| 值 | 场景 |
|---|---|
| 0.3 | 微弱线索，可能是偶然 |
| 0.5 | 一般观察（默认） |
| 0.7 | 明确、清晰的行为 |
| 0.9 | 用户直接明说的偏好或需求 |

宁可低估。置信度会随证据累积自然上升，不需要靠单次高分催熟。

## 批量写入

```bash
python core/vb.py observe --session auto --json '[
  {"category":"interest","key":"audio_visual_creation",
   "statement":"用户主动提出想做音乐可视化效果",
   "domains":["expression"],"strength":0.7},
  {"category":"communication_preference","key":"concrete_questions",
   "statement":"用户对分步骤的具体问题回应更充分",
   "domains":["communication"],"strength":0.6}
]'
```

同一会话内对同一 key 的重复观察会被自动降权到 25%，所以不必担心多写，但也不要靠重复刷置信度——那是无效的。

