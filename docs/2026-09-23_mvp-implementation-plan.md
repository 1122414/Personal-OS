# Personal OS MVP 实施与验收计划

## 范围

以 V0.1 产品设计为验收依据，交付可在本机运行的桌面 Web 应用。Personal OS 是通用产品；「博士」与浊心斯卡蒂属于可配置的当前个人主题。页面覆盖 Today、Tasks、Projects、Intelligence、Review、History、Settings，三套主题保持同一业务结构。

## 阶段

1. 数据与每日闭环：持久化 Project、Task、DailyPlan、DailyLog、Decision、ActivityEvent；确认计划后任务进入 Today；人工任务可完成；日报由真实事件生成并由用户确认。验收：重启后状态仍在，事件顺序可追踪。
2. Agent 与审核：Task 发起 AgentRun，状态/结果回到 Task；执行结束进入 Review；用户确认、继续修改或重跑；文件产物随 Agent 结果一起展示并由用户确认，知识写入另行审核。验收：Agent 完成不自动使 Task 完成。
3. 情报与个性化：频道边界、信息源、筛选反馈、推荐原因；规则可增删改禁用；主题按时间/手动切换，称呼可改；Obsidian 读取与批准后写入。验收：配置持久化，写入无静默自动发生。
4. UI 与端到端验证：按照参考图实现共用布局和三套主题，主要交互可用；浏览器验证主闭环、响应式、键盘与状态一致性，并修复视觉和功能偏差。

## 输入依赖

用户已给出 Obsidian vault 路径 `/Users/geminchen/Documents/MyKnowledgeBase/Obsidian`，已保存在本机数据设置中。本机 Codex CLI 已登录并通过真实调用验证；V0.1 只接入 Codex。核心任务与日报草稿在 Codex 不可用时仍可本地运行；AI 生成按钮与 Agent 执行会明确显示错误。

## 实施验收记录（2026-09-23）

| 阶段 | 已观察结果 | 证据 |
|---|---|---|
| 数据与每日闭环 | 在隔离数据库中完成建项目、建任务、确认今日计划、完成任务、修改与确认日报；状态重启后保留 | 浏览器操作与 `tests/test_store.py` |
| Agent 与审核 | 真实 Codex 在隔离工作目录创建、修改文件；任务只进入 Review，产物显示待审核，用户确认后完成 | 隔离浏览器验收与 `test_agent_result_waits_for_user_review` |
| 情报、主题、知识库 | 频道与情报可创建；三主题切换和空称呼生效；知识提案获批前无文件，批准后写入隔离 vault；真实 vault 仅验证连接 | 浏览器操作、`tests/test_feeds.py`、`tests/test_store.py` |
| AI 与界面 | 实际 Codex 返回可解析的每日建议、项目脉搏与日报；手机宽度和桌面布局已检查 | 隔离 AI 数据库与浏览器验收；`npm run build`、14 项单元测试通过 |

## 验证边界

7 天使用指标需实际使用后才能判断；它是产品方向验证，不可由一次自动化测试宣称达成。
