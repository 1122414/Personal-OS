# Personal OS V0.1 UI 设计文档

> 版本：V0.1  
> 日期：2026-09-23  
> 状态：核心页面 UI 设计建议稿  
> 适用范围：桌面 Web 版 Personal OS  
> 前置文档：`person os初版讨论.md`、`Personal OS V0.1产品设计.md`

---

# 1. 文档目的

本设计文档用于统一 Personal OS V0.1 的页面结构、核心交互、主题系统和视觉规则。

本阶段暂不继续细化高保真视觉稿，而是先确定：

- 每个页面承担什么职责
- 页面内应该展示哪些信息
- 主要交互怎么走
- 三套时间主题如何统一
- 哪些组件必须保持一致
- V0.1 的实现优先级

核心原则：

> **主题可以变化，但产品结构不能变化。**

---

# 2. 三套主题系统

Personal OS 首页及其他核心页面使用三套主题，并随时间自动切换。

## 2.1 时间规则

### 10:00–14:00：Morning Theme

对应蓝白潮汐 / 海洋圣域主题。

特点：

- 银白
- 海蓝
- 青绿色
- 柔和金色
- 透明玻璃材质
- 海面、遗迹、圣堂、潮汐元素
- 整体轻盈、平静、清澈

适用状态：

> 上午进入工作状态、规划、阅读、学习。

---

### 14:00–20:00：Afternoon Theme

对应红黑哥特 / 赤色剧场主题。

特点：

- 深红
- 黑色
- 银白
- 暗金
- 哥特、玫瑰、荆棘、舞台、教堂
- 更强对比
- 更高能量
- 更强视觉焦点

适用状态：

> 下午高强度推进、创作、执行。

---

### 其余时间：Night Theme

对应深海暗色 / Abyss Theme。

特点：

- 深蓝黑
- 冷灰
- 青蓝
- 少量血红
- 深海、潮汐、异质生物、暗色玻璃材质
- 更沉静、更专注

适用状态：

> 夜间执行、独处、回顾、复盘。

---

## 2.2 用户称呼

三套主题中统一使用：

> **博士**

禁止出现：

- 漂泊的旅人
- 旅人
- 指挥官
- 其他称呼

所有问候统一：

```text
早上好，博士。
下午好，博士。
晚上好，博士。
```

---

# 3. 主题系统实现原则

主题只负责：

```text
Theme
├── Wallpaper / 背景
├── Hero Artwork / 主视觉
├── Accent Color / 强调色
├── Surface / 卡片材质
├── Border / 边框
├── Glow / 发光效果
├── Typography Accent / 装饰字体
└── Motion Effect / 动效
```

业务结构不随主题改变。

例如：

```text
TaskCard
ProjectCard
ReviewItem
IntelligenceItem
DailyLogItem
```

在三个主题里：

- 位置相同
- 交互相同
- 信息层级相同
- 只切换视觉 Token

---

# 4. 全局页面结构

V0.1 一级页面：

```text
Personal OS

├── Today
├── Tasks
├── Projects
├── Intelligence
├── Review
├── History
└── Settings
```

Sidebar 推荐：

```text
Today
Tasks
Projects
Intelligence
Review
History

----------------

Settings
```

---

# 5. Global Command Bar

全局 Command Bar 永远位于页面顶部。

示例：

```text
搜索任务、项目、知识，或者直接告诉我你想做什么...
```

支持：

- 创建 Task
- 搜索 Task
- 搜索 Project
- 搜索历史
- 查询知识
- 给 Agent 下任务
- 找某次决策
- 调用快捷操作

Command Bar 是 Personal OS 的统一入口。

---

# 6. Today 首页

## 6.1 页面职责

Today 页面必须回答：

> **博士，我今天应该做什么？**

不是数据 Dashboard。

---

## 6.2 推荐结构

