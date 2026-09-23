from __future__ import annotations

import unittest
from pathlib import Path

from server.app import make_handler


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
