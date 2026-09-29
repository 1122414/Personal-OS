# Personal OS V0.1 产品设计

> 版本：V0.1  
> 日期：2026-09-22  
> 状态：产品设计初稿  
> 前置文档：`person os初版讨论.md`

---

# 1. 产品目标

V0.1 不追求“做一个功能齐全的个人操作系统”。

第一版只验证一个核心问题：

> **我能不能每天从 Personal OS 开始工作，并且在一天结束时，系统知道我今天做了什么。**

V0.1 的唯一主闭环：

```text
早上
Morning Brief
    ↓
确认今日计划
    ↓
Today Tasks
    ↓
自己完成 / 委派 Agent
    ↓
Agent Run
    ↓
Review
    ↓
Task Done
    ↓
晚上自动汇总
    ↓
Daily Log
    ↓
用户确认 / 纠偏
    ↓
成为明天的上下文
```

---

# 2. 产品定位

Personal OS 不是：

- Notion 替代品
- Obsidian 替代品
- Todo 软件
- Agent Dashboard
- Multica 换皮
- 把所有 AI 工具堆在一个页面上的聚合器

Personal OS 的核心是：

> **围绕用户每天“计划 → 执行 → 委派 → 审核 → 记录”的全过程，持续沉淀 Personal Work Graph。**

---

# 3. V0.1 一级页面

第一版只保留 6 个一级页面：

```text
Personal OS

├── Today
├── Tasks
├── Projects
├── Review
├── Intelligence
└── History
```

建议侧边栏：

```text
⌂ Today

□ Tasks
◇ Projects

◎ Intelligence
✓ Review

◷ History
```

右下角保留全局入口：

```text
Ask / Create Task
```

无论在哪个页面，都可以通过一句自然语言创建任务。

例如：

```text
帮我调研一下 Multica 最近的 Agent Runtime 设计
```

系统识别：

```text
Intent：创建任务
Task：调研 Multica Agent Runtime
Project：Personal OS
建议执行：Research Agent
```

用户确认后创建 Task。

---

# 4. Today：每日工作主入口

Today 不是传统 Dashboard。

它是：

> **每日工作驾驶舱。**

页面需要根据一天中的阶段发生变化：

```text
上午：Plan
白天：Execution
晚上：Review
```

---

# 5. Morning Brief

## 5.1 作用

Morning Brief 是用户每天打开 Personal OS 后最先看到的内容。

它不只是展示数据，而是直接回答：

> **我今天应该优先做什么？**

示例：

```text
今天建议优先完成：

① Personal OS V0.1 页面设计
   原因：昨日已完成需求定义，建议继续推进

② 完成 SmartRun XXX
   原因：Deadline 为今天

③ 阅读 XXX Agent 论文
   原因：与当前 Agent Runtime 方向相关
```

操作：

```text
[调整计划]    [确认今日计划]
```

---

## 5.2 Morning Brief 输入

V0.1 只使用以下四类输入：

```text
Yesterday Daily Log
        +
未完成 Tasks
        +
Projects / Deadline
        +
Intelligence
        ↓
Morning Brief Generator
```

第一版不需要复杂 Planner。

系统只需要将结构化上下文交给模型，由模型生成今日建议。

示例输入：

```text
昨天完成：
- Personal OS 产品定义
- Multica 调研

昨天遗留：
- V0.1 页面设计

当前项目：
- Personal OS：已完成需求定义，进入产品设计阶段

Deadline：
- SmartRun XXX：今天

值得关注：
- Gemini 发布 XXX
```

输出：

```json
{
  "priorities": [
    {
      "task": "完成 Personal OS V0.1 页面设计",
      "reason": "昨日需求定义已经完成，适合继续推进"
    }
  ]
}
```

核心原则：

> Morning Brief 的质量主要依赖上下文质量，而不是依赖复杂 Agent 推理。

---

# 6. 确认今日计划

AI 只拥有建议权，不拥有决定权。

Morning Brief 生成后，用户可以：

- 调整顺序
- 删除
- 修改
- 新增任务
- 调整优先级

最后点击：

```text
确认今日计划
```

系统记录：

```text
DailyPlanConfirmed
```

只有确认后的任务才真正进入 Today Tasks。

---

# 7. Today 执行态

确认今日计划后，Today 页面进入执行模式。

