import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, STATUS, PRIORITY, dateLabel, timeLabel } from '../ui.jsx'

const tabs = [['all', '全部'], ['Running', '进行中'], ['Review', '待审核'], ['Done', '已完成'], ['Blocked', '已阻塞']]

export default function Tasks({ data, run, open, focus }) {
  const [tab, setTab] = useState('all')
  const [selectedId, select] = useState(focus || null)
  useEffect(() => { if (focus) select(focus) }, [focus])
  const filtered = data.tasks.filter(task => tab === 'all' || task.status === tab)
  const selected = filtered.find(task => task.id === selectedId) || filtered[0]
  const project = data.projects.find(item => item.id === selected?.project_id)
  const runs = data.agent_runs.filter(item => item.task_id === selected?.id)
  const artifacts = data.artifacts.filter(item => item.task_id === selected?.id)
  const events = data.events.filter(event => event.subject_kind === 'task' && event.subject_id === selected?.id).slice(0, 6)

  return <div className="page tasks-page">
    <div className="page-toolbar"><div className="tabs">{tabs.map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div><Button variant="primary" onClick={() => open('task')}>＋ 新建任务</Button></div>
    <div className="split-layout task-split">
      <Panel className="list-panel">
        {filtered.length ? <div className="task-table"><div className="table-head"><span>任务名称</span><span>所属项目</span><span>截止时间</span><span>优先级</span><span>状态</span></div>{filtered.map(task => <button key={task.id} className={`task-row ${selected?.id === task.id ? 'selected' : ''}`} onClick={() => select(task.id)}>
          <span className="task-title"><i className={`task-ring ${task.status === 'Done' ? 'checked' : ''}`}>{task.status === 'Done' ? '✓' : ''}</i><strong>{task.title}</strong></span>
          <span>{data.projects.find(item => item.id === task.project_id)?.name || '—'}</span><span>{dateLabel(task.deadline)}</span><span className={`priority priority-${task.priority}`}>{PRIORITY[task.priority]}</span><span className={`status status-${task.status}`}>{STATUS[task.status]}</span>
        </button>)}</div> : <Empty title="这里还没有任务" detail="从一句话开始，逐步让计划变成成果。" action={<Button onClick={() => open('task')}>创建任务</Button>} />}
      </Panel>
      <Panel className="detail-panel">
        {selected ? <><div className="detail-title"><div><span className="overline">TASK DETAIL</span><h2>{selected.title}</h2></div><span className={`status status-${selected.status}`}>{STATUS[selected.status]}</span></div>
          <div className="meta-grid"><div><small>所属项目</small><strong>{project?.name || '无项目'}</strong></div><div><small>截止时间</small><strong>{dateLabel(selected.deadline)}</strong></div><div><small>优先级</small><strong>{PRIORITY[selected.priority]}</strong></div><div><small>执行人</small><strong>{selected.executor_type === 'agent' ? selected.agent_id || '待选择 Agent' : '我自己'}</strong></div></div>
          <div className="detail-section"><h3>任务描述</h3><p>{selected.description || '暂无描述。可以编辑任务补充背景与验收标准。'}</p></div>
          {runs.length > 0 && <div className="detail-section"><h3>Agent Run</h3><p className="notice">Codex 直接修改工作目录，结果审核不撤销已有改动。失败或取消后也请核对产物。</p>{runs.map(item => <div className="run-card" key={item.id}><strong>{item.agent_id}</strong><span>{item.status} · {timeLabel(item.started_at)}</span><p>{item.result || item.error || '正在执行，结果返回后进入审核。'}</p></div>)}</div>}
          {artifacts.length > 0 && <div className="detail-section"><h3>产物</h3>{artifacts.map(item => <div className="artifact-row" key={item.id}>{item.name} · {{ Created: '新建', Modified: '修改', Deleted: '删除' }[item.change] || '变更'}</div>)}</div>}
          <div className="detail-section"><h3>活动记录</h3>{events.length ? events.map(event => <div className="activity-row" key={event.id}><span>{timeLabel(event.created_at)}</span><span>{event.type}</span></div>) : <p>暂无活动。</p>}</div>
          <div className="detail-actions wrap"><Button onClick={() => open('task-edit', selected)}>编辑任务</Button>{data.daily_plans.some(plan => plan.date === data.today && plan.confirmed_at) && selected.planned_date !== data.today && !['Done','Blocked'].includes(selected.status) && <Button onClick={() => run('add_to_today', { task_id: selected.id })}>加入今天</Button>}{selected.executor_type === 'self' && selected.status !== 'Done' && <Button variant="primary" onClick={() => run('complete_task', { id: selected.id })}>确认完成</Button>}{selected.executor_type === 'agent' && ['Inbox','Planned','Blocked'].includes(selected.status) && <Button variant="primary" onClick={() => run('start_agent', { task_id: selected.id })}>交给 Codex</Button>}{selected.executor_type === 'agent' && selected.status === 'Running' && runs[0] && <Button onClick={() => run('cancel_agent', { id: runs[0].id })}>取消执行</Button>}{selected.status === 'Done' && <Button onClick={() => open('knowledge', selected)}>沉淀为知识</Button>}</div>
        </> : <Empty title="选择一个任务" detail="任务详情、执行记录与产物会在这里呈现。" />}
      </Panel>
    </div>
  </div>
}
