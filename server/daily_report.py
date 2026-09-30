from __future__ import annotations

import json
import re
from typing import Any

PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}


def todo_line(todo: dict[str, Any]) -> str:
    tag = "" if todo.get("priority", "medium") == "medium" else f"[{PRIORITY_LABELS.get(todo['priority'], '中')}] "
    carried = f"（已拖 {todo['carried_days']} 天）" if todo.get("carried_days") else ""
    return f"- {tag}{todo['title']}{carried}"


def draft_text(facts: dict[str, Any]) -> str:
    """Rule-based fallback: the same two sections the model writes, built only from recorded facts."""
    summary = ["## 今日工作总结", "", "完成：", *([f"- {x}" for x in facts["done"]] or ["- 暂无"])]
    if facts["decisions"]:
        summary += ["", "决策：", *[f"- {x}" for x in facts["decisions"]]]
    if facts["artifacts"]:
        summary += ["", "产物：", *[f"- {x}" for x in facts["artifacts"]]]
    if facts["cards_reviewed"]:
        summary += ["", f"学习：复习了 {facts['cards_reviewed']} 张卡片"]
    if facts["blocked"]:
        summary += ["", "阻塞与执行异常（需要处理）：", *[f"- {x}" for x in facts["blocked"]]]
    if facts["traces"]:
        summary += ["", "代码与会话痕迹（仅供核对，不自动计为完成）："]
        for project, trace in facts["traces"].items():
            counts = "、".join(x for x in (f"{len(trace['commits'])} 次提交" if trace["commits"] else "", f"{len(trace['sessions'])} 段会话" if trace["sessions"] else "") if x)
            latest = "；".join((trace["commits"] or trace["sessions"])[:3])
            summary.append(f"- {project}：{counts}" + (f"，最近：{latest}" if latest else ""))
    if facts["notes"]:
        names = "、".join(facts["notes"][:5]) + (" 等" if len(facts["notes"]) > 5 else "")
        summary += ["", f"知识库变更（仅供核对，不自动计为完成）：{len(facts['notes'])} 篇笔记，{names}"]
    if facts["external"]:
        summary += ["", f"外部资料收录/更新（不计为任务完成）：{'、'.join(facts['external'][:5])}"]
    plan = [todo_line(x) for x in facts["unfinished"]]
    plan += [todo_line(x) for x in facts["pool_high"]]
    plan += [f"- {'验收' if task['status'] == 'Review' else '处理失败的'} Agent 任务：{task['title']}" for task in facts["agent_tasks"]]
    return "\n".join(summary + ["", "## 明日工作计划", "", *(plan or ["- 暂无安排，明早从待办池里挑选"])])


def report_prompt(day: str, facts: dict[str, Any], rules: list[str], draft: str) -> str:
    prompt = (f"你在为用户写 {day} 的工作日报。根据下面的真实数据，用中文输出 Markdown，只包含两个二级标题：\n"
              "## 今日工作总结\n## 明日工作计划\n\n"
              "要求：\n"
              "1. 今日工作总结是归纳不是流水账：按项目或主题写做成了什么、推进到哪一步、有哪些产出和决策，3 到 8 条。"
              "代码提交和 Agent 会话只是推进的线索，要归纳成成果，不要逐条罗列；Obsidian 笔记变化和外部资料也只是线索，不算完成。"
              "有阻塞或执行异常时单独写一条。\n"
              "2. 明日工作计划 3 到 6 条，按轻重排序：先写今天没完成的待办（高优先级在前，拖了多天的要点明），"
              "再写待办池里的高优先级待办和待验收或失败的 Agent 任务。每条写清楚要做的具体动作。\n"
              "3. 不得虚构数据里没有的工作。\n")
    if rules:
        prompt += "4. 必须遵守下面的个人规则：\n" + "\n".join(f"- {x}" for x in rules) + "\n"
    prompt += "\n【当天数据】\n" + json.dumps(facts, ensure_ascii=False, indent=1) + "\n"
    if draft:
        prompt += "\n【当前草稿】（用户可能改过，其中补充的信息可以采用）\n" + draft[:6000] + "\n"
    return prompt + "\n不要读写任何文件，不要运行命令。只输出日报正文。"


def clean_report(text: str) -> str:
    text = text.strip()
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*)\n```", text, re.S)
    return fenced.group(1).strip() if fenced else text
