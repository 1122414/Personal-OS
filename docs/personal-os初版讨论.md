# Personal OS 初版讨论

> 版本：V0.1 前期产品讨论整理  
> 目标：明确为什么做、要做什么、核心价值、V0.1 边界，以及后续产品设计的第一性原则。

---

## 1. 为什么要做 Personal OS

当前日常工作存在三个核心问题：

### 1.1 信息分散
每天需要查看每日笔记、待办、项目状态、新闻与 AI 信息，但这些内容分散在 Obsidian、Todo 软件、浏览器、不同信息源中。

这意味着每天开始工作前，需要主动打开多个软件、寻找信息、回忆上下文。

### 1.2 Agent 分散
不同任务需要分别打开 Codex、Research Agent、其他 Agent 等工具。

例如：

- 让 Codex 修改某个项目
- 让 Research Agent 调研 Gemini 新版本
- 让 Agent 总结论文或项目资料

现在的工作方式是“人去找 Agent”，而不是“Task 进入统一系统后由系统分发给 Agent”。

### 1.3 缺少统一工作入口
笔记、待办、项目、新闻、Agent、工作记录全部属于不同系统，没有一个真正统一的入口。

目标不是简单做一个“导航页”，而是希望：

> 80% 的日常工作操作尽量不离开 Personal OS。

外部软件仍然可以存在，但它们应该逐渐成为 Personal OS 的数据源、知识库、执行器或插件能力。

---

# 2. 产品真正要解决的问题

经过讨论后，产品核心不再定义为“多 Agent 管理平台”。

更准确的定义是：

> **Personal OS 是一个以 Personal Work Graph 为核心的个人工作操作系统：每天早上告诉我该关注什么、该做什么；白天承接我的 Task 并调度 Agent 执行；晚上根据真实工作行为形成记录，最终持续积累属于我自己的工作轨迹。**

它不是：

- Notion 替代品
- Obsidian 替代品
- Todo 软件
- 单纯的 Agent Dashboard
- Multica 的换皮
- 一个把所有 AI 图标放在一起的工具

这些都只是 Personal OS 的外围能力。

---

# 3. 产品核心价值

Personal OS 的核心价值不是“把所有软件放到一个页面”。

真正的核心是：

> **我不应该每天主动去不同软件寻找“我今天该干什么”。信息和工作应该主动汇聚到我面前。**

当前模式：

```text
我
 ↓
打开 Obsidian
 ↓
找日报
 ↓
打开 Todo
 ↓
找待办
 ↓
看新闻
 ↓
回忆项目状态
 ↓
打开 Codex / 其他 Agent
 ↓
找昨天执行结果
```

Personal OS 目标模式：

```text
Obsidian ─────┐
新闻源 ───────┤
Projects ─────┤
Tasks ────────┤
Agent Runs ───┤
昨天的工作 ───┤
              ↓
        Personal OS
              ↓
             我
```

系统主动组织信息，人只需要做最终判断。

---

# 4. 核心原则

## 4.1 Task 是一等公民

Agent 不是核心对象。

> **Agent 是劳动力，Task 才是一等公民。**

任何 Agent 工作都应该从 Task 出发。

```text
Task
 ↓
选择 / 自动选择 Agent
 ↓
Agent Run
 ↓
结果返回 Task
 ↓
Review
```

第一版不要求在 Personal OS 里完整复刻 Codex / Claude Code 的交互界面。

---

## 4.2 Project 状态由系统自动总结，但用户拥有最终修改权

系统应该自动生成“项目态势”，而不是要求用户手工维护进度条。

例如：

> Personal OS：昨日完成需求梳理，目前进入 V0.1 产品设计阶段，存在 2 个未完成 Task。

用户可以手动修改。

一旦用户修改，就应该形成一个明确的 Decision。

---

## 4.3 Decision 是一等公民

例如：

> V0.1 暂不开发插件市场，优先完成 Today 闭环。

这不应该只是一次聊天内容，而应该沉淀为：

```text
Decision
- 内容：V0.1 不做 Plugin Marketplace
- 日期：2026-09-22
- 状态：Active
```

后续 Morning Brief、项目状态、AI 建议都应该尊重这个 Decision，直到用户主动修改或废弃。

---

## 4.4 Personal Rules 必须透明

系统通过用户不断纠偏，逐渐形成 Personal Rules。

例如：

> “不要把浏览网页写进 Daily Log。”

最终形成：

```text
Daily Log Rule:
被动浏览行为不计入完成事项。
```

原则：

- 用户可查看
- 用户可修改
- 用户可禁用
- 用户可删除
- 自然语言为主
- 系统内部可以自动结构化
- 用户不需要写代码

不接受“AI 神秘地越来越懂我”这种黑盒 Memory。

---

