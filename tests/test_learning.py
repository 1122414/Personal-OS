from __future__ import annotations

import base64
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.codex_learning import CodexLearningSession, LearningCancelled, learning_command
from server.materials import extract_pdf, fetch_page
from server.store import Store


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "learning.sqlite3"
        self.store = Store(self.path)
        self.topic = self.store.action("create_learning_topic", {"title": "装饰器", "goal": "理解参数传递"})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 3
        while self.store._workers and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertFalse(self.store._workers, "worker did not finish")

    def send(self, **extra):
        return self.store.action("send_learning_message", {"id": self.topic["id"], "text": "参数怎么传进去？", "request_id": f"test-{time.monotonic_ns()}", **extra})

    @staticmethod
    def successful(captured):
        class Runtime:
            def __init__(self, cwd, cancel, notify):
                self.notify = notify
            def run(self, prompt, native_session_id=None, images=()):
                captured.append({"prompt": prompt, "session": native_session_id, "images": list(images)})
                self.notify("session", {"id": native_session_id or "native-1", "model": "test-model"})
                self.notify("submitted", {"turn_id": "turn-1"})
                self.notify("delta", {"id": "reply", "text": "使用 *args"})
                self.notify("delta", {"id": "reply", "text": " 传递参数。"})
                self.notify("message", {"id": "reply", "text": "使用 *args 传递参数。"})
        return Runtime

    def test_A03_native_session_continues_after_restart_and_modes_change(self):
        captured = []
        with patch("server.learning.CodexLearningSession", self.successful(captured)):
            self.send(); self.wait()
            self.assertIsNone(captured[0]["session"])
            self.assertIn("带着学", captured[0]["prompt"])
            topic = self.store.get("learning_topic", self.topic["id"])
            self.store.action("update_learning_topic", {"id": topic["id"], "expected_updated_at": topic["updated_at"], "mode": "quick"})
            self.store.close(); self.store = Store(self.path)
            self.send(text="换个方向"); self.wait()
        self.assertEqual(captured[1]["session"], "native-1")
        self.assertIn("随问随答", captured[1]["prompt"])
        detail = self.store.learning_detail(self.topic["id"])
        self.assertEqual(len(detail["messages"]), 4)
        self.assertEqual(detail["messages"][1]["content"], "使用 *args 传递参数。")
        self.assertTrue(detail["topic"]["summary_pending"])
        self.assertNotIn("learning_messages", self.store.state())

    def test_A05_question_and_partial_response_survive_failure_and_retry(self):
        class Failed:
            def __init__(self, cwd, cancel, notify): self.notify = notify
            def run(self, *args, **kwargs):
                self.notify("delta", {"id": "part", "text": "尚未完成的解释"})
                raise ValueError("模拟连接中断")
        with patch("server.learning.CodexLearningSession", Failed):
            question = self.send(request_id="stable-request"); self.wait()
        detail = self.store.learning_detail(self.topic["id"])
        self.assertEqual(detail["messages"][0]["content"], question["content"])
        self.assertEqual(detail["messages"][1]["status"], "Failed")
        self.assertEqual(detail["messages"][1]["content"], "尚未完成的解释")
        self.assertFalse(detail["topic"].get("summary_pending"))
        with patch("server.learning.CodexLearningSession", self.successful([])):
            self.store.action("retry_learning", {"id": question["id"], "reset_session": True}); self.wait()
        self.assertEqual(len([m for m in self.store.all("learning_message") if m["role"] == "user"]), 1)
        self.assertEqual(self.store.all("learning_run")[0]["status"], "Completed")
        duplicate = self.send(request_id="stable-request")
        self.assertEqual(duplicate["id"], question["id"])

    def test_A05_cancel_preserves_partial_text_and_rejects_parallel_turn(self):
        entered = threading.Event()
        class Waiting:
            def __init__(self, cwd, cancel, notify): self.cancel, self.notify = cancel, notify
            def run(self, *args, **kwargs):
                self.notify("delta", {"id": "part", "text": "部分回答"})
                entered.set()
                self.cancel.wait(2)
                raise LearningCancelled()
        with patch("server.learning.CodexLearningSession", Waiting):
            self.send()
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(ValueError, "正在回复"):
                self.send()
            run = self.store.all("learning_run")[0]
            self.store.action("cancel_learning", {"id": run["id"]})
            self.wait()
        answer = self.store.get("learning_message", run["assistant_message_id"])
        self.assertEqual(answer["status"], "Cancelled")
        self.assertEqual(answer["content"], "部分回答")

    def test_A05_close_stops_worker_and_reopen_marks_stranded_run(self):
        user = self.store.put("learning_message", {"topic_id": self.topic["id"], "role": "user", "content": "原问题", "revision": 1})
        answer = self.store.put("learning_message", {"topic_id": self.topic["id"], "role": "assistant", "content": "部分", "status": "Running", "revision": 1})
        run = self.store.put("learning_run", {"topic_id": self.topic["id"], "user_message_id": user["id"], "assistant_message_id": answer["id"], "status": "Running"})
        # Simulate an abrupt stop without the normal shutdown finalizer.
        self.store.db.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get("learning_run", run["id"])["status"], "Interrupted")
        self.assertEqual(self.store.get("learning_message", answer["id"])["content"], "部分")

    def test_A09_unparsed_material_is_not_silently_read(self):
        record = self.store.action("create_record", {"content": "参考资料"})
        self.store.action("link_record", {"id": self.topic["id"], "record_id": record["id"]})
        material = self.store.action("add_material", {"record_id": record["id"], "url": "https://example.com/article"})
        with patch("server.learning.CodexLearningSession") as runtime:
            with self.assertRaisesRegex(ValueError, "先解析"):
                self.send(material_ids=[material["id"]])
            runtime.assert_not_called()
        self.assertEqual(self.store.all("learning_message"), [])
        with patch("server.learning.fetch_page", side_effect=ValueError("HTTP 403")):
            self.store.action("parse_material", {"id": material["id"]}); self.wait()
        self.assertEqual(self.store.get("material", material["id"])["read_status"], "failed")

    def test_A09_material_snapshot_pages_and_actual_use_are_distinct(self):
        record = self.store.action("create_record", {"content": "论文资料"})
        self.store.action("link_record", {"id": self.topic["id"], "record_id": record["id"]})
        material = self.store.action("add_material", {"record_id": record["id"], "name": "source.pdf", "base64": base64.b64encode(b"%PDF-1.4").decode()})
        parsed = {"status": "partial", "note": "仅第 2 页文字，其他页未识别", "pages": [{"page": 2, "text": "第 2 页原文"}], "page_count": 3, "fingerprint": "one"}
        with patch("server.learning.extract_pdf", return_value=parsed):
            self.store.action("parse_material", {"id": material["id"]}); self.wait()
        self.assertEqual(self.store.get("material", material["id"])["used_in"], [])
        captured = []
        with patch("server.learning.CodexLearningSession", self.successful(captured)):
            self.send(material_ids=[material["id"]]); self.wait()
        self.assertIn("第 2 页原文", captured[0]["prompt"])
        used = self.store.get("material", material["id"])["used_in"]
        self.assertEqual(len(used), 1)
        source = self.store.learning_detail(self.topic["id"])["messages"][0]["sources"][1]
        self.assertEqual(source["pages"], parsed["pages"])
        self.assertEqual(source["revision"], used[0]["revision"])

    def test_image_runtime_failure_does_not_claim_recognition(self):
        record = self.store.action("create_record", {"content": "一张图"})
        self.store.action("link_record", {"id": self.topic["id"], "record_id": record["id"]})
        body = b"\x89PNG\r\n\x1a\noriginal-image"
        material = self.store.action("add_material", {"record_id": record["id"], "name": "image.png", "base64": base64.b64encode(body).decode()})
        captured = []
        class Unsupported:
            def __init__(self, cwd, cancel, notify): pass
            def run(self, prompt, native_session_id=None, images=()):
                captured.extend(path.read_bytes() for path in images)
                raise ValueError("当前模型不支持图像")
        with patch("server.learning.CodexLearningSession", Unsupported):
            self.send(material_ids=[material["id"]]); self.wait()
        self.assertEqual(captured, [body])
        self.assertEqual(self.store.get("material", material["id"])["used_in"], [])
        self.assertEqual(self.store.all("learning_run")[0]["status"], "Failed")

    def test_importance_marker_is_persisted_without_mastery_inference(self):
        with patch("server.learning.CodexLearningSession", self.successful([])):
            self.send(); self.wait()
        answer = self.store.all("learning_message")[0]
        self.store.action("mark_learning_message", {"id": answer["id"], "important": True})
        self.assertTrue(self.store.get("learning_message", answer["id"])["important"])
        self.assertNotIn("mastered", self.store.get("learning_topic", self.topic["id"]))


