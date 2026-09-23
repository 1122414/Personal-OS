# Personal OS MVP 实施与验收计划

## 范围

以 V0.1 产品设计为验收依据，交付可在本机运行的桌面 Web 应用。Personal OS 是通用产品；「博士」与浊心斯卡蒂属于可配置的当前个人主题。页面覆盖 Today、Tasks、Projects、Intelligence、Review、History、Settings，三套主题保持同一业务结构。

## 阶段

1. 数据与每日闭环：持久化 Project、Task、DailyPlan、DailyLog、Decision、ActivityEvent；确认计划后任务进入 Today；人工任务可完成；日报由真实事件生成并由用户确认。验收：重启后状态仍在，事件顺序可追踪。
2. Agent 与审核：Task 发起 AgentRun，状态/结果回到 Task；执行结束进入 Review；用户确认、继续修改或重跑；Artifact 和知识写入均需单独审核。验收：Agent 完成不自动使 Task 完成。
3. 情报与个性化：频道边界、信息源、筛选反馈、推荐原因；规则可增删改禁用；主题按时间/手动切换，称呼可改；Obsidian 读取与批准后写入。验收：配置持久化，写入无静默自动发生。
4. UI 与端到端验证：按照参考图实现共用布局和三套主题，主要交互可用；浏览器验证主闭环、响应式、键盘与状态一致性，并修复视觉和功能偏差。

## 输入依赖

项目当前没有应用代码。用户已给出 Obsidian vault 路径 `/Users/geminchen/Documents/MyKnowledgeBase/Obsidian`；本机检测到 Codex 和 Multica CLI。模型服务的具体配置尚未给出；使用适配器和显式配置，缺失时展示可操作的未配置状态，不伪造外部执行成功。核心本地工作流不依赖外部服务。

## 验证边界

7 天使用指标需实际使用后才能判断；它是产品方向验证，不可由一次自动化测试宣称达成。
