export const EMPTY_DRAFT = {
  text: '',
  materialIds: [],
  revision: 0,
  requestId: null,
  sending: false,
}

export function learningDraftReducer(draft, event) {
  switch (event.type) {
    case 'text':
      if (event.text === draft.text) return draft
      return { ...draft, text: event.text, revision: draft.revision + 1, requestId: null }
    case 'material': {
      const materialIds = event.selected
        ? [...new Set([...draft.materialIds, event.id])]
        : draft.materialIds.filter(id => id !== event.id)
      return { ...draft, materialIds, revision: draft.revision + 1, requestId: null }
    }
    case 'sending':
      return { ...draft, sending: true, requestId: event.requestId }
    case 'available-materials': {
      const materialIds = draft.materialIds.filter(id => event.ids.includes(id))
      if (materialIds.length === draft.materialIds.length) return draft
      return { ...draft, materialIds, revision: draft.revision + 1, requestId: null }
    }
    case 'settled':
      // A response owns only the draft revision submitted with that request.
      if (event.saved && draft.revision === event.revision) {
        return { ...EMPTY_DRAFT, revision: draft.revision + 1 }
      }
      return { ...draft, sending: false }
    default:
      return draft
  }
}

export function createLatestLoader(load, onValue, onError) {
  let version = 0
  let active = true
  return {
    async reload() {
      if (!active) return
      const request = ++version
      try {
        const value = await load()
        if (request !== version) return
        onValue(value)
        return value
      } catch (error) {
        if (request === version) onError(error)
      }
    },
    start() {
      active = true
    },
    stop() {
      active = false
      version += 1
    },
  }
}