## 4.5 AI 有建议权，没有最终决定权

Morning Brief 可以建议今天做什么，但必须经过用户确认。

流程：

```text
系统分析
 ↓
给出今日建议
 ↓
用户修改 / 删除 / 调整
 ↓
【确认今日计划】
 ↓
进入 Today Tasks
```

---

## 4.6 重要知识沉淀需要审核

Task 执行结束后，系统可以提示：

> 这个结果可能值得沉淀为知识。

用户选择：

- 保存到 Obsidian
- 仅保留在 Task
- 暂不处理

系统不能默认把所有结果自动写入知识库，避免知识噪声。

---

# 5. Personal Work Graph

经过讨论，Personal Work Graph 是整个产品真正长期有价值的资产。

它不是后续增加的一个“图谱页面”，而应该成为 Personal OS 的底层数据模型。

核心对象包括：

| 对象 | 含义 |
|---|---|
| Project | 长期推进的工作 |
| Task | 当前具体要完成的事项 |
| Agent Run | Agent 为某个 Task 做的一次执行 |
| Decision | 用户明确做出的判断或方向选择 |
| Artifact | Task 产生的代码、文档、报告等 |
| Intelligence | 外部世界值得关注的信息 |
| Daily Log | 当天真正完成了什么 |
| Personal Rule | 系统理解和协助用户的行为规则 |

关系示例：

```text
Project
   │
   ├── Task
   │     │
   │     ├── Agent Run
   │     │      └── Artifact
   │     │
   │     ├── Decision
   │     └── Knowledge
   │
   ├── Decision
   └── Daily Log
```

长期价值不是“存了多少笔记”，而是：

- 做过哪些项目
- 做过哪些任务
- 做过哪些重要决策
- 哪些任务失败过
- 哪类任务交给哪个 Agent 效果最好
- 调研过什么
- 最终产生了什么
- 为什么后来改变方向
- 每一天是如何度过的

这构成属于用户自己的数字工作历史。

---

# 6. V0.1 唯一核心闭环

V0.1 不追求“80% 工作都能完成”。

第一版只需要完整跑通下面这一条链：

```text
昨日工作
   +
当前 Projects
   +
Todo / Deadline
   +
Intelligence Brief
   ↓
Morning Brief
   ↓
AI 提议今日计划
   ↓
用户修改
   ↓
【确认今日计划】
   ↓
Today Tasks
   ↙        ↘
自己做     Agent 做
             ↓
         Agent Run
             ↓
           Review
             ↓
         确认完成
             ↓
 Artifact / Decision
             ↓
   是否沉淀为知识？
             ↓
       Evening Scan
             ↓
       自动 Daily Log
             ↓
          用户纠偏
             ↓
       Personal Rules
             ↓
           第二天
```

---

# 7. Morning Brief

Morning Brief 是产品第一入口。

首页不应该首先显示传统 Dashboard 指标，例如：

- 12 Tasks
- 3 Agents Running
- 7 Projects
- 42 Articles

首页首先需要回答：

> **所以我今天应该干嘛？**

建议结构：

```text
今天建议优先完成：

① Personal OS V0.1 产品设计
原因：昨日已完成需求收敛，当前进入设计阶段

② XXX 项目任务
原因：Deadline 临近

③ 阅读 XXX 论文
原因：与你最近关注的 Agent Runtime 方向高度相关
```

用户可以：

- 删除
- 修改
- 调整顺序
- 新增任务

然后点击：

> 【确认今日计划】

确认后才正式进入 Today Tasks。

---

# 8. 首页核心模块

目前确认首页第一版只需要：

1. Morning Brief
2. 今日 Todo
3. Intelligence
4. Project Pulse

其中 Morning Brief 位于最上方，其他模块为辅助信息。

---

# 9. Intelligence，而不是 News Feed

Personal OS 不应该重新制造一个新闻信息流。

正确方向是：

> **Channel-based Intelligence**

例如：

- AI
- Agent
- 互联网
- 金融
- 产品

每个 Channel 由四部分决定：

```text
边界
+
信息源
+
筛选规则
+
用户反馈
```

核心原则：

> **用户定义边界，系统在边界内学习。**

系统可以根据以下行为学习：

- 点击
- 收藏
- 忽略
- 深入研究
- 创建 Task

但不允许 AI 完全自由决定“你应该喜欢什么”。

每条 Intelligence 应支持：

- 忽略
- 收藏
- 深入研究
- 创建 Task
- 关联 Project

---

# 10. Agent 集成边界

V0.1 的 Agent 能力只要求：

```text
Personal OS 创建 Task
 ↓
交给 Multica / Codex 等 Agent Runtime
 ↓
执行
 ↓
返回状态
 ↓
返回最终结果
 ↓
进入 Review
```

