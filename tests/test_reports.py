import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from server.app import make_handler
from server.reports import MAX_REPORT_BYTES, read_report, report_index
from server.store import Store


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / 'vault'
        self.day = (date.today() - timedelta(days=1)).isoformat()
        self.folder = self.vault / '每日AI' / self.day
        self.folder.mkdir(parents=True)
        self.note = self.folder / 'AI日报-测试.md'
        self.note.write_text('**AI HOT 日报**\n\n## 行业动态\n\n- [ ] **一条重要发现**\n  原文：https://example.com/report\n')
        self.store = Store(self.root / 'test.sqlite3')
        self.store.action('save_settings', {'obsidian_vault': str(self.vault)})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def settings(self):
        return self.store.get('settings', 'settings')

    def test_reports_are_artifacts_ordered_by_date_with_full_live_content(self):
        (self.folder / 'important!.md').write_text('not a report')
        (self.folder / 'SmartRun周报.md').write_text('# 周度简报\n\n| 项目 | 状态 |\n|---|---|\n| A | B |')
        old = self.vault / '每日AI' / (date.today() - timedelta(days=2)).isoformat()
        old.mkdir()
        (old / 'MUA日报.md').write_text('# 较早报告')
        (self.vault / '每日AI' / 'state.json').write_text('{}')
        initial = hashlib.sha256(self.note.read_bytes()).hexdigest()
        before_events = len(self.store.events())
        index = self.store.state()['daily_reports']
        self.assertEqual(index['latest_date'], self.day)
        self.assertEqual(len(index['reports']), 3)
        item = index['reports'][0]
        self.assertEqual(item['title'], 'AI HOT 日报')
        body = read_report(self.settings(), item['path'])
        self.assertEqual(body['content'], self.note.read_text())
        self.assertEqual(hashlib.sha256(self.note.read_bytes()).hexdigest(), initial)
        self.assertEqual(len(self.store.events()), before_events)
        self.assertEqual(self.store.all('intelligence_item'), [])
        self.note.write_text('# 正文已更新\n\n最新结论，不能返回旧副本。')
        self.assertIn('最新结论', read_report(self.settings(), item['path'])['content'])
        self.assertNotEqual(report_index(self.settings())['reports'][0]['version'], item['version'])
        self.note.unlink()
        with self.assertRaisesRegex(ValueError, '移动或删除'):
            read_report(self.settings(), item['path'])

    def test_rejects_path_escape_symlinks_and_non_report_files(self):
        for relative in ('../secret.md', f'{self.day}/../../secret.md', str(self.note), f'{self.day}/important!.md', f'{self.day}/state.json', '2026-99-99/report.md'):
            with self.subTest(path=relative), self.assertRaises(ValueError):
                read_report(self.settings(), relative)
        external = self.root / 'secret.md'
        external.write_text('do not read')
        self.note.unlink()
        self.note.symlink_to(external)
        with self.assertRaises(ValueError):
            read_report(self.settings(), f'{self.day}/{self.note.name}')
        self.assertEqual(report_index(self.settings())['reports'], [])
        self.assertTrue(report_index(self.settings())['errors'])
        other = self.root / 'outside'
        self.folder.rename(other)
        self.folder.symlink_to(other, target_is_directory=True)
        with self.assertRaises(ValueError):
            read_report(self.settings(), f'{self.day}/other.md')

    def test_oversize_invalid_encoding_and_missing_configuration_are_explicit(self):
        self.note.write_bytes(b'x' * (MAX_REPORT_BYTES + 1))
        self.assertTrue(report_index(self.settings())['errors'])
        with self.assertRaisesRegex(ValueError, '512 KB'):
            read_report(self.settings(), f'{self.day}/{self.note.name}')
        self.note.write_bytes(b'\xff\xfe\xff')
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            read_report(self.settings(), f'{self.day}/{self.note.name}')
        empty = report_index({})
        self.assertFalse(empty['configured'])
        self.assertTrue(empty['errors'])
        with self.assertRaisesRegex(ValueError, '相对'):
            self.store.action('save_settings', {'daily_reports_folder': '/tmp'})
        with self.assertRaisesRegex(ValueError, '相对'):
            self.store.action('save_settings', {'daily_reports_folder': '../elsewhere'})

    def test_opacity_persists_and_rejects_invalid_values_without_partial_save(self):
        for value in (-1, 101, 2.5, True, '50', None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '透明度'):
                self.store.action('save_settings', {'theme_transparency': value, 'nickname': 'must not save'})
        self.assertNotEqual(self.settings()['nickname'], 'must not save')
        for value in (0, 55, 100):
            self.store.action('save_settings', {'theme_transparency': value})
            self.assertEqual(self.store.state()['settings']['theme_transparency'], value)
        self.store.close()
        self.store = Store(self.root / 'test.sqlite3')
        self.assertEqual(self.store.state()['settings']['theme_transparency'], 100)
        legacy = self.settings()
        legacy.pop('theme_transparency')
        legacy.pop('daily_reports_folder', None)
        self.store.put('settings', legacy)
        self.assertEqual(self.store.state()['settings']['theme_transparency'], 8)
        self.assertEqual(self.store.state()['daily_reports']['latest_date'], self.day)

    def test_report_http_route_reads_only_allowed_content(self):
        handler = object.__new__(make_handler(self.store, self.root))
        handler.headers = {'Host': '127.0.0.1:8765'}
        replies = []
        handler._json = lambda status, value: replies.append((status, value))
        handler.path = '/api/obsidian/report?path=' + quote(f'{self.day}/{self.note.name}')
        handler.do_GET()
        self.assertEqual(replies[-1][0], 200)
        self.assertIn('重要发现', replies[-1][1]['content'])
        handler.path = '/api/obsidian/report?path=../secret.md'
        handler.do_GET()
        self.assertEqual(replies[-1][0], 400)
        handler.headers = {'Host': 'evil.example'}
        handler.do_GET()
        self.assertEqual(replies[-1][0], 403)

    def test_workbuddy_conversations_are_not_ai_brief_context(self):
        todo = self.store.action('create_todo', {'title': 'real todo'})
        self.store.put('intelligence_item', {'title': 'CONVERSATION_NOISE', 'source_kind': 'workbuddy', 'source': 'WorkBuddy', 'why_recommended': 'session'})
        with patch('server.runtime.shutil.which', return_value='codex'), patch.object(self.store, '_codex_readonly', return_value=json.dumps({'priorities': [{'todo_id': todo['id'], 'reason': 'test'}]})) as model:
            self.store.action('generate_brief', {})
        self.assertNotIn('CONVERSATION_NOISE', model.call_args.args[0])
