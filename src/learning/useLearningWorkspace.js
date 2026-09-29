import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { loadLearning } from '../api.js'
import { createLatestLoader, EMPTY_DRAFT, learningDraftReducer } from './state.js'

function pollDelay(detail) {
  const busy = detail?.runs.some(run => run.status === 'Running')
    || detail?.materials.some(item => item.read_status === 'parsing')
    || detail?.summary.state === 'updating'
  return busy ? 700 : 5000
}

export function useLearningDetail(topicId) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const loader = useMemo(() => createLatestLoader(
    () => loadLearning(topicId),
    next => { setDetail(next); setError('') },
    failure => setError(failure.message),
  ), [topicId])

  useEffect(() => {
    let active = true
    let timer
    loader.start()
    async function tick() {
      const next = await loader.reload()
      if (active) timer = setTimeout(tick, pollDelay(next))
    }
    tick()
    return () => {
      active = false
      clearTimeout(timer)
      loader.stop()
    }
  }, [loader])

  return { detail, error, reload: loader.reload }
}

export function useLearningDraft(topicId, run, reload, materials) {
  const [draft, dispatch] = useReducer(learningDraftReducer, EMPTY_DRAFT)
  const pending = useRef(false)

  useEffect(() => {
    if (materials) dispatch({ type: 'available-materials', ids: materials.map(item => item.id) })
  }, [materials])

  async function send() {
    if (!draft.text.trim() || pending.current) return false
    pending.current = true
    const requestId = draft.requestId || crypto.randomUUID()
    dispatch({ type: 'sending', requestId })
    let saved = false
    try {
      saved = !!await run('send_learning_message', {
        id: topicId,
        text: draft.text,
        material_ids: draft.materialIds,
        request_id: requestId,
      })
      return saved
    } finally {
      dispatch({ type: 'settled', revision: draft.revision, saved })
      pending.current = false
      if (saved) await reload()
    }
  }

  return {
    ...draft,
    send,
    setText: text => dispatch({ type: 'text', text }),
    selectMaterial: (id, selected) => dispatch({ type: 'material', id, selected }),
  }
}
