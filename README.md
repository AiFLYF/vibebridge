# VibeBridge

> 创造不是治疗，而是一座桥：把一个人内部的兴趣、想法和能力，一点点连接到更大的世界。

一个长期运行的个人成长支持系统，以 Vibe Coding 和创造活动为低压力入口。它在你正常使用 AI 的过程中安静地积累行为数据，逐渐理解你适合什么样的交互方式，并在恰当的时候提供**完全可以拒绝**的下一步。

**这不是医疗工具。** 它不诊断、不评估、不判断"治愈程度"，也不把"看起来像正常人"当成目标。

---

## 它不做什么

这部分比功能列表更重要：

- 不问卷化。初始化时**一个问题都不问**，画像只能从自然交互中长出来
- 不打断。任何建议只能出现在任务自然完成之后
- 不追问。你说"不"，就结束了。连续两次拒绝会自动进入 7 天静默期
- 不惩罚。拒绝和失败都不降低任何数值
- 不替换你的目标。成长机会只能从你已有的目标里派生
- 不上传。全部数据在本地，报告零网络请求

## 架构

```
LLM 决策层        判断何时观察、如何措辞、什么是自然机会
      ↕ CLI       唯一接口，LLM 不直接编辑任何 JSON
确定性数据层      存储 / 置信度演算 / 指标计算 / 安全闸门 / 报告生成
```

数据流：

```
自然对话 → 观察 → 候选记忆 → 跨会话验证 → 长期画像
                                    ↓
                            自适应成长引擎
                                    ↓
                    可选实验 → 结果 → Analytics → HTML 报告
```

`observations.jsonl` **只追加、不可变，是唯一真相源**。候选记忆、验证记忆、画像、指标全部是派生物，任何时候可以完整重算。

## 安装

需要 Python 3.9+，零第三方依赖。

```bash
git clone https://github.com/<you>/vibebridge.git
cp -r vibebridge ~/.claude/skills/vibebridge
```

Windows PowerShell：

```powershell
Copy-Item -Recurse vibebridge "$HOME\.claude\skills\vibebridge"
```

然后在对话中：

```
/vb-init
```

初始化只创建目录和配置文件，**不会问你任何问题**。

可选：装上斜杠命令（`/vb-report`、`/vb-profile` 等），见 [`install/README.md`](install/README.md)。不装也能用，正常聊天时 skill 会自动生效。

验证安装：

```bash
python ~/.claude/skills/vibebridge/core/vb.py doctor
```

## 代码与数据分离

```
~/.claude/skills/vibebridge/     Skill 代码（可随时覆盖升级）
~/.vibebridge/                   你的数据（升级永远不会碰）
```

用 `VIBEBRIDGE_HOME` 环境变量可以改数据位置。

```
~/.vibebridge/
├── version.json  config.json  profile.json
├── memory/
│   ├── observations.jsonl      不可变真相源
│   ├── candidates.json         全部信念 + 证据累积
│   ├── verified.json           已验证信念
│   └── conflicts.json          信念修订记录
├── sessions/YYYY/MM/
├── projects/  experiments/  milestones/  growth/  analytics/
├── reports/latest.html + history/
├── backups/  exports/  logs/
```

## 日常使用

大部分时候你什么都不用做，就是正常写代码、做东西。系统在后台记录。

想看的时候：

| 命令 | 作用 |
|---|---|
| `/vb-report` | 生成交互式 HTML 报告 |
| `/vb-dashboard` | 生成并打开 |
| `/vb-profile` | 当前自动形成的画像 |
| `/vb-memory` | 长期记忆及其证据 |
| `/vb-grow` | 当前最自然的下一步（可能是"现在什么都不适合"） |
| `/vb-reflect` | 低压力复盘，不需要回答任何东西 |
| `/vb-reset` | 降低当前难度 |

## 报告

单文件 HTML，完全离线，可以直接拷走或存档。11 个页面：

总览 · 趋势 · 行为 · 成长时间线 · 项目 · 实验 · 互动地图 · 记忆浏览器 · 证据浏览器 · 洞察 · 支持策略

时间窗口 `7D / 30D / 90D / 6M / ALL`，所有数字可以点击展开到原始观察记录。

洞察严格区分三类，推断永远不会被写成事实：

> **观察到的事实** — 过去 30 天主动分享作品的记录比上一周期多。
>
> **可能的解读** — 这可能意味着低压力的公开表达正在变得容易，也可能只是最近项目性质不同。
>
> **可选的下一步** — 保持现在的节奏就好，不需要升级到实时群聊。

## 置信度模型

```
confidence = saturation(证据权重) × consistency(支持/反对) 
           × cross_session(跨会话分布) × recency(时间衰减)
```

晋升为"已验证"需要同时满足：`confidence ≥ 0.75`、证据 ≥ 3 条、来自 ≥ 2 个不同会话。

同一会话内重复的证据只算 25% 权重——**一次话多的对话在数学上不可能制造出一条长期结论**。

出现相反证据时不覆盖旧信念，而是写一条修订记录，两个方向的证据同时保留。

## 六个成长维度

自我表达 · 沟通 · 社会互动 · 协作 · 独立性 · 自我倡导

各自独立，各有 0-10 阶梯。**"协作 L7、语音沟通 L2" 是完全合法的状态**，不需要被拉平。

等级可升可降。降级记为"主动降低难度以回到舒适区"，不是扣分。

## 隐私

- 默认全部本地，不上传任何第三方
- HTML 报告零网络请求
- `vb export` 完整导出，`vb reset all --confirm` 彻底删除
- 仓库里的示例数据全部是虚构人物

## 测试

```bash
python tests/run_all.py          # 130 项端到端验收
python tests/simulate.py         # 生成 A~E 五个模拟用户
python tests/validate_html.py <report.html>
```

覆盖：初始化幂等、跨会话晋升、同会话防自我强化、冲突修订、时间衰减、多维升降级、拒绝零惩罚、连续拒绝静默期、数据损坏隔离恢复、日志截断修复、备份还原、schema 迁移与回滚、空数据、非法输入、600 条量级、隐私导出与彻底删除。

五个模拟用户覆盖不同模式，其中**用户 D 持续拒绝所有实验**——测试断言他的所有等级保持为 0、没有任何失败记录、且系统进入静默期，同时仍然形成了有意义的画像。

## 开发

```
core/       schema store memory observe session project experiment
            growth safety profile analytics insight report migrate vb
templates/  dashboard.html
references/ 按需加载的深入文档
tests/      run_all simulate validate_html
examples/   虚构的示例数据集
```

添加 schema 迁移：在 `core/migrate.py` 用 `@migration("1.0.0", "1.1.0")` 装饰。迁移前自动快照，失败自动回滚。

## 许可

MIT

## 免责声明

本项目基于交互过程中产生的行为数据，用于长期自我观察、个性化支持和成长复盘，不构成医学诊断、临床评估或任何形式的疗效判断。它不能替代专业支持。如果你或你关心的人正在经历心理危机，请联系专业人士（中国大陆心理援助热线 12356，紧急情况 120）。

完整声明见 [DISCLAIMER.md](DISCLAIMER.md)。