```text
┌─────────────────────────────────────────────┐
│ Greeting + Command Bar                     │
├─────────────────────────────────────────────┤
│ Morning Brief / 今日简报                    │
│                                             │
│ 今天最值得推进的 3 件事                      │
│ ① Task + Why                               │
│ ② Task + Why                               │
│ ③ Task + Why                               │
│                                             │
│ [调整计划]            [确认今日计划]          │
├──────────────────────┬──────────────────────┤
│ Today Tasks          │ Project Pulse        │
├──────────────────────┼──────────────────────┤
│ Intelligence         │ Review Waiting       │
├──────────────────────┴──────────────────────┤
│ Daily Rhythm / Review Entry                │
└─────────────────────────────────────────────┘
```

---

## 6.3 Morning Brief

内容：

- 今日建议优先事项
- 为什么推荐
- 昨日遗留
- Deadline
- Project Context
- Intelligence Context

建议只展示：

> 3 个核心事项

避免变成 Todo 列表。

---

## 6.4 今日计划确认

Morning Brief 之后：

```text
调整
删除
补充
重新排序
```

然后点击：

```text
确认今日计划
```

确认后：

```text
Plan Mode
↓
Work Mode
```

Morning Brief 收缩，Today Tasks 成为主视觉。

---

## 6.5 晚间状态

晚上自动进入：

```text
Review Mode
```

顶部变为：

```text
今天完成：
6 Tasks
2 Agent Runs
1 Decision
3 Artifacts
```

主要按钮：

```text
修改日报
结束今天
```

---

# 7. Tasks 页面

## 7.1 页面职责

Tasks 是整个 Personal OS 的核心工作台。

原则：

> **Task 是一等公民，Agent 是执行器。**

---

## 7.2 推荐布局

```text
顶部：
全部 / 进行中 / Review / Done / Blocked

筛选：
今日 / 本周 / 高优先级 / Agent / 待审核 / 已完成

┌────────────────────────┬───────────────────────┐
│ Task List              │ Task Detail           │
│                        │                       │
│ ○ Task A               │ Title                 │
│ ○ Task B               │ Project               │
│ ○ Task C               │ Deadline              │
│                        │ Priority              │
│                        │ Subtasks              │
│                        │ Executor              │
│                        │ Agent Run             │
│                        │ Artifact              │
│                        │ Activity              │
│                        │                       │
│                        │ [Start]               │
│                        │ [Assign Agent]        │
│                        │ [Done]                │
└────────────────────────┴───────────────────────┘
```

---

## 7.3 Task 列表字段

建议：

```text
Task Name
Project
Priority
Deadline
Executor
Status
```

Status：

```text
Inbox
Planned
Running
Review
Done
Blocked
```

---

## 7.4 Task Detail

必须包含：

- 标题
- 描述
- 所属 Project
- Deadline
- Priority
- Tags
- Subtasks
- Executor
- Agent Run
- Artifact
- Activity
- Notes

---

## 7.5 Agent 入口

执行方式：

```text
○ 我自己

○ Agent
   ├── Codex
   ├── Research Agent
   └── ...
```

按钮：

```text
开始
交给 Agent
完成
```

Agent 完成后：

```text
Running
↓
Review
↓
用户确认
↓
Done
```

---

# 8. Projects 页面

## 8.1 页面职责

Project 页面回答：

> **这个项目现在到底怎么样？**

不是传统 Jira。

---

## 8.2 项目列表

推荐：

```text
[Active] [Paused] [Completed]

Project Card
├── Project Name
├── Current Stage
├── Active Tasks
├── Decisions
├── Last Update
└── Health / Pulse
```

---

## 8.3 Project Detail

推荐结构：

```text
Project Name

AI Project Pulse
────────────────

当前阶段
最近进展
当前重点
风险 / Blocker

────────────────

Active Tasks

────────────────

Milestones

────────────────

Recent Decisions

────────────────

Artifacts

────────────────

Recent Activity
```

---

