from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from server.store import Store
from server.traces import cursor_key, read_appended


def at(days_ago: int, hour: int = 10) -> datetime:
    day = datetime.now().astimezone() - timedelta(days=days_ago)
    return day.replace(hour=hour, minute=0, second=0, microsecond=0)


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.items = self.root / "items"
        self.items.mkdir()
        self.store = Store(self.root / "test.sqlite3")
        self.store.cursor_projects = self.root / "cursor"
        self.store.codex_sessions_root = self.root / "codex"
        self.store.action("save_settings", {"repo_scan_root": str(self.items)})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def repo(self, name: str) -> Path:
        path = self.items / name
        path.mkdir()
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        return path.resolve()

    def commit(self, path: Path, subject: str, when: datetime) -> None:
        (path / "log.txt").write_text(f"{(path / 'log.txt').read_text() if (path / 'log.txt').exists() else ''}{subject}\n")
        env = {**os.environ, "GIT_AUTHOR_DATE": when.isoformat(), "GIT_COMMITTER_DATE": when.isoformat()}
        subprocess.run(["git", "-C", str(path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", subject], check=True, env=env)

    def cursor_transcript(self, workspace: Path, when: datetime, question: str, answer: str) -> None:
        folder = self.store.cursor_projects / cursor_key(str(workspace)) / "agent-transcripts" / "s1"
        folder.mkdir(parents=True)
        hours = int(when.utcoffset().total_seconds() // 3600)
        stamp = f"{when.strftime('%A, %b %d, %Y, %I:%M %p')} (UTC{hours:+d})"
        lines = [
            {"role": "user", "message": {"content": [{"type": "text", "text": f"<timestamp>{stamp}</timestamp>\n<user_query>\n{question}\n</user_query>"}]}},
            {"role": "assistant", "message": {"content": [{"type": "text", "text": answer}]}},
        ]
        (folder / "s1.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))

    def codex_session(self, workspace: Path, when: datetime, question: str, answer: str) -> None:
        folder = self.store.codex_sessions_root / "2026" / "09"
        folder.mkdir(parents=True, exist_ok=True)
        utc = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        lines = [
            {"timestamp": utc, "type": "session_meta", "payload": {"cwd": str(workspace)}},
            {"timestamp": utc, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>x</environment_context>"}]}},
            {"timestamp": utc, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": question}]}},
            {"timestamp": utc, "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": answer}]}},
        ]
        (folder / "rollout.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))

    def trace_count(self) -> int:
        return self.store.db.execute("SELECT count(*) FROM activity WHERE type LIKE 'Trace%'").fetchone()[0]

    def test_H01_candidates_list_recent_repositories_and_register_in_one_step(self):
        active = self.repo("active")
        self.commit(active, "最近的提交", at(2))
        stale = self.repo("stale")
        self.commit(stale, "很久以前", at(40))
        (self.items / "plain").mkdir()
        result = self.store.action("list_repo_candidates", {})
        self.assertEqual([x["path"] for x in result["candidates"]], [str(active)])
        self.assertEqual(result["candidates"][0]["commits"], 1)
        registered = self.store.action("register_projects", {"paths": [str(active)]})
        project = registered["projects"][0]
        self.assertEqual((project["name"], project["workspace_path"]), ("active", str(active)))
        self.assertEqual(self.store.action("list_repo_candidates", {})["candidates"], [])
        self.assertEqual(self.store.action("register_projects", {"paths": [str(active)]})["projects"], [])

    def test_H02_H03_H04_last_work_groups_previous_active_day_by_project(self):
        alpha, beta, other = self.repo("alpha"), self.repo("beta"), self.repo("other")
        self.commit(alpha, "实现登录页", at(3))
        self.commit(beta, "修复同步", at(3, 15))
        self.commit(other, "未登记仓库的提交", at(1))
        self.cursor_transcript(alpha, at(3, 11), "帮我看登录页样式", "已调整按钮间距，下一步补表单校验")
        self.codex_session(beta, at(3, 16), "排查同步失败", "原因是时区换算")
        self.store.action("register_projects", {"paths": [str(alpha), str(beta)]})
        work = self.store.state()["last_work"]
        self.assertEqual(work["date"], at(3).date().isoformat())
        groups = {g["name"]: g for g in work["groups"]}
        self.assertEqual(set(groups), {"alpha", "beta"})
        self.assertEqual([c["title"] for c in groups["alpha"]["commits"]], ["实现登录页"])
        self.assertEqual(groups["alpha"]["sessions"][0]["title"], "帮我看登录页样式")
        self.assertIn("表单校验", groups["alpha"]["sessions"][0]["last_text"])
        self.assertEqual(groups["beta"]["sessions"][0]["label"], "Codex")
        self.assertEqual(groups["beta"]["sessions"][0]["title"], "排查同步失败")
        dump = json.dumps(work, ensure_ascii=False)
        self.assertNotIn("未登记仓库的提交", dump)
        self.assertNotIn("environment_context", dump)

    def test_codex_injected_context_and_review_subsessions_are_ignored(self):
        alpha = self.repo("alpha")
        self.commit(alpha, "提交", at(2))
        folder = self.store.codex_sessions_root / "2026" / "09"
        folder.mkdir(parents=True)
        utc = at(2).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        def message(role, text):
            kind = "input_text" if role == "user" else "output_text"
            return {"timestamp": utc, "type": "response_item", "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]}}
        main = [{"timestamp": utc, "type": "session_meta", "payload": {"cwd": str(alpha)}},
                message("user", "# AGENTS.md instructions for /x\n<INSTRUCTIONS>规则</INSTRUCTIONS>"),
                message("user", "# Context from my IDE setup:\n## Open tabs\n## My request for Codex:\n修一下导航"),
                message("assistant", "导航已修复")]
        review = [{"timestamp": utc, "type": "session_meta", "payload": {"cwd": str(alpha), "parent_thread_id": "p1"}},
                  message("user", "审核这个命令"), message("assistant", '{"risk_level":"low"}')]
        for name, lines in (("main.jsonl", main), ("review.jsonl", review)):
            (folder / name).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
        self.store.action("register_projects", {"paths": [str(alpha)]})
        sessions = self.store.state()["last_work"]["groups"][0]["sessions"]
        self.assertEqual([(x["title"], x["last_text"]) for x in sessions], [("修一下导航", "导航已修复")])

    def test_unmatched_sessions_are_listed_separately(self):
        alpha = self.repo("alpha")
        self.commit(alpha, "提交", at(2))
        self.codex_session(self.root / "elsewhere", at(2, 12), "别的目录里的问题", "回答")
        self.store.action("register_projects", {"paths": [str(alpha)]})
        work = self.store.state()["last_work"]
        self.assertEqual([x["title"] for x in work["unassigned_sessions"]], ["别的目录里的问题"])

    def test_repeated_sync_does_not_duplicate_traces(self):
        alpha = self.repo("alpha")
        self.commit(alpha, "第一次", at(2))
        self.cursor_transcript(alpha, at(2), "问题", "回答")
        self.store.action("register_projects", {"paths": [str(alpha)]})
        count = self.trace_count()
        self.assertEqual(count, 2)
        self.store.action("sync_traces", {})
        self.store.action("sync_traces", {})
        self.assertEqual(self.trace_count(), count)

    def test_sessions_are_read_incrementally_and_large_files_from_the_tail(self):
        alpha = self.repo("alpha")
        self.commit(alpha, "提交", at(2))
        self.codex_session(alpha, at(2, 9), "最早的问题", "最早的回答")
        path = self.store.codex_sessions_root / "2026" / "09" / "rollout.jsonl"
        self.store.action("register_projects", {"paths": [str(alpha)]})
        first_offset = self.store._trace_state()["files"][str(path)]["offset"]
        utc = at(2, 18).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        with path.open("a") as stream:
            stream.write(json.dumps({"timestamp": utc, "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "追加的最新进展"}]}}, ensure_ascii=False) + "\n")
        with patch("server.traces.read_appended", wraps=read_appended) as reader:
            self.store.action("sync_traces", {})
        self.assertEqual(reader.call_args.args[1], first_offset)
        session = self.store.state()["last_work"]["groups"][0]["sessions"][0]
        self.assertEqual((session["title"], session["last_text"]), ("最早的问题", "追加的最新进展"))
        self.assertEqual(self.store._trace_state()["files"][str(path)]["offset"], len(path.read_bytes()))

        big = self.store.codex_sessions_root / "2026" / "09" / "big.jsonl"
        filler = json.dumps({"timestamp": utc, "type": "response_item", "payload": {"type": "function_call_output", "output": "x" * 200}})
        lines = [json.dumps({"timestamp": utc, "type": "session_meta", "payload": {"cwd": str(alpha)}})] + [filler] * 50
        lines.append(json.dumps({"timestamp": utc, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "尾部的问题"}]}}, ensure_ascii=False))
        big.write_text("\n".join(lines) + "\n")
        with patch("server.traces.MAX_READ_PER_FILE", 2000):
            self.store.action("sync_traces", {})
        entry = self.store._trace_state()["files"][str(big)]
        self.assertEqual((entry["cwd"], entry["offset"]), (str(alpha), big.stat().st_size))
        self.assertIn("尾部的问题", json.dumps(entry, ensure_ascii=False))

    def test_H08_daily_log_lists_traces_and_goes_stale_on_new_commit(self):
        alpha = self.repo("alpha")
        self.commit(alpha, "今天的第一个提交", datetime.now().astimezone() - timedelta(minutes=5))
        self.store.action("register_projects", {"paths": [str(alpha)]})
        log = self.store.action("draft_log", {})
        self.assertIn("代码与会话痕迹", log["summary"])
        self.assertIn("今天的第一个提交", log["summary"])
        self.assertFalse(self.store.log_view(self.store.get("daily_log", log["id"]))["stale"])
        self.commit(alpha, "之后的提交", datetime.now().astimezone())
        self.store.action("sync_traces", {})
        self.assertTrue(self.store.log_view(self.store.get("daily_log", log["id"]))["stale"])

    def test_sync_without_projects_or_sources_is_empty_and_quiet(self):
        result = self.store.action("sync_traces", {})
        self.assertEqual((result["commits"], result["sessions"], result["errors"]), (0, 0, []))
        self.assertIsNone(self.store.state()["last_work"])


if __name__ == "__main__":
    unittest.main()
