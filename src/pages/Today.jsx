import React, { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Panel, STATUS, dateLabel } from '../ui.jsx'

export default function Today({ data, run, open, navigate }) {
  const plan = data.daily_plans.find(item => item.date === data.today)
  const log = data.daily_logs.find(item => item.date === data.today)
  const suggestions = data.brief || []
  const [ordered, setOrdered] = useState([])
  useEffect(() => { if (!plan) setOrdered(suggestions.map(item => item.task_id)) }, [data.today, plan?.id, suggestions.map(item => item.task_id).join(',')])
  const tasks = useMemo(() => ordered.map(id => data.tasks.find(task => task.id === id)).filter(Boolean), [ordered, data.tasks])
  const todayTasks = data.tasks.filter(task => task.planned_date === data.today)
  const done = todayTasks.filter(task => task.status === 'Done').length
  const running = data.agent_runs.filter(run => run.status === 'Running')
  const waiting = data.tasks.filter(task => task.status === 'Review')
  const hour = new Date().getHours()
  const mode = !plan ? 'plan' : hour >= 20 || hour < 6 ? 'review' : 'work'
  const latestProject = data.projects.find(project => project.status === 'Active')
  const topIntel = data.intelligence_items.filter(item => item.feedback !== 'ignore').slice(0, 2)

  function shift(index, delta) {
    const next = [...ordered]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    setOrdered(next)
  }

  return <div className="page today-page">
    <div className="page-intro"><span>{dateLabel(data.today)}</span><span>{mode === 'plan' ? '规划今天' : mode === 'review' ? '回顾今天' : '专注执行'}</span></div>
    {!plan ? <Panel className="brief-panel feature-panel" title="今日简报" action={<span className="overline">MORNING BRIEF</span>}>
      <div className="brief-lead"><h2>今天最值得推进的事</h2><p>从未完成任务、截止日期与项目上下文整理。请调整后确认。</p></div>
      {tasks.length ? <div className="priority-list">{tasks.map((task, index) => {
        const suggestion = suggestions.find(item => item.task_id === task.id)
        return <div className="priority-item" key={task.id}>
          <span className="priority-number">0{index + 1}</span>
          <div><strong>{task.title}</strong><p>{suggestion?.reason || '由你加入今日计划'}</p></div>
          <div className="row-actions"><button onClick={() => shift(index, -1)} title="上移" disabled={index === 0}>↑</button><button onClick={() => shift(index, 1)} title="下移" disabled={index === tasks.length - 1}>↓</button><button onClick={() => setOrdered(ordered.filter(id => id !== task.id))} title="移除">×</button></div>
        </div>
      })}</div> : <Empty title="今天的计划由你开始" detail="创建任务后，它会进入这里供你确认。" />}
      <div className="brief-actions"><Button onClick={() => open('task')}>＋ 添加任务</Button>{data.runtime?.codex_available && tasks.length > 0 && <Button onClick={() => run('generate_brief', {})}>生成 AI 建议</Button>}<Button variant="primary" onClick={() => run('confirm_plan', { task_ids: ordered })}>确认今日计划</Button></div>
    </Panel> : <Panel className="work-panel feature-panel" title={mode === 'review' ? '今日回顾' : '今日任务'} action={<span className="overline">{done} / {todayTasks.length} 已完成</span>}>
      <div className="progress-track"><span style={{ width: `${todayTasks.length ? done / todayTasks.length * 100 : 0}%` }} /></div>
      <div className="work-list">{todayTasks.length ? todayTasks.map(task => <div className="work-row" key={task.id}>
        <span className={`task-ring ${task.status === 'Done' ? 'checked' : ''}`}>{task.status === 'Done' ? '✓' : ''}</span>
        <div><strong>{task.title}</strong><small>{data.projects.find(project => project.id === task.project_id)?.name || '无项目'} · {STATUS[task.status]}</small></div>
        {task.executor_type === 'self' && task.status !== 'Done' ? <Button onClick={() => run('complete_task', { id: task.id })}>完成</Button> : <Button onClick={() => navigate('tasks', task.id)}>查看</Button>}
      </div>) : <Empty title="计划已确认" detail="继续添加任务并在任务页安排今天。" action={<Button onClick={() => open('task')}>添加任务</Button>} />}</div>
      <div className="brief-actions"><Button onClick={() => navigate('tasks')}>查看全部任务 →</Button><Button variant="primary" onClick={() => log ? navigate('history') : run('draft_log', {})}> {log ? '查看今日日报' : '生成今日日报'}</Button></div>
    </Panel>}
    <div className="today-grid">
      <Panel title="今日任务" action={<button className="text-link" onClick={() => navigate('tasks')}>查看全部 →</button>}>
        {(plan ? todayTasks : data.tasks.filter(task => task.status !== 'Done').slice(0, 4)).length ? (plan ? todayTasks : data.tasks.filter(task => task.status !== 'Done').slice(0, 4)).map(task => <button key={task.id} className="mini-row" onClick={() => navigate('tasks', task.id)}><span className="task-ring" /><span>{task.title}</span><small>{STATUS[task.status]}</small></button>) : <Empty title="暂无任务" />}
      </Panel>
      <Panel title="项目脉搏" action={<button className="text-link" onClick={() => navigate('projects')}>全部项目 →</button>}>
        {latestProject ? <div className="pulse"><strong>{latestProject.name}</strong><p>{latestProject.pulse || latestProject.stage || '等待项目进展'}</p><small>当前阶段 · {latestProject.stage}</small></div> : <Empty title="尚无项目" detail="建立项目，今天的任务便有了上下文。" action={<Button onClick={() => open('project')}>创建项目</Button>} />}
      </Panel>
      <Panel title="情报精选" action={<button className="text-link" onClick={() => navigate('intelligence')}>查看情报 →</button>}>
        {topIntel.length ? topIntel.map(item => <button className="mini-row" key={item.id} onClick={() => navigate('intelligence', item.id)}><span className="small-symbol">✧</span><span>{item.title}</span></button>) : <Empty title="暂无情报" detail="在情报页设定频道和来源。" />}
      </Panel>
      <Panel title="等待审核" action={<button className="text-link" onClick={() => navigate('review')}>进入审核 →</button>}>
        {waiting.length ? waiting.slice(0, 3).map(task => <button className="mini-row" key={task.id} onClick={() => navigate('review', task.id)}><span className="small-symbol">◉</span><span>{task.title}</span><small>待确认</small></button>) : <Empty title="没有待审核事项" />}
      </Panel>
    </div>
    {(running.length > 0 || log) && <Panel title="今日节奏" className="rhythm-panel"><div className="rhythm-content">{running.length > 0 && <span>{running.length} 个 Agent 正在执行</span>}{log && <span>日报 · {log.confirmed_at ? '已确认' : '待确认'}</span>}<Button onClick={() => navigate(log ? 'history' : 'review')}>查看 →</Button></div></Panel>}
  </div>
}
