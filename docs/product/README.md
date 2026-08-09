# RefineQ 产品文档

这套文档面向 Eazo「Personal Agent」赛道初赛（8 月 10 日 22:00 截止）与复赛（8 月 16/17 日），同时作为赛后继续演进的产品基线。评分与提交规则以 [HACKATHON.md](../../HACKATHON.md) 为准，本套文档负责回答"产品是什么、为谁做、怎么改、怎么讲"。

## 文档地图

| 文档 | 内容 | 主要服务的评分项 |
| --- | --- | --- |
| [01-positioning.md](01-positioning.md) | 定位、价值主张、竞品差距、价值实现四维分析、文案修改建议 | 洞察与理解 30%，体验设计 40% |
| [02-persona.md](02-persona.md) | 起点人物档案模板、访谈提纲、授权模板、官方六问回答框架 | 洞察与理解 30%，真实使用 20% |
| [03-prd.md](03-prd.md) | 核心闭环、功能规格现状与调整、可靠性规则、非目标 | 静态测评，完成度 20% |
| [04-experience.md](04-experience.md) | 用户旅程、Aha 时刻设计、逐条体验升级建议（含涉及文件与工作量） | 体验设计 40% |
| [05-roadmap.md](05-roadmap.md) | P0（提交前）/ P1（复赛前）/ P2（赛后）路线图与"不要做"清单 | 全部 |
| [06-demo-script.md](06-demo-script.md) | 演示账号准备、2 分钟视频分镜、动态测评预算、4 分钟路演与故障预案 | 动态测评 50%，技术连通性 10% |
| [07-submission-kit.md](07-submission-kit.md) | 提交表单逐项草稿、Agent 简介文案、源码 ZIP 打包规范、最终检查表 | 初赛提交 |
| [08-adversarial-experience-agentization-review.md](08-adversarial-experience-agentization-review.md) | 导航整治后的完整流程、交互体验、价值实现与 Agent 化对抗性审查，以及第一性原理方案 | 赛后产品与 Agent 演进基线 |

## 使用顺序

今天（8 月 8 日）到提交（8 月 10 日 22:00）建议按这个顺序执行：

1. 读 [05-roadmap.md](05-roadmap.md)，确认 P0 范围，冻结其余改动。
2. 按 [02-persona.md](02-persona.md) 完成一次真实访谈并取得授权。这是全套材料里唯一不能由团队自己补齐的东西，最先做。
3. 按 [01-positioning.md](01-positioning.md) 的文案建议改 README 与首页占位文案。
4. 按 [06-demo-script.md](06-demo-script.md) 准备演示账号与公网部署验收。
5. 按 [07-submission-kit.md](07-submission-kit.md) 打包提交。

## 三个纪律

**不可虚构。** 人物、引语、使用数据必须来自真实访谈与真实使用。伪造用户反馈属于官方明列的取消资格情形（HACKATHON.md 第 11 节）。所有文档中标注【待访谈填写】的字段，宁可空着提交，也不要编造。

**先讲人，再讲相似用户。** 对外任何一处表达（提交表单、README、视频、路演）都从一位具体人物开始，"适合所有学生"这类说法一律不出现。

**提交前只做低风险改动。** 距截止约两天，代码层面只接受文案、单点小改与部署验收。任何重构、依赖变更、新功能模块都放进 P1/P2。
