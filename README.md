# Personal OS

本地优先的个人工作台。围绕每日计划、任务执行、Agent 审核与日报，持续记录可追溯的工作轨迹。应用功能面向通用用户；「博士」和浊心斯卡蒂是当前可配置的个人主题。

## macOS 客户端

构建需要 macOS、Swift 命令行工具、Python 3.12+，以及 Node.js 20.19+ 或 22.12+。在项目根目录执行：

```sh
npm ci
./scripts/build-macos-app.sh
open 'build/Personal OS.app'
```

构建结果是 `build/Personal OS.app`，可从 Finder 双击打开。界面在独立客户端窗口运行；应用自动启动仅监听本机的后台服务并在退出时停止。它仍需本机安装 Python 3.12+，当前构建不包含独立的 Python 运行时。重新构建应用会更新界面和服务代码，不会删除用户数据。

客户端数据保存在 `~/Library/Application Support/Personal OS/personal-os.sqlite3`。首次启动时，若原网页原型的 `data/personal-os.sqlite3` 存在且客户端数据尚不存在，会复制原数据一次；不会覆盖客户端已有数据。诊断日志位于同目录的 `desktop.log`。

开发前端或 API 时，仍可分别运行 `python3 -m server.app` 和 `npm run dev`；开发服务器会将 `/api` 代理到本地后端。网页原型的数据默认保存在 `data/personal-os.sqlite3`，与客户端数据分开。

可在 Settings 中填写 Obsidian vault 路径，或首次启动前设置 `PERSONAL_OS_OBSIDIAN_VAULT` 环境变量。应用只读取 Markdown 文件变化；写入必须从 Review 中批准，目标为 vault 内的 `Personal-OS/` 文件夹，已有同名文件不会覆盖。

Agent 任务需要在所属项目中设置本地工作目录，且本机已登录 Codex CLI。点击“交给 Codex”后在该目录执行；结果返回 Review，只有人工确认才将任务标为完成。AI 简报、项目脉搏和日报整理也通过本机 Codex CLI 生成。若运行时不可用，基本计划与日报仍根据本地事件运行，并明确显示执行错误。

Agent 执行时会将任务描述交给 Codex；AI 建议会发送相关任务、项目、决策与规则上下文。系统对工作目录做执行前后快照，在 Review 中列出检测到的文件变更，跳过隐藏目录和常见依赖/构建目录，最多记录 20,000 个文件。确认 Agent 结果前应核对真实工作目录。HTTP API 只监听本机，并拒绝非本机来源的写请求。

Intelligence 频道支持每行一个 RSS/Atom 来源地址、关注关键词、排除关键词和每日上限。刷新后，来源时间、收录时间、刷新错误与用户反馈保存在本地；忽略项不进入简报，收藏/忽略暂不训练推荐模型。

AI 日报直接读取 Obsidian 已落盘的 Markdown：默认 `每日AI/YYYY-MM-DD/*.md`，可在 Settings → AI 日报来源修改 vault 内的相对子目录。Today 展示最新一期入口，Intelligence 默认打开 AI 日报，支持按日期阅读全文；每 30 秒检查文件更新，也可手动刷新。今天尚无报告时明确显示最新报告日期。报告只读，工作台中的勾选框只展示原笔记状态；不会修改原笔记。支持常用 Markdown、表格、代码和 HTTP(S) 原文链接，HTML 作为文字显示、图片不自动加载。最多展示最近 366 个日期目录和 2,000 篇，单篇上限 512 KB，超限显示提示。

WorkBuddy 会话作为可选历史入口保留在 Intelligence → 历史会话；会话摘要不进入首页或 AI 简报。Settings 中可以展开会话同步配置，但读取 AI 日报不依赖它。当前本机已停止原会话自动同步。该适配仍针对 WorkBuddy 5.6 本地格式，已导入数据保留；不读取认证/推理/工具日志，不修改源数据。

Settings → 外观主题可调整 0–100% 的界面背景透明度，拖动即时预览，保存后跨重启保留，三套主题共用。透明度作用于面板与侧栏背景，文字保持不透明。

Today 支持挑选已有任务、排序和修订待办计划；已经执行的项目保留事实。History 按日期加载完整事件，日报出现新事件后提示过期，刷新保留旧稿，确认前需核对。过去日期可以补记；自动化仍只在应用运行时工作。

Settings 提供数据库备份、JSON 导出及恢复入口。恢复前自动保留当前数据库，运行任务期间禁止恢复。备份不包含项目文件与 Obsidian 笔记。Tasks 可归档、恢复和重开任务。

本轮实际修复范围、35 项测试及首次使用步骤见 [修复与 WorkBuddy 验收报告](docs/2026-09-29_repair-verification.md)。

```sh
python3 -m unittest discover -s tests -v
npm run build
```

产品说明见 [V0.1 产品设计](docs/Personal-OSV0.1产品设计.md)，视觉参考见 [参考素材索引](docs/reference-assets/README.md)。

本次透明度和日报成品阅读的验收见 [主题与 AI 日报阅读](docs/2026-09-29_theme-and-daily-reports.md)。