class ProtocolTests(unittest.TestCase):
    def test_stdio_handshake_readonly_stream_and_resume_contract(self):
        lines = [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "native-id"}, "model": "fixture"}},
            {"id": 3, "result": {"turn": {"id": "turn-id"}}},
            {"method": "item/agentMessage/delta", "params": {"threadId": "native-id", "turnId": "turn-id", "itemId": "item", "delta": "流式文字"}},
            {"method": "item/completed", "params": {"threadId": "native-id", "turnId": "turn-id", "item": {"type": "agentMessage", "id": "item", "text": "完整回复"}}},
            {"method": "turn/completed", "params": {"threadId": "native-id", "turn": {"id": "turn-id", "status": "completed", "items": []}}},
        ]
        sent = []
        class Input(io.StringIO):
            def write(self, value): sent.append(json.loads(value)); return len(value)
        class Process:
            def __init__(self, *args, **kwargs): self.stdin = Input(); self.stdout = io.StringIO("\n".join(map(json.dumps, lines)))
            def poll(self): return 0
        events = []
        with patch("server.codex_learning.shutil.which", return_value="/bin/codex"), patch("server.codex_learning.subprocess.Popen", Process):
            CodexLearningSession(Path('/tmp'), threading.Event(), lambda kind, value: events.append((kind, value))).run("question", "native-id")
        self.assertEqual([x.get("method") for x in sent], ["initialize", "initialized", "thread/resume", "turn/start"])
        self.assertEqual(sent[2]["params"]["sandbox"], "read-only")
        self.assertEqual(sent[3]["params"]["sandboxPolicy"], {"type": "readOnly", "networkAccess": False})
        self.assertEqual([kind for kind, _ in events], ["session", "submitted", "delta", "message"])

    def test_learning_command_disables_external_actions_without_changing_config(self):
        with patch("server.codex_learning.shutil.which", return_value="/bin/codex"):
            command = learning_command()
        for setting in ('mcp_servers={}', 'features.plugins=false', 'features.shell_tool=false', 'features.apps=false', 'sandbox_mode="read-only"'):
            self.assertIn(setting, command)

    def test_private_network_material_urls_are_rejected_before_connection(self):
        with patch('server.materials.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]), patch('server.materials.socket.create_connection') as connect:
            with self.assertRaisesRegex(ValueError, '内网'):
                fetch_page('http://example.com/private')
            connect.assert_not_called()

    @unittest.skipUnless(Path('build/PersonalOSPDF').is_file(), 'Build the macOS PDFKit helper first')
    def test_real_pdfkit_extracts_text_and_reports_blank_page(self):
        # Minimal two-page PDF with a text page and a blank scan-like page.
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
                   b'<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>',
                   b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
                   b'<< /Length 46 >>\nstream\nBT /F1 12 Tf 20 250 Td (PDF source text) Tj ET\nendstream',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                   b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] >>']
        body = b'%PDF-1.4\n'; offsets = [0]
        for number, obj in enumerate(objects, 1):
            offsets.append(len(body)); body += f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n'
        xref = len(body)
        body += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
        body += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
        body += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
        result = extract_pdf(body)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['page_count'], 2)
        self.assertEqual(result['pages'][0]['page'], 1)
        self.assertIn('PDF source text', result['pages'][0]['text'])


if __name__ == '__main__':
    unittest.main()
