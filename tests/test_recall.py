from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from server.recall import instant, shared_terms
from server.store import Store


class RecallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'recall.sqlite3')
        self.now = datetime.now().astimezone()
        self.topic = self.store.action('create_learning_topic', {'title': 'Python 装饰器', 'goal': '参数透传与计时工具'})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def record(self, text='用 Python 装饰器做计时工具', days=10, **extra):
        record = self.store.create_record({'content': text, 'record_type': 'idea'})
        record.update(extra)
        record = self.store.put('record', record)
        record['created_at'] = (self.now - timedelta(days=days)).isoformat()
        self.store.db.execute('UPDATE objects SET data=?,created_at=? WHERE id=?', (json.dumps(record), record['created_at'], record['id']))
        self.store.db.commit()
        return record

    def state(self, **extra):
        return self.store.action('create_personal_state', {'text': '这周想轻一点，先把已有学习继续下去', **extra})

    def test_default_expiry_preserves_original_without_creating_work(self):
        state = self.state(pace='light')
        self.assertAlmostEqual((instant(state['expires_at']) - self.now).total_seconds(), 7 * 86400, delta=5)
        original = self.store.get('record', state['record_id'])
        self.assertEqual(original['content'], state['text'])
        self.assertEqual([], self.store.all('task'))
        self.assertEqual([], self.store.all('agent_run'))
        self.assertTrue(self.store.personal_state_view(state, self.now)['active'])
        self.assertFalse(self.store.personal_state_view(state, self.now + timedelta(days=8))['active'])
        self.assertEqual(original, self.store.get('record', state['record_id']))

    def test_explicit_date_and_pending_inference_confirmation(self):
        end = (self.now + timedelta(days=3)).date().isoformat()
        state = self.state(expires_at=end, source_kind='inference', pace='rest')
        self.assertEqual(end, state['expires_at'][:10])
        self.assertEqual('normal', self.store.learning_state_context()['pace'])
        self.store.action('confirm_personal_state', {'id': state['id'], 'expected_updated_at': state['updated_at']})
        self.assertEqual('rest', self.store.learning_state_context()['pace'])

    def test_end_and_revision_conflict_preserve_history(self):
        state = self.state()
        changed = self.store.action('update_personal_state', {'id': state['id'], 'expected_updated_at': state['updated_at'], 'text': '恢复了，照常学习'})
        self.assertEqual([state['record_id']], changed['previous_record_ids'])
        self.assertEqual(state['text'], changed['original_text'])
        self.assertIsNotNone(self.store.get('record', state['record_id']))
        with self.assertRaisesRegex(ValueError, '别处修改'):
            self.store.action('end_personal_state', {'id': state['id'], 'expected_updated_at': state['updated_at']})
        self.store.action('end_personal_state', {'id': changed['id'], 'expected_updated_at': changed['updated_at']})
        self.assertEqual([], self.store.active_personal_states())
        self.assertEqual(1, len(self.store.all('personal_state')))

    def test_invalid_state_and_source_mismatch_do_not_save(self):
        record = self.record()
        for extra in ({'expires_at': 'bad'}, {'expires_at': '2000-01-01'}, {'pace': []}, {'avoid_new_projects': 'yes'}, {'record_id': record['id']}, {'source_kind': []}):
            with self.assertRaises(ValueError):
                self.state(**extra)
        self.assertEqual([], self.store.all('personal_state'))

    def test_state_from_existing_record_preserves_whitespace_and_source(self):
        record = self.record('  这周想轻一点。\n\n')
        state = self.state(text=record['content'], record_id=record['id'])
        self.assertEqual(record['content'], state['text'])
        self.assertEqual(record['id'], state['record_id'])
        self.assertEqual(1, len(self.store.all('record')))

    def test_current_state_context_overrides_expired_history_without_editing_plan(self):
        todo = self.store.action('create_todo', {'title': '继续阅读', 'today': True})
        state = self.state(pace='rest', avoid_new_projects=True)
        prompt = self.store._learning_prompt(self.topic, {'id': 'test', 'content': '继续', 'sources': []}, False)
        self.assertIn('rest', prompt)
        self.assertIn(state['record_id'], prompt)
        with patch('server.recall.datetime') as clock:
            clock.now.return_value = self.now + timedelta(days=8)
            clock.fromisoformat.side_effect = datetime.fromisoformat
            after = self.store.learning_state_context()
        self.assertEqual([], after['states'])
        self.assertFalse(after['avoid_new_projects'])
        self.assertEqual(todo, self.store.get('todo', todo['id']))

    def test_related_reasons_are_grounded_and_no_noise_fill(self):
        old = self.record()
        self.record('周末海边散步，记得带相机')
        self.record(days=0)
        results = self.store.related_records(self.topic['id'])
        self.assertEqual([old['id']], [item['record_id'] for item in results])
        self.assertIn('Python'.lower(), results[0]['matched_terms'])
        self.assertIn('计时工具', results[0]['reason'])
        self.assertFalse(shared_terms('今天学习这个东西', '最近记录一些想法'))
        self.assertEqual([], self.store.all('task'))

    def test_weekly_limit_once_and_no_missed_week_flood(self):
        for i in range(7):
            self.record(f'Python 装饰器计时工具方案 {i}')
        review = self.store.recall_tick(self.now)
        self.assertEqual(3, len(review['items']))
        self.assertEqual(review, self.store.recall_tick(self.now + timedelta(seconds=1)))
        self.store.recall_tick(self.now + timedelta(days=70))
        self.assertEqual(2, len(self.store.all('idea_review')))
        self.assertEqual([], self.store.all('task'))

    def test_empty_week_can_later_generate_but_handled_review_is_not_refilled(self):
        self.assertEqual([], self.store.recall_tick(self.now)['items'])
        old = self.record()
        review = self.store.recall_tick(self.now)
        self.assertEqual([old['id']], [item['record_id'] for item in review['items']])
        self.store.action('recall_feedback', {'id': old['id'], 'choice': 'never'})
        self.record('Python 装饰器新的旧点子')
        self.store.recall_tick(self.now)
        self.assertEqual([], self.store.weekly_review_view(self.now)['items'])
        self.assertEqual(1, len(self.store.all('idea_review')))

    def test_legacy_empty_review_is_filled_in_place(self):
        year, week, _ = self.now.isocalendar()
        legacy = self.store.put('idea_review', {'week': f'{year}-W{week:02d}', 'items': []})
        self.record()
        review = self.store.recall_tick(self.now)
        self.assertEqual(legacy['id'], review['id'])
        self.assertEqual(1, len(review['items']))
        self.assertEqual(1, len(self.store.all('idea_review')))

    def test_weekly_filters_age_before_cap_and_empty_remains_empty(self):
        self.record('完全不相关的文字')
        for _ in range(3):
            self.record(days=2)
        old = self.record('Python 装饰器', days=10)
        review = self.store.recall_tick(self.now)
        self.assertEqual([old['id']], [item['record_id'] for item in review['items']])
        self.store.action('recall_feedback', {'id': old['id'], 'choice': 'never'})
        self.assertEqual([], self.store.weekly_review_view(self.now)['items'])

    def test_feedback_defer_never_continue_and_cooldown(self):
        records = [self.record() for _ in range(3)]
        self.store.recall_tick(self.now)
        for record, choice in zip(records, ('defer', 'never', 'continue')):
            self.store.action('recall_feedback', {'id': record['id'], 'choice': choice})
        self.assertEqual([], self.store.weekly_review_view(self.now)['items'])
        self.assertFalse(self.store._recall_allowed(self.store.get('record', records[0]['id']), self.now))
        self.assertTrue(self.store._recall_allowed(self.store.get('record', records[0]['id']), self.now + timedelta(days=8)))
        self.assertFalse(self.store._recall_allowed(self.store.get('record', records[1]['id']), self.now + timedelta(days=80)))
        next_week = self.store.recall_tick(self.now + timedelta(days=8))
        self.assertNotIn(records[2]['id'], [item['record_id'] for item in next_week['items']])
        self.assertEqual([], self.store.all('task'))

    def test_no_new_projects_suppresses_unknown_and_explicit_new_project(self):
        self.record(idea_scope='new_project')
        self.record(idea_scope='unknown')
        existing = self.record(idea_scope='existing')
        self.store.recall_tick(self.now)
        self.state(avoid_new_projects=True)
        self.assertEqual([existing['id']], [item['record_id'] for item in self.store.related_records(self.topic['id'])])
        self.assertEqual([existing['id']], [item['record_id'] for item in self.store.weekly_review_view(self.now)['items']])

    def test_cached_review_revalidates_edited_content(self):
        record = self.record()
        self.store.recall_tick(self.now)
        self.store.action('update_record', {'id': record['id'], 'expected_updated_at': record['updated_at'], 'title': '散步', 'content': '看海'})
        self.assertEqual([], self.store.weekly_review_view(self.now)['items'])

    def test_restart_keeps_feedback_and_state(self):
        old = self.record()
        self.state()
        self.store.recall_tick(self.now)
        self.store.action('recall_feedback', {'id': old['id'], 'choice': 'never'})
        path = self.store.path
        self.store.close()
        self.store = Store(path)
        data = self.store.state()
        self.assertEqual([], data['weekly_review']['items'])
        self.assertTrue(data['personal_states'][0]['active'])
        self.assertNotIn('idea_reviews', data)

    def test_reply_retains_state_used_for_that_attempt(self):
        state = self.state(pace='light')
        message = {'id': 'saved-question', 'topic_id': self.topic['id'], 'content': '继续', 'sources': []}
        with patch('server.learning.threading.Thread') as worker:
            self.store._start_learning(self.topic, message)
            sent_message = worker.call_args.kwargs['args'][1]
            self.store.action('end_personal_state', {'id': state['id'], 'expected_updated_at': state['updated_at']})
            prompt = self.store._learning_prompt(self.topic, sent_message, False)
            self.assertIn(state['text'], prompt)
            assistant = self.store.all('learning_message')[0]
            self.assertEqual('light', assistant['state_context']['pace'])
            self.assertEqual([], self.store.learning_state_context()['states'])
            self.store._workers.clear()


if __name__ == '__main__':
    unittest.main()
