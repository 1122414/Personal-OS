# 学习卡片与 WorkBuddy 通道计划

日期：2026-09-30

## 目标

1. 学习主题下有卡片：正面问题或概念，背面解答，可以读也可以自测。
2. 卡片可以自己写、编辑、删除；也可以让 AI 每天按主题推送新卡片。
3. 复习按记忆程度排期，首页「今日学习」集中处理今天的新卡片和到期复习。
4. 当天新卡片同时写进 Obsidian。
5. 接入 WorkBuddy：既能生成学习卡片，也能作为「Agent 任务」的派单通道。

用户已确认的选择：

- 在现有「学习」上扩展，并恢复侧栏入口（9/29 首页改版时被收起）。
- 卡片为正面问题/概念、背面解答。
- 复习：忘了明天再来，模糊 3 天，记得依次 7/14/30 天；在 30 天间隔上仍记得，标为「已掌握」不再出现，可手动恢复。
- AI 按主题目标生成：每个开启推送的主题每天 N 张（N 可设）。
- 推送出现在首页，并写入 Obsidian。
- 每个主题自己选生成通道：Codex、Kimi、Claude Code、Cursor、WorkBuddy。
- WorkBuddy 两处都能选。

## 已核对的前提

- 现有学习模块：主题（标题、目标、带着学/随问随答）、关联记录与资料、与 Codex 的对话、空闲后自动总结、每周想起旧点子。用户库里目前没有学习主题。
- 各通道已能在任意目录里以非交互方式运行并返回最后一段回复（`runtime.execute`）；Kimi、Claude Code、Cursor 在 `sandbox-exec` 下只能写工作目录和临时目录，Codex 用自带的工作区沙箱。
- 每日自动化线程每分钟一轮，8～20 点刷新情报和项目脉搏，可以挂每日推送。
- WorkBuddy 5.7.0 自带 CodeBuddy CLI 2.156.0（`WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy`，node 脚本），参数与 Claude Code 一致：`-p --output-format stream-json`、`-r <会话>`、`--permission-mode`、`--allowedTools`。CLI 登录与 WorkBuddy 应用分开，当前未登录，需要用户在终端运行一次并执行 `/login`。

## 设计

### 数据

- 主题新增：`push_enabled`（默认关）、`daily_count`（1～10，默认 3）、`card_engine`（默认 codex）、`last_push_date`、`last_push_error`。
- 新对象 `learning_card`：`topic_id`、`front`、`back`、`source`（user / ai）、`engine`、`step`、`due_date`、`last_rating`、`reviews`（最近 50 次）、`mastered_at`。
- 新卡片当天到期（作为今天的新卡片出现）。
- 评分：忘了 → 明天，回到第 0 级；模糊 → 3 天后，级别不变；记得 → 升一级，依次 7/14/30 天；已在 30 天这一级仍记得 → 已掌握。
- 删除主题不在本次范围；删除记录不影响卡片。

### 操作

- `create_card`、`update_card`、`delete_card`、`review_card`（rating：forgot / fuzzy / remembered）、`restore_card`（取消已掌握，明天再来）。
- `update_learning_topic` 接受推送设置。
- `generate_cards`：按主题目标和已有卡片正面（避免重复），让所选通道只输出 JSON 数组；在空的临时目录里运行，不碰任何项目。解析后去重、截断，保存为 AI 卡片。耗时操作，不持有全局锁。
- 状态里新增 `today_cards`：未掌握且到期的卡片，标出新卡片与复习。

### 每日推送

- 每日自动化在 8～20 点检查开启推送、且今天还没推送过的主题，逐个生成。无论成功失败都记下当天已尝试，失败原因写在主题上并显示，不会每分钟重试。
- 主题页有「现在生成」，手动再加 N 张。

### Obsidian

- 配置了仓库时，把当天新建的卡片按主题写到 `学习卡片/YYYY-MM-DD.md`，当天卡片有增删改时整份重写。未配置仓库时跳过并在主题页提示。目录是符号链接时拒绝写入。

### WorkBuddy 通道

- 新运行时 `workbuddy`：默认使用 WorkBuddy 自带的 codebuddy，也可在设置里填路径。
- 命令行与 Claude Code 相同的形式（stream-json、自动接受编辑、允许 Bash、`-r` 续接），`sandbox-exec` 只允许写工作目录、临时目录和它自己的状态目录（登录后实测确定）。
- 同时出现在 Agent 任务的通道选项和卡片生成通道里。

### 前端

- 侧栏恢复「学习」，位于待办和 Agent 任务之间。
- 主题页新增「卡片」页签：推送设置（开关、每天几张、生成通道）、现在生成、写一张卡片、卡片列表（编辑、删除、下次复习日期、来源）、已掌握区（恢复）。
- 首页「今日学习」：显示今天待学张数；逐张看正面 →「看答案」→ 忘了/模糊/记得；做完显示完成。

## 阶段

1. 计划文档（本文件）。
2. 后端：卡片、排期、推送设置、生成、每日推送、Obsidian 写入，附测试。
3. WorkBuddy 运行时：解析、沙箱、续接；用户登录后用 `/tmp` 仓库真实验证。
4. 前端：侧栏、卡片页签、首页今日学习。
5. 验证：`/tmp` 数据测试实例与 `/tmp` Obsidian 仓库真实生成一次、复习一轮、写入文件；验收记录、README、重建客户端。

## 验证边界

- 只在 `/tmp` 副本和 `/tmp` 仓库上真实运行，不写用户的真实数据库和 Obsidian 仓库。
- 真实生成会消耗所选通道的额度，每个通道只做最小次数。
