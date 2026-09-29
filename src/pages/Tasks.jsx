import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, STATUS, PRIORITY, dateLabel, runDuration, timeLabel } from '../ui.jsx'

const tabs = [['all', '全部'], ['Running', '进行中'], ['Review', '待审核'], ['Done', '已完成'], ['Blocked', '已阻塞'], ['archived', '已归档']]
const COLUMNS = [['Inbox', '待办'], ['Planned', '计划中'], ['Running', '运行中'], ['Review', '待审核'], ['Done', '完成'], ['Blocked', '阻塞']]
const DONE_LIMIT = 12
const RUN_STATUS = { Running: '运行中', Finished: '已完成', Failed: '失败', Canceled: '已取消', Interrupted: '已中断' }

function Dispatch({ task, agents, latest, run }) {
  const available = agents.filter(agent => agent.available)
  const [choice, setChoice] = useState('')
  if (!available.length) return <span className="muted">本机未找到可用 Agent，请在设置中填写命令路径</span>
  const value = choice || (available.some(agent => agent.id === task.runtime) ? task.runtime : available[0].id)
  return <span className="dispatch"><select aria-label="执行通道" value={value} onChange={event => setChoice(event.target.value)}>{available.map(agent => <option key={agent.id} value={agent.id}>{agent.label}</option>)}</select><Button variant="primary" onClick={() => run('start_agent', { task_id: task.id, runtime: value })}>{latest && latest.status !== 'Finished' ? '重试' : '派出'}</Button></span>
}

function AgentRuns({ runs, agents }) {
  const meta = agents.find(agent => agent.id === (runs[0].runtime || 'codex'))
  const label = meta?.label || runs[0].agent_id
  return <div className="detail-section"><h3>执行记录</h3>
    <p className="notice">{label} {meta?.sandboxed ? '在系统沙箱中运行，只能写入工作目录。' : '直接修改工作目录。'}结果审核不撤销已有改动，失败或取消后也请核对产物。</p>
    {runs.map((item, index) => <div className="run-card" key={item.id}>
      <div className="run-head"><strong>{item.agent_id}</strong><span className={`run-status run-${item.status}`}>{RUN_STATUS[item.status] || item.status}</span><span>{timeLabel(item.started_at)} · {runDuration(item)}</span></div>
      {item.outside_writes?.length > 0 && <p className="notice">尝试写入工作目录以外：{item.outside_writes.join('、')}</p>}
      <p>{item.result || item.error || (item.status === 'Running' ? '正在执行，结果返回后进入审核。' : '没有返回结果。')}</p>
      {item.log_tail?.length > 0 && <details open={index === 0 && item.status === 'Running'}><summary>执行日志 · 最近 {item.log_tail.length} 行</summary><pre className="run-log">{item.log_tail.join('\n')}</pre></details>}
    </div>)}
  </div>
}

function Board({ tasks, projects, latestRun, selectedId, select }) {
  return <div className="task-board">{COLUMNS.map(([status, label]) => {
    const column = tasks.filter(task => task.status === status)
    const shown = status === 'Done' ? column.slice(0, DONE_LIMIT) : column
    return <section className={`board-column board-${status}`} key={status}>
      <header><span>{label}</span><small>{column.length}</small></header>
      {shown.map(task => {
        const last = latestRun(task.id)
        const project = projects.find(item => item.id === task.project_id)?.name
        return <button key={task.id} className={`board-card ${selectedId === task.id ? 'selected' : ''}`} onClick={() => select(task.id)}>
          <strong>{task.title}</strong>
          <small>{[task.executor_type === 'agent' ? task.agent_id || 'Agent' : '我自己', last && runDuration(last), project].filter(Boolean).join(' · ')}</small>
          {last?.log_tail?.length > 0 && <span className="board-log">{last.log_tail.at(-1)}</span>}
        </button>
      })}
      {column.length > shown.length && <small className="board-more">另有 {column.length - shown.length} 项，切到列表查看</small>}
    </section>
  })}</div>
}

