import { useEffect, useRef, useState } from 'react'
import { action, loadRunningRuns, loadState } from './api.js'
import { agentNotices, mergeRunningRuns } from './liveRuns.js'
import { createWorkspaceRequests } from './workspaceRequests.js'

export default function useWorkspaceData(onError) {
  const [data, setData] = useState(null)
  const [pending, setPending] = useState(null)
  const [loading, setLoading] = useState(true)
  const [requests] = useState(() => createWorkspaceRequests({
    load: loadState,
    loadRunning: loadRunningRuns,
    action,
    onData: setData,
    onPending: setPending,
  }))
  const hasRunningAgent = !!data?.agent_runs?.some(item => item.status === 'Running')
  const latest = useRef(data)
  latest.current = data
  const noticed = useRef(null)

  useEffect(() => {
    const notify = window.webkit?.messageHandlers?.notify
    if (notify && data) agentNotices(noticed.current, data).forEach(notice => notify.postMessage(notice))
    noticed.current = data
  }, [data])

  useEffect(() => {
    let mounted = true
    requests.start()
    requests.refresh()
      .catch(error => { if (mounted) onError({ error: error.message }) })
      .finally(() => { if (mounted) setLoading(false) })
    return () => {
      mounted = false
      requests.stop()
    }
  }, [requests, onError])

  useEffect(() => {
    const timer = setInterval(() => requests.refresh().catch(() => {}), 30000)
    return () => clearInterval(timer)
  }, [requests])

  useEffect(() => {
    const timer = setInterval(async () => {
      const runs = await requests.live().catch(() => null)
      if (!runs) return
      const merged = mergeRunningRuns(latest.current, runs)
      if (merged.stale) requests.refresh().catch(() => {})
      else if (runs.length) setData(merged.data)
    }, hasRunningAgent ? 1500 : 5000)
    return () => clearInterval(timer)
  }, [requests, hasRunningAgent])

  return { data, pending, loading, refresh: requests.refresh, mutate: requests.mutate }
}