示例：

```text
TODAY

3 / 6 Completed
────────────────────────

□ SmartRun XXX
  Project · SmartRun
  高优先级

□ Personal OS V0.1 页面设计
  Project · Personal OS

✓ 阅读 Agent Runtime 文档

────────────────────────

Agent Running

● 调研 Multica Runtime
  Research Agent
  Running · 16 min

────────────────────────

Project Pulse

Personal OS
昨天：完成产品定义
今天：V0.1 产品设计
风险：无
```

---

# 8. Task：系统核心对象

Task 是整个 Personal OS 最重要的执行对象。

核心原则：

> **Agent 是劳动力，Task 才是一等公民。**

V0.1 Task 基础字段：

```text
Task

id
title
description

status
priority

project_id

source
created_at
planned_date
deadline

executor_type
agent_id

result
review_status

created_by
```

---

## 8.1 Task Source

Task 需要记录来源。

V0.1 支持：

```text
Manual
Morning Brief
Intelligence
Project
Agent Suggestion
Yesterday Carryover
```

这样后续可以分析：

> 我的任务通常是从哪里产生的？

---

# 9. Task 生命周期

V0.1 默认状态机：

```text
Inbox
  ↓
Planned
  ↓
Running
  ↓
Review
  ↓
Done
```

异常状态：

```text
Running
  ↓
Blocked
```

人工任务：

```text
Planned
  ↓
Done
```

Agent 任务：

```text
Planned
  ↓
Running
  ↓
Review
  ↓
Done
```

核心原则：

> **Agent Finished ≠ Task Done**

Agent 执行结束后，只进入 Review。

只有用户确认后，Task 才真正完成。

---

# 10. Task Detail

Task Detail 第一版使用侧边抽屉即可，不必做完整页面。

示例：

```text
修改 Personal OS Agent Adapter

Project
Personal OS

Status
Review

Executor
Codex

────────────────

Task

实现统一 Agent Adapter：

execute()
status()
cancel()
result()

────────────────

Agent Run

Codex
14:02 Started
14:36 Finished

修改：
7 Files

Tests：
18 / 18 Passed

────────────────

Result

已完成 AgentAdapter 基础接口……

[查看完整结果]

────────────────

[要求继续修改]

[确认完成]
```

完成后提示：

```text
是否值得沉淀？

[保存到 Obsidian]
[仅保留任务]
```

---

# 11. Agent 在 V0.1 中的位置

V0.1 不设置一级 Agents 页面。

原因：

> Agent 不应该重新成为产品中心。

Agent 只作为 Task 的执行方式出现。

例如：

```text
执行方式

○ 我自己

● Agent
  Codex
  Research Agent
```

未来 Agent 数量多了以后，再考虑新增：

```text
Agents / Workforce
```

第一版不做。

---

# 12. Projects

Project 页面不做传统 Jira 式项目管理。

它首先回答：

> **这个项目现在到底处于什么状态？**

示例：

```text
Personal OS

Status
Active

────────────────

AI Project Pulse

当前阶段：
V0.1 产品设计

最近进展：
- 完成产品核心价值定义
- 确定 Personal Work Graph 为核心资产
- 明确 V0.1 主闭环

当前重点：
- Today 页面
- Task 模型
- Agent Runtime Adapter

阻塞：
暂无

────────────────

Active Tasks

□ Today 页面设计
□ Task Schema
□ Agent Adapter

────────────────

Recent Decisions

09/22
V0.1 不开发 Plugin Marketplace

09/22
Task 必须属于 Personal OS
```

Project 页面核心是：

> **Project Context，而不是 Kanban。**

---

# 13. Decision

Decision 是 V0.1 的一等公民。

例如：

```text
Decision

标题：
V0.1 暂时只接入 Codex

内容：
暂不实现完整 Multi-Agent Router，
先验证单 Agent Task 闭环。

关联：
Personal OS

Status：
Active
```

Morning Brief、Project Pulse、AI 建议等后续生成内容必须考虑已有 Decision。

用户明确做出的决定优先级高于 AI 推断。

---

# 14. Intelligence

V0.1 不做传统 News Feed。

正确方向是：

> **Channel-based Intelligence**

页面结构：

```text
Intelligence

[AI] [Agent] [互联网] [金融] [+频道]
```

例如 AI Channel：

