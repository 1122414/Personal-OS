// Read responses are snapshots. Mutations invalidate older reads; overlapping
// mutations need one fresh snapshot after all writes settle.
export function createWorkspaceRequests({ load, action, onData, onPending }) {
  let active = true
  let version = 0
  let overlapping = false
  const writes = new Map()

  function publishPending() {
    if (active) onPending([...writes.values()].at(-1) || null)
  }

  async function refresh() {
    if (!active || writes.size) return
    const request = ++version
    try {
      const next = await load()
      if (!active || request !== version) return
      onData(next)
      return next
    } catch (error) {
      if (active && request === version) throw error
    }
  }

  async function mutate(name, payload) {
    if (!active) throw new Error('工作空间已关闭，请重新打开后操作')
    const id = ++version
    writes.set(id, name)
    if (writes.size > 1) overlapping = true
    publishPending()

    let response, failure, refreshError
    try {
      response = await action(name, payload)
      if (active && !overlapping) onData(response.state)
    } catch (error) {
      failure = error
    } finally {
      writes.delete(id)
      publishPending()
      if (!writes.size) {
        const needsRefresh = overlapping || !!failure
        overlapping = false
        if (needsRefresh) {
          try {
            await refresh()
          } catch (error) {
            // A failed read must not change a successful write into a failed one.
            refreshError = error
          }
        }
      }
    }

    if (failure) throw failure
    return { ...response, refreshError }
  }

  return {
    refresh,
    mutate,
    start() { active = true },
    stop() {
      active = false
      version += 1
    },
  }
}
