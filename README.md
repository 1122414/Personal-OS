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

Intelligence 频道支持每行一个 RSS/Atom 来源地址、关注关键词、排除关键词和每日上限。刷新后，来源、推荐原因与用户反馈会保存在本地。

```sh
python3 -m unittest discover -s tests -v
npm run build
```

产品说明见 [V0.1 产品设计](docs/Personal-OSV0.1产品设计.md)，视觉参考见 [参考素材索引](docs/reference-assets/README.md)。
