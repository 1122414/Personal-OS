import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, STATUS, runDuration, taskState, timeLabel } from '../ui.jsx'
import { Changes, Composer, Conversation, RUN_STATUS } from './AgentChat.jsx'

const tabs = [['all', '全部'], ['Inbox', '待派出'], ['Running', '运行中'], ['Reply', '等你回复'], ['Review', '待验收'], ['Done', '已完成'], ['Blocked', '失败或取消'], ['archived', '已归档']]
const COLUMNS = [['Inbox', '待派出'], ['Running', '运行中'], ['Reply', '等你回复'], ['Review', '待验收'], ['Done', '已完成'], ['Blocked', '失败或取消']]
const DONE_LIMIT = 12
function Dispatch({ task, agents, latest, run }) {
  const available = agents.filter(agent => agent.available)
  const [choice, setChoice] = useState('')
  if (!available.length) return <span className="muted">本机未找到可用 Agent，请在设置中填写命令路径</span>
  const value = choice || (available.some(agent => agent.id === task.runtime) ? task.runtime : available[0].id)
  return <span className="dispatch"><select aria-label="执行通道" value={value} onChange={event => setChoice(event.target.value)}>{available.map(agent => <option key={agent.id} value={agent.id}>{agent.label}</option>)}</select><Button variant="primary" onClick={() => run('start_agent', { task_id: task.id, runtime: value })}>{latest && latest.status !== 'Finished' ? '重试' : '派出'}</Button></span>
}

function Board({ tasks, projects, allRuns, latestRun, selectedId, select }) {
  return <div className="task-board">{COLUMNS.map(([status, label]) => {
    const cards = tasks.filter(task => taskState(task, allRuns) === status)
    const shown = status === 'Done' ? cards.slice(0, DONE_LIMIT) : cards
    return <section className={`board-column board-${status}`} key={status}>
      <header><span>{label}</span><small>{cards.length}</small></header>
      {shown.map(task => {
        const last = latestRun(task.id)
        const project = projects.find(item => item.id === task.project_id)?.name
        return <button key={task.id} className={`board-card ${selectedId === task.id ? 'selected' : ''}`} onClick={() => select(task.id)}>
          <strong>{task.title}</strong>
          <small>{[task.agent_id || 'Agent', last && runDuration(last), project].filter(Boolean).join(' · ')}</small>
          {last?.log_tail?.length > 0 && <span className="board-log">{last.log_tail.at(-1)}</span>}
        </button>
      })}
      {cards.length > shown.length && <small className="board-more">另有 {cards.length - shown.length} 项，切到列表查看</small>}
    </section>
  })}</div>
}

