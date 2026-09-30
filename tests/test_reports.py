import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from server.app import make_handler
from server.reports import MAX_REPORT_BYTES, read_report, report_index, report_summary
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

    def test_finance_and_law_modules_are_read_and_grouped(self):
        for folder, name in (('每日金融', '金融日报.md'), ('每日法律', '法律日报.md')):
            (self.vault / folder / self.day).mkdir(parents=True)
            (self.vault / folder / self.day / name).write_text(f'# {name[:4]}')
        index = self.store.state()['daily_reports']
        self.assertEqual([m['name'] for m in index['modules']], ['AI', '金融', '法律'])
        self.assertEqual([r['module'] for r in index['reports']], ['AI', '金融', '法律'])
        self.assertEqual(index['errors'], [])
        law = index['reports'][2]
        self.assertEqual(read_report(self.settings(), law['path'], '每日法律')['content'], '# 法律日报')
        self.assertEqual(read_report(self.settings(), law['path'], '每日法律')['id'], law['id'])
        with self.assertRaisesRegex(ValueError, '已配置'):
            read_report(self.settings(), law['path'], '私人笔记')
        handler = object.__new__(make_handler(self.store, self.root))
        handler.headers = {'Host': '127.0.0.1:8765'}
        replies = []
        handler._json = lambda status, value: replies.append((status, value))
        handler.path = '/api/obsidian/report?module=' + quote('每日金融') + '&path=' + quote(f'{self.day}/金融日报.md')
        handler.do_GET()
        self.assertEqual((replies[-1][0], replies[-1][1]['module']), (200, '金融'))

    def test_summary_is_taken_from_each_reports_own_summary_section(self):
        samples = {
            'heading': ('# 金融日报\n\n> 覆盖窗口：略\n\n## 今日三句话\n\n1. 第一句\n2. **第二句**\n\n## 一、宏观\n正文', ['第一句', '第二句']),
            'callout': ('---\ntitle: 法律\n---\n\n# 法律日报\n\n> [!summary] 今日三句话\n> 1. **重磅**：条例\n> 2. [规定](https://x)\n\n---\n', ['重磅：条例', '规定']),
            'lead': ('**AI HOT 日报**\n\n> 数据来源：略\n\n> **导语**：大事件\n>\n> 展开一段\n\n## 模型', ['大事件', '展开一段']),
            'numbered': ('# 雷达\n\n## 一、执行摘要\n\n本期要点。\n\n## 二、详情', ['本期要点。']),
            'fallback': ('**标题**\n\n| a | b |\n\n第一段正文 [[笔记|别名]]。\n\n第二段', ['第一段正文 别名。']),
            'ignored mention': ('# 报告\n\n正文里提到摘要：不算\n\n## 摘要\n- 真正的摘要', ['真正的摘要']),
        }
        for name, (text, expected) in samples.items():
            with self.subTest(name):
                self.assertEqual(report_summary(text), expected)

    def test_index_summarises_the_main_report_of_each_module(self):
        (self.folder / 'MUA日报.md').write_text('# MUA\n\n## 今日结论\n- 不是主报告')
        self.note.write_text('**AI HOT 日报**\n\n> **导语**：今天的导语\n')
        (self.vault / '每日金融' / self.day).mkdir(parents=True)
        (self.vault / '每日金融' / self.day / '金融日报.md').write_text('# 金融\n\n## 今日三句话\n1. 金融一句')
        summaries = self.store.state()['daily_reports']['summaries']
        self.assertEqual([(s['module'], s['items']) for s in summaries], [('AI', ['今天的导语']), ('金融', ['金融一句'])])
        self.note.write_text('**AI HOT 日报**\n\n> **导语**：改过的导语，长度也变了\n')
        self.assertEqual(self.store.state()['daily_reports']['summaries'][0]['items'], ['改过的导语，长度也变了'])

    def test_module_list_is_validated_and_replaces_defaults(self):
        self.store.action('save_settings', {'daily_reports_folder': '每日AI'})
        for modules in ([], [{'name': 'AI', 'folder': '/tmp'}], [{'name': '', 'folder': 'a'}], [{'name': 'A', 'folder': 'a'}, {'name': 'A', 'folder': 'b'}]):
            with self.subTest(modules=modules), self.assertRaises(ValueError):
                self.store.action('save_settings', {'report_modules': modules})
        self.store.action('save_settings', {'report_modules': [{'name': ' AI ', 'folder': '每日AI'}, {'name': '周报', 'folder': '每周'}]})
        index = self.store.state()['daily_reports']
        self.assertEqual(index['modules'], [{'name': 'AI', 'folder': '每日AI'}, {'name': '周报', 'folder': '每周'}])
        self.assertEqual(len(index['errors']), 1)
        self.assertIn('周报', index['errors'][0])
        self.assertEqual(len(index['reports']), 1)

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
