import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, STATUS, dateLabel } from '../ui.jsx'

export default function Projects({ data, run, open, focus, navigate }) {
  const [filter, setFilter] = useState('Active')
  const [selectedId, select] = useState(focus || null)
  useEffect(() => { if (focus) select(focus) }, [focus])
  const filtered = data.projects.filter(item => item.status === filter)
  const selected = filtered.find(item => item.id === selectedId) || filtered[0]
  const tasks = data.tasks.filter(item => item.project_id === selected?.id)
  const activeTasks = tasks.filter(item => item.status !== 'Done')
  const decisions = data.decisions.filter(item => item.project_id === selected?.id)
  const artifacts = data.artifacts.filter(item => tasks.some(task => task.id === item.task_id))
  const activity = data.events.filter(item => item.project_id === selected?.id).slice(0, 4)
  const pulse = selected?.pulse || (selected ? `${selected.stage} · ${activeTasks.length} 项待推进任务，${decisions.filter(item => item.status === 'Active').length} 项有效决策。` : '')

  return <div className="page projects-page">
    <div className="page-toolbar"><div className="tabs">{[['Active', '进行中'], ['Paused', '已暂停'], ['Completed', '已完成']].map(([key, label]) => <button key={key} className={filter === key ? 'active' : ''} onClick={() => setFilter(key)}>{label}</button>)}</div><Button variant="primary" onClick={() => open('project')}>＋ 新建项目</Button></div>
    <div className="split-layout project-split"><Panel className="list-panel">
      {filtered.length ? filtered.map(project => <button key={project.id} className={`project-card ${selected?.id === project.id ? 'selected' : ''}`} onClick={() => select(project.id)}><div className="project-thumb">◇</div><div className="project-card-body"><strong>{project.name}</strong><p>{project.description || project.stage}</p><small>{data.tasks.filter(task => task.project_id === project.id && task.status !== 'Done').length} 项进行中 · {project.stage}</small></div></button>) : <Empty title="暂无此类项目" action={<Button onClick={() => open('project')}>创建项目</Button>} />}
    </Panel><Panel className="detail-panel project-detail">
      {selected ? <><div className="detail-title"><div><span className="overline">PROJECT CONTEXT</span><h2>{selected.name}</h2><p>{selected.description}</p></div><Button onClick={() => open('project-edit', selected)}>编辑项目</Button></div>
        <p className="muted">项目概览 · 下方包含 Agent 任务、决策与活动{selected.workspace_path ? ` · 目录 ${selected.workspace_path}` : ''}</p>
        <section className="pulse-box">{selected.pulse && <p className="muted">{selected.pulse_stale ? '项目已有变化，请更新态势' : '态势已同步至最近生成时'} · {selected.pulse_generated_at ? dateLabel(selected.pulse_generated_at) : '未记录生成时间'}</p>}<div className="panel-heading"><h3>项目脉搏</h3><div className="inline-actions">{data.runtime?.codex_available && <Button onClick={() => run('generate_project_pulse', { id: selected.id })}>AI 更新</Button>}<Button onClick={() => open('pulse', selected)}>手动编辑</Button></div></div><div className="pulse-grid"><div><small>当前阶段</small><strong>{selected.stage}</strong></div><div><small>最近进展与重点</small><p>{pulse}</p></div><div><small>Agent 任务</small><strong>{activeTasks.length} 项进行中</strong></div><div><small>风险与阻塞</small><p>{tasks.some(item => item.status === 'Blocked') ? '有 Agent 任务失败或被取消' : '暂无已标记阻塞'}</p></div></div></section>
        <div className="project-columns"><section><div className="panel-heading"><h3>Agent 任务</h3><button className="text-link" disabled={!selected.workspace_path} title={selected.workspace_path ? '' : '先编辑项目，填写本地工作目录'} onClick={() => open('task', { project_id: selected.id })}>＋ 派个 Agent 任务</button></div>{!selected.workspace_path && <p className="muted">这个项目还没有本地工作目录，Agent 无处执行。<button className="text-link" onClick={() => open('project-edit', selected)}>去填写</button></p>}{activeTasks.length ? activeTasks.slice(0, 5).map(task => <button className="mini-row" key={task.id} onClick={() => navigate('tasks', task.id)}><span className="task-ring" /><span>{task.title}</span><small>{STATUS[task.status]}</small></button>) : <p className="muted">暂无进行中的 Agent 任务。</p>}</section>
          <section><div className="panel-heading"><h3>近期决策</h3><button className="text-link" onClick={() => open('decision', { project_id: selected.id })}>＋ 记录</button></div>{decisions.length ? decisions.slice(0, 4).map(item => <div className="decision-row" key={item.id}><span className="small-symbol">✦</span><div><strong>{item.title}</strong><p>{item.reason || item.content}</p><small>{item.status} · {dateLabel(item.decided_at)}</small></div><button className="text-link" onClick={() => open('decision-edit', item)}>编辑</button></div>) : <p className="muted">重要方向会在这里留存。</p>}</section></div>
        {(artifacts.length > 0 || activity.length > 0) && <div className="project-columns"><section><h3>产物</h3>{artifacts.map(item => <div className="artifact-row" key={item.id}>{item.name} · {{ Created: '新建', Modified: '修改', Deleted: '删除' }[item.change] || '变更'}</div>)}</section><section><h3>最近活动</h3>{activity.map(item => <div className="activity-row" key={item.id}><span>{dateLabel(item.created_at)}</span><span>{item.type}</span></div>)}</section></div>}
      </> : <Empty title="选择或创建项目" detail="项目会把任务、决策和产物连成同一段工作脉络。" />}
    </Panel></div>
  </div>
}