export default function Tasks({ data, run, open, focus }) {
  const [tab, setTab] = useState('all')
  const [view, setView] = useState('list')
  const [selectedId, select] = useState(focus || null)
  useEffect(() => { if (focus) select(focus) }, [focus])
  const agents = data.runtime?.agents || []
  const filtered = view === 'board' ? data.tasks.filter(task => !task.archived_at) : data.tasks.filter(task => tab === 'archived' ? !!task.archived_at : !task.archived_at && (tab === 'all' || task.status === tab))
  const selected = filtered.find(task => task.id === selectedId) || filtered[0]
  const project = data.projects.find(item => item.id === selected?.project_id)
  const runs = data.agent_runs.filter(item => item.task_id === selected?.id)
  const artifacts = data.artifacts.filter(item => item.task_id === selected?.id)
  const events = data.events.filter(event => event.subject_kind === 'task' && event.subject_id === selected?.id).slice(0, 6)
  const latestRun = taskId => data.agent_runs.find(item => item.task_id === taskId)

  return <div className="page tasks-page">
    <div className="page-toolbar">{view === 'list' ? <div className="tabs">{tabs.map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div> : <span className="muted">按状态分列，已归档任务不显示。</span>}<div className="inline-actions"><div className="tabs view-toggle" role="group" aria-label="任务视图">{[['list', '列表'], ['board', '看板']].map(([key, label]) => <button key={key} className={view === key ? 'active' : ''} aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>)}</div><Button variant="primary" onClick={() => open('task')}>＋ 新建任务</Button></div></div>
    <div className={`split-layout task-split ${view === 'board' ? 'board-split' : ''}`}>
      {view === 'board' ? <Panel className="list-panel board-panel"><Board tasks={filtered} projects={data.projects} latestRun={latestRun} selectedId={selected?.id} select={select} /></Panel> : <Panel className="list-panel">
        {filtered.length ? <div className="task-table"><div className="table-head"><span>任务名称</span><span>所属项目</span><span>截止时间</span><span>优先级</span><span>状态</span></div>{filtered.map(task => <button key={task.id} className={`task-row ${selected?.id === task.id ? 'selected' : ''}`} onClick={() => select(task.id)}>
          <span className="task-title"><i className={`task-ring ${task.status === 'Done' ? 'checked' : ''}`}>{task.status === 'Done' ? '✓' : ''}</i><strong>{task.title}</strong></span>
          <span>{data.projects.find(item => item.id === task.project_id)?.name || '—'}</span><span>{dateLabel(task.deadline)}</span><span className={`priority priority-${task.priority}`}>{PRIORITY[task.priority]}</span><span className={`status status-${task.status}`}>{STATUS[task.status]}</span>
        </button>)}</div> : <Empty title="这里还没有任务" detail="从一句话开始，逐步让计划变成成果。" action={<Button onClick={() => open('task')}>创建任务</Button>} />}
      </Panel>}
      <Panel className="detail-panel">
        {selected ? <><div className="detail-title"><div><span className="overline">TASK DETAIL</span><h2>{selected.title}</h2></div><span className={`status status-${selected.status}`}>{STATUS[selected.status]}</span></div>
          <div className="meta-grid"><div><small>所属项目</small><strong>{project?.name || '无项目'}</strong></div><div><small>截止时间</small><strong>{dateLabel(selected.deadline)}</strong></div><div><small>优先级</small><strong>{PRIORITY[selected.priority]}</strong></div><div><small>执行人</small><strong>{selected.executor_type === 'agent' ? selected.agent_id || '待选择 Agent' : '我自己'}</strong></div></div>
          <div className="detail-section">{selected.record_id && <a href={`#records/${selected.record_id}`}>查看来源记录 →</a>}<h3>任务描述</h3><p>{selected.description || '暂无描述。可以编辑任务补充背景与验收标准。'}</p></div>
          {runs.length > 0 && <AgentRuns runs={runs} agents={agents} />}
          {artifacts.length > 0 && <div className="detail-section"><h3>产物</h3>{artifacts.map(item => <div className="artifact-row" key={item.id}>{item.name} · {{ Created: '新建', Modified: '修改', Deleted: '删除' }[item.change] || '变更'}</div>)}</div>}
          <div className="detail-section"><h3>活动记录</h3>{events.length ? events.map(event => <div className="activity-row" key={event.id}><span>{timeLabel(event.created_at)}</span><span>{event.type}</span></div>) : <p>暂无活动。</p>}</div>
          <div className="detail-actions wrap"><Button onClick={() => open('task-edit', selected)}>编辑任务</Button>{!['Running','Review'].includes(selected.status) && <Button onClick={() => run('archive_task', { id: selected.id, restore: !!selected.archived_at })}>{selected.archived_at ? '取消归档' : '归档'}</Button>}{['Done','Blocked'].includes(selected.status) && <Button onClick={() => run('reopen_task', { id: selected.id })}>重新打开</Button>}{data.daily_plans.some(plan => plan.date === data.today && plan.confirmed_at) && selected.planned_date !== data.today && !['Done','Blocked'].includes(selected.status) && <Button onClick={() => run('add_to_today', { task_id: selected.id })}>加入今天</Button>}{!selected.archived_at && selected.executor_type === 'self' && ['Inbox','Planned','Running'].includes(selected.status) && <Button variant="primary" onClick={() => run('complete_task', { id: selected.id })}>确认完成</Button>}{!selected.archived_at && selected.executor_type === 'agent' && ['Inbox','Planned','Blocked'].includes(selected.status) && <Dispatch key={selected.id} task={selected} agents={agents} latest={runs[0]} run={run} />}{selected.executor_type === 'agent' && selected.status === 'Running' && runs[0] && <Button onClick={() => run('cancel_agent', { id: runs[0].id })}>取消执行</Button>}{selected.status === 'Done' && <Button onClick={() => open('knowledge', selected)}>沉淀为知识</Button>}</div>
        </> : <Empty title="选择一个任务" detail="任务详情、执行记录与产物会在这里呈现。" />}
      </Panel>
    </div>
  </div>
}