export default function Tasks({ data, run, open, focus, navigate }) {
  const [tab, setTab] = useState('all')
  const [view, setView] = useState('list')
  const [selectedId, select] = useState(focus || null)
  useEffect(() => { if (focus) select(focus) }, [focus])
  const agents = data.runtime?.agents || []
  const filtered = view === 'board' ? data.tasks.filter(task => !task.archived_at) : data.tasks.filter(task => tab === 'archived' ? !!task.archived_at : !task.archived_at && (tab === 'all' || taskState(task, data.agent_runs) === tab))
  const selected = filtered.find(task => task.id === selectedId) || filtered[0]
  const project = data.projects.find(item => item.id === selected?.project_id)
  const runs = data.agent_runs.filter(item => item.task_id === selected?.id)
  const artifacts = data.artifacts.filter(item => item.task_id === selected?.id)
  const events = data.events.filter(event => event.subject_kind === 'task' && event.subject_id === selected?.id).slice(0, 6)
  const latestRun = taskId => data.agent_runs.find(item => item.task_id === taskId)
  const pendingKnowledge = data.knowledge_proposals.filter(item => item.status === 'Review').length

  return <div className="page tasks-page">
    <div className="page-toolbar">{view === 'list' ? <div className="tabs">{tabs.map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div> : <span className="muted">按状态分列，已归档的不显示。</span>}<div className="inline-actions"><div className="tabs view-toggle" role="group" aria-label="Agent 任务视图">{[['list', '列表'], ['board', '看板']].map(([key, label]) => <button key={key} className={view === key ? 'active' : ''} aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>)}</div><Button variant="primary" onClick={() => open('task')}>＋ 新建 Agent 任务</Button></div></div>
    {pendingKnowledge > 0 && <p className="notice">有 {pendingKnowledge} 条知识写入等你确认。<button className="text-link" onClick={() => navigate('review')}>去确认 →</button></p>}
    <div className={`split-layout task-split ${view === 'board' ? 'board-split' : ''}`}>
      {view === 'board' ? <Panel className="list-panel board-panel"><Board tasks={filtered} projects={data.projects} allRuns={data.agent_runs} latestRun={latestRun} selectedId={selected?.id} select={select} /></Panel> : <Panel className="list-panel">
        {filtered.length ? <div className="task-table"><div className="table-head"><span>任务名称</span><span>所属项目</span><span>通道</span><span>对话</span><span>状态</span></div>{filtered.map(task => <button key={task.id} className={`task-row ${selected?.id === task.id ? 'selected' : ''}`} onClick={() => select(task.id)}>
          <span className="task-title"><i className={`task-ring ${task.status === 'Done' ? 'checked' : ''}`}>{task.status === 'Done' ? '✓' : ''}</i><strong>{task.title}</strong></span>
          <span>{data.projects.find(item => item.id === task.project_id)?.name || '—'}</span><span>{task.agent_id || '—'}</span><span>{data.agent_runs.filter(item => item.task_id === task.id).length || '—'}{data.agent_runs.some(item => item.task_id === task.id) ? ' 轮' : ''}</span><span className={`status status-${taskState(task, data.agent_runs)}`}>{STATUS[taskState(task, data.agent_runs)]}</span>
        </button>)}</div> : <Empty title="还没有 Agent 任务" detail="把要改代码或整理文件的事交给 Agent：选一个有本地目录的项目，写清要求与完成标准。自己要做的事请放进「待办」。" action={<Button onClick={() => open('task')}>新建 Agent 任务</Button>} />}
      </Panel>}
      <Panel className="detail-panel">
        {selected ? <><div className="detail-title"><div><span className="overline">TASK DETAIL</span><h2>{selected.title}</h2></div><span className={`status status-${taskState(selected, runs)}`}>{STATUS[taskState(selected, runs)]}</span></div>
          <div className="meta-grid"><div><small>项目目录</small><strong>{project?.name || '未关联项目'}</strong></div><div><small>执行通道</small><strong>{selected.agent_id || '未选择'}</strong></div><div><small>对话</small><strong>{runs.length} 轮</strong></div><div><small>最近一次</small><strong>{runs[0] ? `${RUN_STATUS[runs[0].status] || runs[0].status} · ${runDuration(runs[0])}` : '尚未派出'}</strong></div></div>
          {selected.record_id && <a href={`#records/${selected.record_id}`}>查看来源记录 →</a>}
          <Conversation task={selected} runs={runs} agents={agents} />
          <Changes artifacts={artifacts} />
          <details className="detail-section"><summary>活动记录</summary>{events.length ? events.map(event => <div className="activity-row" key={event.id}><span>{timeLabel(event.created_at)}</span><span>{event.type}</span></div>) : <p>暂无活动。</p>}</details>
          <div className="detail-actions wrap"><Button onClick={() => open('task-edit', selected)}>编辑</Button>{!['Running','Review'].includes(selected.status) && <Button onClick={() => run('archive_task', { id: selected.id, restore: !!selected.archived_at })}>{selected.archived_at ? '取消归档' : '归档'}</Button>}{selected.status === 'Done' && <Button onClick={() => run('reopen_task', { id: selected.id })}>重新打开</Button>}{!selected.archived_at && (['Inbox','Planned'].includes(selected.status) || (selected.status === 'Blocked' && !runs.length)) && <Dispatch key={selected.id} task={selected} agents={agents} latest={runs[0]} run={run} />}{selected.status === 'Done' && <Button onClick={() => open('knowledge', selected)}>沉淀为知识</Button>}</div>
          {!selected.archived_at && runs.length > 0 && ['Running', 'Review', 'Blocked'].includes(selected.status) && <Composer key={selected.id} task={selected} runs={runs} run={run} />}
        </> : <Empty title="选择一个 Agent 任务" detail="要求、执行记录与产物会在这里呈现。" />}
      </Panel>
    </div>
  </div>
}
