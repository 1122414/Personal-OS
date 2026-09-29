import assert from 'node:assert/strict'
import test from 'node:test'
import { createLatestLoader, EMPTY_DRAFT, learningDraftReducer } from '../../src/learning/state.js'

function draftSession() {
  let current = EMPTY_DRAFT
  return {
    get value() { return current },
    dispatch(event) { current = learningDraftReducer(current, event) },
  }
}

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('successful send clears only the submitted draft', () => {
  const session = draftSession()
  session.dispatch({ type: 'text', text: '请解释参数透传' })
  session.dispatch({ type: 'material', id: 'pdf-1', selected: true })
  const revision = session.value.revision
  session.dispatch({ type: 'sending', requestId: 'request-1' })
  session.dispatch({ type: 'settled', revision, saved: true })
  assert.equal(session.value.text, '')
  assert.deepEqual(session.value.materialIds, [])
  assert.equal(session.value.requestId, null)
  assert.equal(session.value.sending, false)
})

test('late send completion preserves a new question and its material selection', async () => {
  const session = draftSession()
  session.dispatch({ type: 'text', text: '第一个问题' })
  const revision = session.value.revision
  const response = deferred()
  session.dispatch({ type: 'sending', requestId: 'request-1' })
  const completion = response.promise.then(saved => session.dispatch({ type: 'settled', revision, saved }))
  session.dispatch({ type: 'text', text: '先写下一个问题' })
  session.dispatch({ type: 'material', id: 'pdf-2', selected: true })
  response.resolve(true)
  await completion
  assert.equal(session.value.text, '先写下一个问题')
  assert.deepEqual(session.value.materialIds, ['pdf-2'])
  assert.equal(session.value.requestId, null)
  assert.equal(session.value.sending, false)
})

test('failed send retains its idempotency key; changing any payload resets it', () => {
  const session = draftSession()
  session.dispatch({ type: 'text', text: '请再讲一遍' })
  const revision = session.value.revision
  session.dispatch({ type: 'sending', requestId: 'same-on-retry' })
  session.dispatch({ type: 'settled', revision, saved: false })
  assert.equal(session.value.requestId, 'same-on-retry')
  assert.equal(session.value.text, '请再讲一遍')
  session.dispatch({ type: 'material', id: 'image', selected: true })
  assert.equal(session.value.requestId, null)
  session.dispatch({ type: 'sending', requestId: 'new-request' })
  session.dispatch({ type: 'text', text: '跳过练习，换方向' })
  assert.equal(session.value.requestId, null)
})

test('editing away and back during send does not let an old response erase intent', () => {
  const session = draftSession()
  session.dispatch({ type: 'text', text: '问题' })
  const revision = session.value.revision
  session.dispatch({ type: 'sending', requestId: 'request-1' })
  session.dispatch({ type: 'text', text: '另一个问题' })
  session.dispatch({ type: 'text', text: '问题' })
  session.dispatch({ type: 'settled', revision, saved: true })
  assert.equal(session.value.text, '问题')
})

test('out-of-order detail responses cannot replace the latest result', async () => {
  const old = deferred(), fresh = deferred()
  const values = [], errors = []
  let count = 0
  const loader = createLatestLoader(() => ++count === 1 ? old.promise : fresh.promise, value => values.push(value), error => errors.push(error))
  const first = loader.reload(), second = loader.reload()
  fresh.resolve('new reply')
  await second
  old.resolve('old reply')
  await first
  assert.deepEqual(values, ['new reply'])
  assert.deepEqual(errors, [])
})

test('obsolete errors and responses after unmount are ignored, current errors recover', async () => {
  const old = deferred(), fresh = deferred(), abandoned = deferred()
  const requests = [old, fresh, abandoned]
  const values = [], errors = []
  const loader = createLatestLoader(() => requests.shift().promise, value => values.push(value), error => errors.push(error.message))
  const first = loader.reload(), second = loader.reload()
  fresh.resolve('latest')
  await second
  old.reject(new Error('obsolete failure'))
  await first
  const third = loader.reload()
  loader.stop()
  abandoned.resolve('after unmount')
  await third
  assert.deepEqual(values, ['latest'])
  assert.deepEqual(errors, [])
  // A send callback may ask to reload after the topic has already unmounted.
  await loader.reload()
  assert.deepEqual(errors, [])
  loader.start()
  requests.push({ promise: Promise.reject(new Error('current failure')) })
  await loader.reload()
  assert.deepEqual(errors, ['current failure'])
  requests.push({ promise: Promise.resolve('recovered') })
  await loader.reload()
  assert.deepEqual(values, ['latest', 'recovered'])
})

test('unlinking a selected material drops only that selection, not the question', () => {
  const session = draftSession()
  session.dispatch({ type: 'text', text: '保留我的问题' })
  session.dispatch({ type: 'material', id: 'removed', selected: true })
  session.dispatch({ type: 'material', id: 'kept', selected: true })
  const unchanged = session.value
  session.dispatch({ type: 'available-materials', ids: ['removed', 'kept'] })
  assert.equal(session.value, unchanged)
  session.dispatch({ type: 'available-materials', ids: ['kept'] })
  assert.deepEqual(session.value.materialIds, ['kept'])
  assert.equal(session.value.text, '保留我的问题')
})
