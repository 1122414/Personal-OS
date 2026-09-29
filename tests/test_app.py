from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock

from server.app import make_handler, migrate_legacy_database
from server.store import Store


class LocalRequestTests(unittest.TestCase):
    def setUp(self):
        handler_type = make_handler(None, Path("/private/tmp"))
        self.handler = object.__new__(handler_type)

    def test_local_json_action_and_vite_origin_are_allowed(self):
        self.handler.headers = {
            "Host": "127.0.0.1:8765",
            "Origin": "http://127.0.0.1:5173",
            "Content-Type": "application/json; charset=utf-8",
        }
        self.assertTrue(self.handler._local_request(mutation=True))

    def test_remote_origin_and_form_posts_are_rejected(self):
        self.handler.headers = {
            "Host": "127.0.0.1:8765",
            "Origin": "https://example.com",
            "Content-Type": "application/json",
        }
        self.assertFalse(self.handler._local_request(mutation=True))
        self.handler.headers = {"Host": "127.0.0.1:8765", "Content-Type": "text/plain"}
        self.assertFalse(self.handler._local_request(mutation=True))

    def test_dns_rebinding_host_is_rejected(self):
        self.handler.headers = {"Host": "example.com:8765"}
        self.assertFalse(self.handler._local_request())

    def test_malformed_authorities_are_rejected_without_raising(self):
        for host, origin in (("[", None), ("127.0.0.1:bad", None),
                             ("127.0.0.1", "http://["), ("127.0.0.1", "http://127.0.0.1:bad")):
            with self.subTest(host=host, origin=origin):
                self.handler.headers = {"Host": host, "Content-Type": "application/json"}
                if origin:
                    self.handler.headers["Origin"] = origin
                self.assertFalse(self.handler._local_request(mutation=True))
                self.handler._json = Mock()
                self.handler.do_POST()
                self.assertEqual(403, self.handler._json.call_args.args[0])


class MigrationTests(unittest.TestCase):
    def test_backup_preserves_existing_data_and_never_overwrites_target(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "old.sqlite3"
            target = Path(folder) / "application-support" / "personal-os.sqlite3"
            original = Store(source)
            original.action("create_task", {"title": "原有任务"})
            self.assertTrue(migrate_legacy_database(source, target))
            migrated = Store(target)
            self.assertEqual(migrated.all("task")[0]["title"], "原有任务")
            migrated.action("create_task", {"title": "客户端任务"})
            self.assertFalse(migrate_legacy_database(source, target))
            self.assertEqual(len(migrated.all("task")), 2)
            migrated.close()
            original.close()
