# Personal OS UI 参考素材

## 产品定位与使用方式

Personal OS 面向通用个人工作场景。「博士」只是当前开发者选择的《明日方舟》主角称呼，浊心斯卡蒂是当前个性化主题角色，不是固定用户身份或产品定位。后续实现应区分通用产品功能与可配置的称呼、主题和角色素材。

首页三张图由用户提供，原样保存。内页使用内置 imagegen 逐页生成，每页依次完成晨间、午后、夜间三个独立文件。图片用于视觉与布局参考，并非可交互页面；文字、日期、数量、检查结果、连接状态均为示例，不代表已实现的能力或实际运行结果。业务行为以产品需求和用户最新指示为准。

参考图中的日历、相册、习惯打卡等入口不自动纳入 V0.1。内页统一使用 Today、Tasks、Projects、Intelligence、Review、History 和 Settings。

## 主题映射

| 主题 | 用户原图 | 时间 | 视觉 |
|---|---|---|---|
| morning | 图 1 | 10:00–14:00 | 银白、海蓝、青绿、海洋圣域 |
| afternoon | 图 3 | 14:00–20:00 | 赤色剧场、玫瑰、荆棘、哥特圣堂 |
| night | 图 2 | 其余时间 | 深海黑蓝、青色荧光、少量血红 |

映射依据视觉设计，不依据原图中问候文字。首页原图中的「漂泊的旅人」等文字原样保留，不作为新页面称呼要求。

## 页面索引

| 页面 | 晨间 | 午后 | 夜间 |
|---|---|---|---|
| 首页（用户原图） | [图片](home/morning.png) | [图片](home/afternoon.png) | [图片](home/night.png) |
| 任务 Tasks | [图片](tasks/morning.png) | [图片](tasks/afternoon.png) | [图片](tasks/night.png) |
| 项目 Projects | [图片](projects/morning.png) | [图片](projects/afternoon.png) | [图片](projects/night.png) |
| 情报 Intelligence | [图片](intelligence/morning.png) | [图片](intelligence/afternoon.png) | [图片](intelligence/night.png) |
| 审核 Review | [图片](review/morning.png) | [图片](review/afternoon.png) | [图片](review/night.png) |
| 历史 History | [图片](history/morning.png) | [图片](history/afternoon.png) | [图片](history/night.png) |
| 设置 Settings | [图片](settings/morning.png) | [图片](settings/afternoon.png) | [图片](settings/night.png) |

## 生成规格

[基础提示词与主题输入](prompts.json)保存每张图的主要提示词、主题参考图与输出相对路径。生成时还加入了对同页晨间布局和 Tasks 内页外框的保持要求。

生成式参考图的文字、图标、边框与布局不能保证像素级一致；正式实现时用共享组件和主题 Token 固定结构，不能直接把整张参考图当作产品交互实现。