暂时不做：

- 完整 Agent IDE
- 在 Personal OS 内复刻 Codex
- 高级多轮 Agent 工作台
- 复杂 Agent Workflow

外部 Agent 只是执行器。

---

# 11. Agent Task Review

V0.1 阶段：

> **所有 Agent 任务默认进入 Review。**

Task 生命周期初版：

```text
Inbox
 ↓
Planned
 ↓
Running
 ↓
Review
 ↓
Done / Blocked
```

Agent 完成任务不等于 Task 自动完成。

必须经过用户确认。

---

# 12. Daily Log

晚上系统定时扫描当天工作行为，自动生成 Daily Log。

第一版主要读取：

1. Personal OS 内部的 Task / Agent 行为
2. 从 Personal OS 发起的 Agent 对话 / 结果
3. Obsidian 文件变化

暂时不扫描：

- ChatGPT 外部聊天
- Claude 独立聊天
- 其他外部软件中的独立聊天

Daily Log 示例：

```text
2026-09-22

今天完成：
- 完成 Personal OS 产品需求梳理
- Codex 完成 XXX 功能
- 阅读 XXX 论文
- 修改 Agent 简历

产出：
- XXX.md
- PR #12
- 产品决策 3 项

未完成：
- Multica Demo

今日主要投入：
- Personal OS
- 求职
- Agent 学习
```

用户进行确认和纠偏。

---

# 13. Activity / Event Ledger

为了让 Daily Log 和 Personal Work Graph 更可靠，系统从 V0.1 就应该维护 Activity / Event Ledger。

例如：

```text
09:42 TaskCreated
10:03 AgentRunStarted
10:34 ArtifactCreated
10:41 TaskReviewed
11:12 DecisionCreated
14:26 ObsidianFileChanged
16:03 TaskCompleted
```

晚上通过：

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

Activity Ledger 是后续 Personal Work Graph 的基础。

---

# 14. Obsidian 的角色

Obsidian 只是知识库，不是 Personal OS 本身。

第一版只需要：

- 读取 Daily Note
- 读取文件变化
- 读取相关知识
- 在用户明确审批后写入内容

不需要：

- 重做 Obsidian
- 做 Notion 式编辑器
- 做完整知识库 UI

---

# 15. V0.1 明确不做

以下功能全部从 V0.1 删除：

- 插件市场
- Notion 式笔记编辑器
- 完整 Calendar
- Workflow Builder
- 完整 Agent IDE
- 多用户协作
- 手机 App
- 无审核自动写入 Obsidian
- 接几十种 Agent
- 复杂数据 Dashboard

插件化可以在架构层预留接口，但第一版不做 Marketplace。

---

# 16. V0.1 成功标准

7 天使用后，满足下面三条就认为方向成立：

### 成功标准 1
不再每天主动打开 Obsidian 找日报。

### 成功标准 2
每天打开电脑后的第一入口，从微信 / 浏览器等工具变成 Personal OS。

### 成功标准 3
80% 的 Agent 任务从 Personal OS 发出，并且结果回到 Personal OS。

---

# 17. 产品长期目标

Personal OS 最终最重要的资产，不是页面，也不是某一个 Agent。

而是：

> **Personal Work Graph / 个人工作轨迹。**

它持续记录：

- 我做过什么
- 为什么做
- 谁帮我做
- 产生了什么
- 什么被我否决
- 什么被沉淀
- 我的规则如何变化
- 我的项目如何演进

即使未来：

- 换掉 Multica
- 换掉 Codex
- 换掉 Obsidian
- 换掉某个模型

Personal OS 本身依然有价值。

---

# 18. 判断新需求是否应该加入

以后任何新功能，都先问四个问题：

1. 它能不能让 Morning Brief 更准？
2. 它能不能让 Task 更顺畅地完成？
3. 它能不能让 Daily Log 更准确？
4. 它能不能让 Personal Work Graph 更有价值？

如果四个全部是否定：

> 不做。

---

# 19. 产品哲学

最后将 Personal OS 压缩成五个词：

> **Plan → Work → Agent → Review → Remember**

- Plan：早上确认今天做什么
- Work：白天推进任务
- Agent：需要时交给 Agent
- Review：结果由人确认
- Remember：沉淀为长期可控的工作轨迹

这里的 Remember 不是黑盒 AI Memory，而是：

> **结构化、可查看、可修改、可以长期积累的 Personal Work Graph。**

---

# 20. 下一阶段

下一阶段进入：

> **Personal OS V0.1 产品设计**

重点设计：

- Today
- Task
- Project
- Review
- Daily Log
- Intelligence
- Personal Rules
- Activity Ledger
- Personal Work Graph

并将页面、数据模型、交互流程、Agent Runtime 与 Connector 架构逐一对应。
