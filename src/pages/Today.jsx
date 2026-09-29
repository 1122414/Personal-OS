import React, { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Panel, STATUS } from '../ui.jsx'

export default function TodayPlan({ data, run, open, navigate }) {
  const plan = data.daily_plans.find(item => item.date === data.today)
  const log = data.daily_logs.find(item => item.date === data.today)
  const suggestions = data.brief || []
  const [ordered, setOrdered] = useState([])
  const [editing, setEditing] = useState(false)
  const [dirty, setDirty] = useState(false)
  useEffect(() => { if (!plan && !dirty) setOrdered(suggestions.map(item => item.task_id)) }, [data.today, plan?.id, suggestions.map(item => item.task_id).join(',')])
  const tasks = useMemo(() => ordered.map(id => data.tasks.find(task => task.id === id)).filter(Boolean), [ordered, data.tasks])
  const todayTasks = (plan?.task_ids || []).map(id => data.tasks.find(task => task.id === id)).filter(Boolean)
  const done = todayTasks.filter(task => task.status === 'Done').length
  const hour = new Date().getHours()
  const review = plan && (hour >= 20 || hour < 6)

  function shift(index, delta) {
    const next = [...ordered]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    setDirty(true); setOrdered(next)
  }

  if (!plan || editing) return <Panel className="brief-panel today-plan" title="今天" action={<span className="overline">{plan ? '调整计划' : '规划今天'}</span>}>
    <p className="muted">从未完成任务、截止日期与项目上下文整理。请调整后确认。</p>
    {tasks.length ? <div className="priority-list">{tasks.map((task, index) => {
      const suggestion = suggestions.find(item => item.task_id === task.id)
      return <div className="priority-item" key={task.id}>
        <span className="priority-number">0{index + 1}</span>
        <div><strong>{task.title}</strong><p>{suggestion?.reason || '由你加入今日计划'}</p></div>
        <div className="row-actions"><button onClick={() => shift(index, -1)} title="上移" disabled={index === 0}>↑</button><button onClick={() => shift(index, 1)} title="下移" disabled={index === tasks.length - 1}>↓</button><button disabled={!!plan && ['Running', 'Review', 'Done'].includes(task.status)} onClick={() => { setDirty(true); setOrdered(ordered.filter(id => id !== task.id)) }} title="移除">×</button></div>
      </div>
    })}</div> : <Empty title="今天的计划由你开始" detail="创建任务后，它会进入这里供你确认。" />}
    <div className="brief-actions wrap"><select aria-label="选择已有任务" value="" onChange={event => { if (event.target.value) { setDirty(true); setOrdered([...ordered, event.target.value]) } }}><option value="">选择已有任务…</option>{data.tasks.filter(task => !task.archived_at && ['Inbox', 'Planned'].includes(task.status) && !ordered.includes(task.id)).map(task => <option key={task.id} value={task.id}>{task.title}</option>)}</select><Button onClick={() => open('task')}>＋ 添加任务</Button>{!plan && data.runtime?.codex_available && tasks.length > 0 && <Button onClick={async () => { const result = await run('generate_brief', {}); if (result) { setDirty(true); setOrdered(result.priorities.map(item => item.task_id)) } }}>生成 AI 建议</Button>}{editing && <Button onClick={() => setEditing(false)}>取消调整</Button>}<Button variant="primary" onClick={async () => { const result = await run(plan ? 'revise_plan' : 'confirm_plan', { task_ids: ordered }); if (result) { setEditing(false); setDirty(false) } }}>{plan ? '保存计划调整' : '确认今日计划'}</Button></div>
  </Panel>

  return <Panel className="work-panel today-plan" title={review ? '今天 · 回顾' : '今天'} action={<span className="overline">{done} / {todayTasks.length} 已完成</span>}>
    <div className="progress-track"><span style={{ width: `${todayTasks.length ? done / todayTasks.length * 100 : 0}%` }} /></div>
    <div className="work-list">{todayTasks.length ? todayTasks.map(task => <div className="work-row" key={task.id}>
      <span className={`task-ring ${task.status === 'Done' ? 'checked' : ''}`}>{task.status === 'Done' ? '✓' : ''}</span>
      <div><strong>{task.title}</strong><small>{data.projects.find(project => project.id === task.project_id)?.name || '无项目'} · {STATUS[task.status]}</small></div>
      {task.executor_type === 'self' && task.status !== 'Done' ? <Button onClick={() => run('complete_task', { id: task.id })}>完成</Button> : <Button onClick={() => navigate('tasks', task.id)}>查看</Button>}
    </div>) : <Empty title="计划已确认" detail="继续添加任务并在任务页安排今天。" action={<Button onClick={() => open('task')}>添加任务</Button>} />}</div>
    <div className="brief-actions wrap"><Button onClick={() => { setOrdered(plan.task_ids); setDirty(true); setEditing(true) }}>调整计划</Button><Button onClick={() => navigate('tasks')}>全部任务 →</Button><Button variant="primary" onClick={() => log ? navigate('history') : run('draft_log', {})}>{log ? (log.confirmed_at ? '查看今日日报' : '核对并结束今天') : '生成今日日报'}</Button></div>
  </Panel>
}
