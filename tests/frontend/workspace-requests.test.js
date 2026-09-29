import assert from 'node:assert/strict'
import test from 'node:test'
import { createWorkspaceRequests } from '../../src/workspaceRequests.js'

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function harness() {
  const reads = [], writes = [], values = [], pending = []
  const requests = createWorkspaceRequests({
    load: () => {
      const job = deferred()
      reads.push(job)
      return job.promise
    },
    action: (name, payload) => {
      const job = { ...deferred(), name, payload }
      writes.push(job)
      return job.promise
    },
    onData: value => values.push(value),
    onPending: name => pending.push(name),
  })
  return { requests, reads, writes, values, pending }
}

const response = (state, result = { id: 'saved-id' }) => ({ state, result })

test('an old poll cannot overwrite a completed ordinary save; no extra read is needed', async () => {
  const h = harness()
  const poll = h.requests.refresh()
  const save = h.requests.mutate('create_record', { content: '新记录' })
  h.writes[0].resolve(response('after-save'))
  await save
  h.reads[0].resolve('before-save')
  await poll
  assert.deepEqual(h.values, ['after-save'])
  assert.equal(h.reads.length, 1)
  assert.deepEqual(h.pending, ['create_record', null])
})

test('overlapping saves wait for all completions then read authoritative state', async () => {
  const h = harness()
  const first = h.requests.mutate('first', {})
  const second = h.requests.mutate('second', {})
  h.writes[1].resolve(response('snapshot-before-first-finished'))
  await second
  assert.deepEqual(h.values, [])
  assert.equal(h.pending.at(-1), 'first')
  h.writes[0].resolve(response('another-old-snapshot'))
  await Promise.resolve()
  assert.equal(h.reads.length, 1)
  h.reads[0].resolve('both-saved')
  await first
  assert.deepEqual(h.values, ['both-saved'])
  assert.equal(h.pending.at(-1), null)
})

test('reverse completion order also requires a fresh read rather than trusting launch order', async () => {
  const h = harness()
  const first = h.requests.mutate('first', {})
  const second = h.requests.mutate('second', {})
  h.writes[0].resolve(response('first-result'))
  await first
  h.writes[1].resolve(response('second-request-captured-before-first-write'))
  await Promise.resolve()
  h.reads[0].resolve('authoritative')
  await second
  assert.deepEqual(h.values, ['authoritative'])
})

test('polls during a write are skipped and stale refresh errors are ignored', async () => {
  const h = harness()
  const oldPoll = h.requests.refresh()
  const save = h.requests.mutate('save', {})
  await h.requests.refresh()
  assert.equal(h.reads.length, 1)
  h.writes[0].resolve(response('saved'))
  await save
  h.reads[0].reject(new Error('obsolete read failed'))
  await oldPoll
  assert.deepEqual(h.values, ['saved'])
})

test('read failure after successful overlapping writes does not turn saving into failure', async () => {
  const h = harness()
  const first = h.requests.mutate('first', {})
  const second = h.requests.mutate('second', {})
  h.writes[0].resolve(response('first'))
  await first
  h.writes[1].resolve(response('second', { id: 'second-id' }))
  await Promise.resolve()
  h.reads[0].reject(new Error('read unavailable'))
  const result = await second
  assert.equal(result.result.id, 'second-id')
  assert.equal(result.refreshError.message, 'read unavailable')
  assert.equal(h.writes.length, 2)
  assert.deepEqual(h.values, [])
})

test('ambiguous write failure refreshes state without repeating the mutation', async () => {
  const h = harness()
  const save = h.requests.mutate('save', {})
  const failure = assert.rejects(save, /connection lost/)
  h.writes[0].reject(new Error('connection lost'))
  await Promise.resolve()
  h.reads[0].resolve('write-did-reach-server')
  await failure
  assert.deepEqual(h.values, ['write-did-reach-server'])
  assert.equal(h.writes.length, 1)
})

test('latest read wins, stopped callbacks are ignored, and restarting loads again', async () => {
  const h = harness()
  const first = h.requests.refresh()
  const second = h.requests.refresh()
  h.reads[1].resolve('new')
  await second
  h.reads[0].resolve('old')
  await first
  const save = h.requests.mutate('save', {})
  h.requests.stop()
  h.writes[0].resolve(response('after-unmount'))
  await save
  await h.requests.refresh()
  assert.deepEqual(h.values, ['new'])
  assert.equal(h.reads.length, 2)
  h.requests.start()
  const restarted = h.requests.refresh()
  h.reads[2].resolve('restarted')
  await restarted
  assert.deepEqual(h.values, ['new', 'restarted'])
})

test('a new write invalidates the reconciliation read of an earlier batch', async () => {
  const h = harness()
  const first = h.requests.mutate('first', {})
  const second = h.requests.mutate('second', {})
  h.writes[0].resolve(response('first'))
  await first
  h.writes[1].resolve(response('second'))
  await Promise.resolve()
  const third = h.requests.mutate('third', {})
  h.writes[2].resolve(response('third-saved'))
  await third
  h.reads[0].resolve('before-third')
  await second
  assert.deepEqual(h.values, ['third-saved'])
})
