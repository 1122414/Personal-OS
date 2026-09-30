// Patch running agent runs into the last full snapshot. When a run has ended or a new
// one appeared, the snapshot is stale in other ways too (status, changes), so ask for a full refresh.
export function mergeRunningRuns(data, runs) {
  if (!data) return { data, stale: true }
  const live = new Map(runs.map(run => [run.id, run]))
  const known = new Set(data.agent_runs.map(run => run.id))
  const stale = data.agent_runs.some(run => run.status === 'Running' && !live.has(run.id)) || runs.some(run => !known.has(run.id))
  return { data: { ...data, agent_runs: data.agent_runs.map(run => live.get(run.id) || run) }, stale }
}

// Turns that ended between two snapshots and need the user. Canceled or interrupted turns were the user's own doing.
export function agentNotices(previous, next) {
  if (!previous || !next) return []
  const before = new Map(previous.agent_runs.map(run => [run.id, run.status]))
  return next.agent_runs.filter(run => before.get(run.id) === 'Running' && ['Finished', 'Failed'].includes(run.status)).map(run => {
    const task = next.tasks.find(item => item.id === run.task_id)
    const agent = run.agent_id || 'Agent'
    const body = run.status === 'Failed' ? `${agent} 执行失败：${(run.error || '').split('\n')[0].slice(0, 120) || '请查看日志'}`
      : run.needs_reply ? `${agent} 在等你回复` : `${agent} 这一轮做完了，待验收`
    return { taskId: run.task_id, title: task?.title || 'Agent 任务', body }
  })
}
