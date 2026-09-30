import assert from 'node:assert/strict'
import test from 'node:test'
import { agentNotices, mergeRunningRuns } from '../../src/liveRuns.js'
import { createWorkspaceRequests } from '../../src/workspaceRequests.js'

const snapshot = { tasks: [], agent_runs: [{ id: 'a', status: 'Running', transcript: [] }, { id: 'b', status: 'Finished' }] }

test('running runs are patched into the snapshot', () => {
  const merged = mergeRunningRuns(snapshot, [{ id: 'a', status: 'Running', transcript: [{ type: 'text', text: '先看看' }] }])
  assert.equal(merged.stale, false)
  assert.deepEqual(merged.data.agent_runs[0].transcript, [{ type: 'text', text: '先看看' }])
  assert.equal(merged.data.agent_runs[1], snapshot.agent_runs[1])
})

test('an ended or unknown run asks for a full refresh', () => {
  assert.equal(mergeRunningRuns(snapshot, []).stale, true)
  assert.equal(mergeRunningRuns(snapshot, [snapshot.agent_runs[0], { id: 'c', status: 'Running' }]).stale, true)
})

test('a live read is dropped once a write starts', async () => {
  let release
  const requests = createWorkspaceRequests({
    load: async () => ({}),
    loadRunning: () => new Promise(resolve => { release = resolve }),
    action: async () => ({ state: {} }),
    onData: () => {},
    onPending: () => {},
  })
  const reading = requests.live()
  await requests.mutate('save', {})
  release([{ id: 'a', status: 'Running' }])
  assert.equal(await reading, undefined)
  const fresh = requests.live()
  release([{ id: 'a', status: 'Running' }])
  assert.deepEqual(await fresh, [{ id: 'a', status: 'Running' }])
})

test('ended turns become notices; canceled and already finished turns do not', () => {
  const tasks = [{ id: 't1', title: '写一个小脚本' }, { id: 't2', title: '整理文档' }, { id: 't3', title: '跑测试' }, { id: 't4', title: '取消的' }]
  const previous = { tasks, agent_runs: [
    { id: 'r1', task_id: 't1', status: 'Running' }, { id: 'r2', task_id: 't2', status: 'Running' },
    { id: 'r3', task_id: 't3', status: 'Running' }, { id: 'r4', task_id: 't4', status: 'Running' }, { id: 'r5', task_id: 't2', status: 'Finished' },
  ] }
  const next = { tasks, agent_runs: [
    { id: 'r1', task_id: 't1', status: 'Finished', agent_id: 'Kimi', needs_reply: true },
    { id: 'r2', task_id: 't2', status: 'Finished', agent_id: 'Kimi' },
    { id: 'r3', task_id: 't3', status: 'Failed', agent_id: 'Codex', error: '额度用完\n详细信息' },
    { id: 'r4', task_id: 't4', status: 'Canceled' }, { id: 'r5', task_id: 't2', status: 'Finished' },
  ] }
  assert.deepEqual(agentNotices(previous, next), [
    { taskId: 't1', title: '写一个小脚本', body: 'Kimi 在等你回复' },
    { taskId: 't2', title: '整理文档', body: 'Kimi 这一轮做完了，待验收' },
    { taskId: 't3', title: '跑测试', body: 'Codex 执行失败：额度用完' },
  ])
  assert.deepEqual(agentNotices(null, next), [])
})
