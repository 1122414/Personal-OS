import assert from 'node:assert/strict'
import test from 'node:test'
import { mergeRunningRuns } from '../../src/liveRuns.js'
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