```text
AI

今日精选 6

────────────────

Gemini 发布 XXX
Google · 2h

为什么值得关注：
与你关注的 GUI Agent / 长程任务能力相关。

[忽略]
[收藏]
[深入研究]
[创建 Task]
```

---

## 14.1 Intelligence 核心原则

系统不能只告诉用户“这条新闻很重要”。

必须解释：

> **为什么认为它值得你关注。**

用户对每条信息可以：

- 忽略
- 收藏
- 深入研究
- 创建 Task
- 关联 Project

---

# 15. Intelligence Channel

每个频道由以下几部分组成：

```text
边界
+
信息源
+
筛选规则
+
用户反馈
```

示例：

```text
AI

关注：
LLM
Agent
Coding Agent
GUI Agent
模型发布
重要论文

降低优先级：
普通 Prompt 教程
AI 营销文章

每日：
最多 8 条
```

系统根据以下行为逐渐调整排序：

```text
Read
Ignore
Save
DeepResearch
CreateTask
```

原则：

> **用户定义边界，系统只在边界内学习。**

---

# 16. Review Center

Review 是 V0.1 的核心页面之一。

所有需要用户确认的内容统一进入 Review。

示例：

```text
Review

3 Waiting
```

内容：

```text
Codex
完成 Personal OS Agent Adapter

[查看]
```

```text
Research Agent
完成 Gemini 版本调研

[查看]
```

```text
Knowledge Proposal
建议将「Multica Runtime 调研」写入 Obsidian

[查看]
```

V0.1 Review 只需要支持：

- Agent Result Review
- Knowledge Write Review

以后再扩展：

- 邮件发送
- 日历修改
- Git Merge
- 文件删除
- 其他高风险操作

---

# 17. Daily Log

每天晚上系统定时生成 Daily Review。

示例：

```text
Daily Review
September 23

今天完成 5 个 Task

完成：

1. 完成 Personal OS V0.1 产品设计
2. Codex 完成 Agent Adapter
3. 阅读 XXX 论文

────────────────

Agent 工作

Codex
2 Runs
1 Completed

Research Agent
1 Run
Completed

────────────────

产生的成果

personal-os-v0.1.md
AgentAdapter.ts
Multica Research

────────────────

今日重要决策

V0.1 Agent 首先只支持 Codex

────────────────

未完成

SmartRun XXX
→ 是否移动到明天？

────────────────

[修改日报]

[结束今天]
```

点击：

```text
结束今天
```

记录：

```text
DailyLogConfirmed
```

当天工作正式封存。

---

# 18. Daily Log 数据来源

V0.1 晚间扫描只读取：

1. Personal OS 内部 Task / Agent 行为
2. 从 Personal OS 发起的 Agent 对话与结果
3. Obsidian 文件变化

暂时不读取：

- ChatGPT 外部独立聊天
- Claude 外部独立聊天
- 其他软件独立对话

---

# 19. History

History 第一版不做复杂 Timeline。

只需要支持按日期查看 Daily Log。

示例：

```text
History

September

23
完成 5 Task
2 Agent Runs
1 Decision

22
完成 4 Task
3 Decisions

21
完成 6 Task
```

点击某一天后查看当天 Daily Log。

它直接服务一个重要需求：

> **让我知道自己每天真实做过什么，而不是感觉一天虚无地过去。**

---

# 20. Personal Rules

Personal Rules 放在：

```text
Settings
└── Personal Rules
```

示例：

```text
Daily Log

✓ 被动浏览网页不算完成事项

✓ Agent 执行完成后必须经过 Review

✓ 论文阅读只有产生笔记才算完成

────────────────

Intelligence

✓ AI 频道最多 8 条 / 天

✓ 降低 AI 营销内容优先级
```

每条规则支持：

```text
Edit
Disable
Delete
```

用户使用自然语言修改规则。

系统内部可以自动结构化。

---

# 21. Activity / Event Ledger

为了让 Daily Log 和 Work Graph 可追踪，V0.1 从第一天就记录事件。

示例：

```text
09:42 TaskCreated
10:03 AgentRunStarted
10:34 ArtifactCreated
10:41 TaskReviewed
11:12 DecisionCreated
14:26 ObsidianFileChanged
16:03 TaskCompleted
```

晚上：

