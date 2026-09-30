// Patch running agent runs into the last full snapshot. When a run has ended or a new
// one appeared, the snapshot is stale in other ways too (status, changes), so ask for a full refresh.
export function mergeRunningRuns(data, runs) {
  if (!data) return { data, stale: true }
  const live = new Map(runs.map(run => [run.id, run]))
  const known = new Set(data.agent_runs.map(run => run.id))
  const stale = data.agent_runs.some(run => run.status === 'Running' && !live.has(run.id)) || runs.some(run => !known.has(run.id))
  return { data: { ...data, agent_runs: data.agent_runs.map(run => live.get(run.id) || run) }, stale }
}
