import { useEffect, useState } from 'react'
import { action, loadState } from './api.js'
import { createWorkspaceRequests } from './workspaceRequests.js'

export default function useWorkspaceData(onError) {
  const [data, setData] = useState(null)
  const [pending, setPending] = useState(null)
  const [loading, setLoading] = useState(true)
  const [requests] = useState(() => createWorkspaceRequests({
    load: loadState,
    action,
    onData: setData,
    onPending: setPending,
  }))
  const hasRunningAgent = !!data?.agent_runs?.some(item => item.status === 'Running')

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
    const timer = setInterval(() => requests.refresh().catch(() => {}), hasRunningAgent ? 8000 : 30000)
    return () => clearInterval(timer)
  }, [requests, hasRunningAgent])

  return { data, pending, loading, refresh: requests.refresh, mutate: requests.mutate }
}