## 8.4 Decision

Decision 是项目中的核心对象。

例如：

```text
Decision

V0.1 暂不开发 Plugin Marketplace

Status:
Active

Reason:
优先验证 Today → Task → Daily Log 主闭环。
```

AI 后续建议必须尊重 Active Decision。

---

# 9. Intelligence 页面

## 9.1 页面职责

不是新闻 Feed。

而是：

> **个人 Intelligence Center。**

---

## 9.2 频道结构

左侧：

```text
For You

AI
Agent
互联网
金融
产品
论文

+ 新建频道
```

---

## 9.3 信息列表

每条信息至少展示：

- 标题
- 来源
- 时间
- Channel
- Why Recommended
- 相关 Project
- 阅读状态

操作：

```text
忽略
收藏
深入研究
创建 Task
```

---

## 9.4 推荐必须可解释

每条内容显示：

```text
为什么推荐：

与你当前推进的 Personal OS Agent Runtime 有关。
```

或者：

```text
命中 AI Channel：
Coding Agent / GUI Agent
```

---

## 9.5 详情页

```text
Title

Source
Published At

AI Summary

Why Relevant

Related Projects

Evidence / Sources

Related Reading

[Create Task]
[Research]
[Save]
```

---

# 10. Review 页面

## 10.1 页面职责

Review 是：

> **Personal OS 的 Decision Inbox。**

不是普通通知页。

---

## 10.2 分类

```text
All

Agent Results
Knowledge
Decisions

Future:
Email
Calendar
Git
Files
```

---

## 10.3 页面布局

```text
┌───────────────────────┬──────────────────────┐
│ Review Queue          │ Review Detail        │
│                       │                      │
│ Agent Result          │ Task                 │
│ Knowledge Proposal    │ Agent                │
│ Decision              │ Result               │
│ ...                   │ Evidence             │
│                       │ Artifact             │
│                       │                      │
│                       │ Actions              │
└───────────────────────┴──────────────────────┘
```

---

## 10.4 Agent Result 操作

```text
确认完成
继续修改
重新执行
```

---

## 10.5 Knowledge Review

```text
写入 Obsidian
修改后写入
仅保留 Task
不保存
```

---

# 11. History / Daily Log 页面

## 11.1 页面职责

不是“数据统计”。

而是回答：

> **我到底是怎么度过这段时间的？**

---

## 11.2 默认视图

默认：

```text
Day
```

而不是 Month Dashboard。

---

## 11.3 Daily Timeline

```text
September 23

Summary
────────────────

6 Tasks
2 Agent Runs
1 Decision
3 Artifacts

────────────────

09:32
DailyPlanConfirmed

10:14
Task Completed

11:03
Decision Created

13:21
Agent Started

14:02
Artifact Created

...

────────────────

今天完成

今日决策

未完成

[修改日报]

[结束今天]
```

---

## 11.4 周 / 月 / 年

切换：

```text
Day
Week
Month
Year
```

Month 示例：

```text
Completed Tasks
Agent Runs
Decisions
Artifacts

Project Distribution

Work Trend

Milestones

AI Monthly Summary
```

---

## 11.5 History 搜索

未来必须支持自然语言：

```text
我上个月 Personal OS 做了什么？

什么时候决定先不做 Plugin Marketplace？

最近三个月 Agent 开发推进了什么？
```

Personal Work Graph 将为这些问题提供上下文。

---

# 12. Settings 页面

Settings 不作为核心高频页面，但 V0.1 需要具备基础配置。

---

## 12.1 Theme

```text
Theme

Auto by Time     ON

10:00–14:00
Morning Theme

14:00–20:00
Afternoon Theme

Other
Night Theme
```

允许以后切换：

```text
Auto
Manual
```

---

## 12.2 Personal Rules

例如：

```text
Daily Log

✓ 被动浏览网页不算完成事项
✓ Agent Task 默认需要 Review
✓ 论文阅读只有产生笔记才算完成
```

