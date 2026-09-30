// Actions that call a model or a remote source and may run for minutes.
export const BACKGROUND_JOBS = new Set(['refresh_channel', 'generate_brief', 'generate_project_pulse', 'summarize_log', 'sync_workbuddy', 'generate_cards', 'sync_traces'])

// Read responses are snapshots. Mutations invalidate older reads; overlapping
// mutations need one fresh snapshot after all writes settle. Background jobs do
// not hold back other saves or polls; their result arrives through a fresh read.
export function createWorkspaceRequests({ load, action, onData, onPending, loadRunning }) {
  let active = true
  let version = 0
  let overlapping = false
  const writes = new Map()
  const jobs = new Map()

  function publishPending() {
    if (active) onPending([...writes.values()].at(-1) || [...jobs.values()].at(-1) || null)
  }

  async function runJob(name, payload) {
    const id = ++version
    jobs.set(id, name)
    publishPending()
    let response, failure, refreshError
    try {
      response = await action(name, payload)
    } catch (error) {
      failure = error
    } finally {
      jobs.delete(id)
      version += 1
      publishPending()
      if (writes.size) overlapping = true
      else {
        try {
          await refresh()
        } catch (error) {
          refreshError = error
        }
      }
    }
    if (failure) throw failure
    return { ...response, refreshError }
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

  // A live read never invalidates others; it is dropped once a write or newer snapshot starts.
  async function live() {
    if (!active || writes.size || !loadRunning) return
    const request = version
    const runs = await loadRunning()
    if (!active || writes.size || request !== version) return
    return runs
  }

  async function mutate(name, payload) {
    if (!active) throw new Error('工作空间已关闭，请重新打开后操作')
    if (BACKGROUND_JOBS.has(name)) return runJob(name, payload)
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
    live,
    mutate,
    start() { active = true },
    stop() {
      active = false
      version += 1
    },
  }
}
