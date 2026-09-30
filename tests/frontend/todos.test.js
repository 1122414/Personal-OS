import assert from 'node:assert/strict'
import test from 'node:test'
import { dropBefore, nextPriority, todoOrder } from '../../src/todos.js'

test('unranked to-dos come first by creation time, then the rest by rank', () => {
  const todos = [
    { id: 'a', created_at: '2026-09-30T08:00' },
    { id: 'b', created_at: '2026-09-30T07:00', rank: 2 },
    { id: 'c', created_at: '2026-09-30T06:00' },
    { id: 'd', created_at: '2026-09-30T09:00', rank: 0 },
  ]
  assert.deepEqual(todos.sort(todoOrder).map(item => item.id), ['c', 'a', 'd', 'b'])
})

test('drop position follows the hovered half of a row', () => {
  const list = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
  assert.equal(dropBefore(list, 'b', false), 'b')
  assert.equal(dropBefore(list, 'b', true), 'c')
  assert.equal(dropBefore(list, 'c', true), null)
  assert.equal(dropBefore(list, 'x', false), null)
})

test('priority cycles medium, high, low', () => {
  assert.deepEqual([undefined, 'medium', 'high', 'low'].map(nextPriority), ['high', 'high', 'low', 'medium'])
})