支持：

```text
Edit
Disable
Delete
```

---

## 12.3 Connector

未来：

```text
Obsidian
GitHub
Calendar
Gmail
Drive
```

V0.1 可以只做少量。

---

## 12.4 Agent Runtime

```text
Runtime

Multica
Codex
Research Agent
...
```

---

# 13. 全局核心对象

V0.1 数据对象：

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

---

# 14. 页面关系

整个产品主链：

```text
                    Intelligence
                         │
                         ▼
Morning Brief → Task → Project
                   │
                   ▼
                 Agent
                   │
                   ▼
                 Review
                   │
                   ▼
               Daily Log
                   │
                   ▼
                 History
                   │
                   ▼
          Personal Work Graph
                   │
                   └────→ Tomorrow Morning Brief
```

---

# 15. 统一组件

三套主题共享：

## Navigation

- Sidebar
- Command Bar
- Top Actions
- User Menu

## Task Components

- Task Row
- Task Card
- Task Detail
- Status Pill
- Priority Badge
- Agent Badge

## Project Components

- Project Card
- Project Pulse
- Milestone
- Decision Item

## Intelligence

- Intelligence Card
- Source Badge
- Why Recommended
- Channel Chip

## Review

- Review Queue Item
- Review Detail
- Approval Action Bar

## History

- Activity Timeline
- Daily Log
- Metric Card
- Trend Chart

---

# 16. 统一交互原则

## 16.1 少跳转

Task、Review 等高频场景优先：

> 列表 + 右侧 Detail Panel

避免大量整页跳转。

---

## 16.2 AI 有建议权，不拥有最终决定权

所有重要操作：

```text
AI Suggest
↓
User Review
↓
Execute
```

---

## 16.3 自动生成必须可修改

包括：

- Morning Brief
- Project Pulse
- Daily Log
- Personal Rules
- Intelligence Ranking

---

# 17. 动效建议

三套主题可以有不同的轻量动效。

## Morning

- 水波
- 光线
- 漂浮粒子
- 白鸟
- 透明卡片轻微浮动

## Afternoon

- 红色粒子
- 缓慢花瓣
- 细微光线扫过
- 荆棘发光
- 卡片边缘红色呼吸灯

## Night

- 深海波纹
- Cyan 粒子
- 很弱的背景流体
- 微弱呼吸发光
- Abyss Creature 轮廓缓慢变化

注意：

> 动效只增加氛围，不能影响工作效率。

---

# 18. 页面开发优先级

推荐：

```text
1. Today
2. Tasks
3. Projects
4. Review
5. History
6. Intelligence
7. Settings
```

原因：

### Phase 1

```text
Today
Tasks
Projects
```

验证：

> Plan → Work

### Phase 2

```text
Agent
Review
```

验证：

> Task → Agent → Review

### Phase 3

```text
History
```

验证：

> Work → Remember

### Phase 4

```text
Intelligence
```

补充外部信息输入。

---

# 19. V0.1 UI 判断标准

任何新的页面模块或组件，都先问：

1. 是否让 Morning Brief 更有效？
2. 是否让 Task 更容易完成？
3. 是否让 Agent 执行更清晰？
4. 是否让 Review 更有效率？
5. 是否让 Daily Log 更准确？
6. 是否让 Personal Work Graph 更有价值？

如果全部否：

> **不做。**

---

# 20. 产品 UI 核心表达

Personal OS 最终不是一个普通效率 Dashboard。

它应该让用户感受到：

> **这是属于博士自己的数字工作空间。**

三个时间主题只是它不同时间下的状态：

```text
Morning
清澈、平静、规划

Afternoon
强烈、推进、创造

Night
沉静、专注、复盘
```

但核心工作流永远保持一致：

> **Plan → Work → Agent → Review → Remember**

最终所有工作都会进入：

> **Personal Work Graph**