```text
Events
 ↓
关联 Task / Project
 ↓
过滤 Personal Rules
 ↓
LLM Summary
 ↓
Daily Log
```

Event Ledger 是 Personal Work Graph 的基础设施。

---

# 22. V0.1 核心数据对象

第一版建议包含：

```text
User

Project
Task
Agent
AgentRun

Decision
Artifact

IntelligenceChannel
IntelligenceItem

DailyPlan
DailyLog

PersonalRule
ActivityEvent
```

核心关系：

```text
Project
 ├── Task
 │    ├── AgentRun
 │    │     └── Artifact
 │    └── Decision
 │
 ├── Decision
 └── DailyLog

DailyPlan
 └── Task

IntelligenceItem
 └── Task

ActivityEvent
 ├── Task
 ├── Project
 ├── AgentRun
 └── DailyLog
```

这些对象逐渐构成 Personal Work Graph。

---

# 23. Multica / Agent Runtime 定位

Multica 不属于 Personal OS 的核心数据层。

架构上：

```text
Personal OS
      │
      │ Task
      ▼
Agent Runtime Adapter
      │
      ├── Multica Adapter
      │       ↓
      │    Codex
      │    Claude
      │    DSH
      │
      └── Future Adapter
```

Personal OS 只认统一接口：

```text
execute()
getStatus()
getResult()
cancel()
```

Multica 只是其中一种 Runtime Provider。

核心原则：

> **Personal OS 不依赖 Multica 的内部数据模型。**

未来更换 Agent Runtime 时，Personal Work Graph 不受影响。

---

# 24. V0.1 明确不做

第一版不开发：

- Plugin Marketplace
- Notion 式笔记编辑器
- 完整 Calendar
- Workflow Builder
- 完整 Agent IDE
- 多用户协作
- 手机 App
- 无审核自动写入 Obsidian
- 接入几十种 Agent
- 复杂数据 Dashboard
- Agent Workforce 管理页

可以预留扩展接口，但不提前实现。

---

# 25. V0.1 开发阶段

## Phase 1：Daily Loop

先做：

```text
Today
Tasks
Daily Log
```

先验证：

> Morning → Today → Evening

是否足够好用。

这一阶段甚至不需要 Agent。

---

## Phase 2：Context

加入：

```text
Projects
Decision
Project Pulse
```

目标：

> 让 Morning Brief 和 Daily Log 开始拥有稳定项目上下文。

---

## Phase 3：Agent Loop

加入：

```text
Agent Adapter
Codex / Multica
Review
```

形成：

```text
Task
 ↓
Agent
 ↓
Review
 ↓
Done
```

---

## Phase 4：Information & Personalization

加入：

```text
Intelligence
Obsidian
Personal Rules
```

形成完整 V0.1。

---

# 26. V0.1 验证指标

连续使用 7 天后，满足以下三条则认为方向成立：

### 1. Personal OS 成为每天第一入口
打开电脑后的第一件事，是打开 Personal OS。

### 2. 不再主动打开 Obsidian 找日报
日报和昨日工作已经自动进入 Morning Brief / History。

### 3. 80% Agent Task 从 Personal OS 发出并返回
Agent 不再成为独立的信息孤岛。

---

# 27. 产品判断原则

未来任何新需求，都先问：

1. 它能不能让 Morning Brief 更准？
2. 它能不能让 Task 更顺畅地完成？
3. 它能不能让 Daily Log 更准确？
4. 它能不能让 Personal Work Graph 更有价值？

如果四个问题全部是否：

> **不做。**

---

# 28. V0.1 产品主线

最终可以用五个词概括：

> **Plan → Work → Agent → Review → Remember**

```text
Plan
早上确定今天做什么

Work
白天推进任务

Agent
需要时把 Task 交给 Agent

Review
Agent 结果由用户确认

Remember
将工作过程沉淀进 Personal Work Graph
```

---

# 29. 下一步设计重点

接下来不再继续扩充大框架。

下一阶段进入：

> **Today 首页详细产品设计**

重点确定：

1. Morning Brief 第一屏具体布局
2. Morning Brief 生成逻辑
3. 今日计划编辑与确认交互
4. Today 执行态
5. Agent Running 如何展示
6. Project Pulse 如何展示
7. Evening Review 如何接管 Today
8. 从 Morning 到 Evening 的页面状态切换
