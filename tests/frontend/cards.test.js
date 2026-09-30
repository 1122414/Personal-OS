import assert from 'node:assert/strict'
import test from 'node:test'
import { dueLabel, sourceLabel, todayCards } from '../../src/learning/cards.js'

const card = (id, fields) => ({ id, created_at: `2026-09-${id}T08:00:00+08:00`, reviews: [], mastered_at: null, ...fields })

test('today lists due unmastered cards, reviews before new ones', () => {
  const cards = [
    card('10', { due_date: '2026-09-30' }),
    card('11', { due_date: '2026-09-28', reviews: [{ rating: 'fuzzy' }] }),
    card('12', { due_date: '2026-10-01' }),
    card('13', { due_date: null, mastered_at: '2026-09-29T00:00:00+08:00' }),
    card('14', { due_date: '2026-09-29' }),
  ]
  assert.deepEqual(todayCards(cards, '2026-09-30').map(item => item.id), ['11', '14', '10'])
  assert.deepEqual(todayCards(undefined, '2026-09-30'), [])
})

test('due and source labels', () => {
  assert.equal(dueLabel(card('1', { due_date: '2026-09-30' }), '2026-09-30'), '今天学')
  assert.equal(dueLabel(card('1', { due_date: '2026-09-29', reviews: [{}] }), '2026-09-30'), '今天复习')
  assert.equal(dueLabel(card('1', { due_date: '2026-10-01' }), '2026-09-30'), '明天复习')
  assert.equal(dueLabel(card('1', { due_date: '2026-10-07' }), '2026-09-30'), '7 天后复习')
  assert.equal(dueLabel(card('1', { mastered_at: 'x' }), '2026-09-30'), '已掌握')
  assert.equal(sourceLabel({ source: 'ai', engine: 'Kimi' }), 'AI · Kimi')
  assert.equal(sourceLabel({ source: 'user' }), '我写的')
})
