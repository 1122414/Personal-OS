import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, dateLabel, timeLabel } from '../ui.jsx'

const eventNames = { DailyPlanConfirmed: '确认今日计划', TaskCreated: '创建任务', TaskCompleted: '完成任务', DecisionCreated: '记录决策', AgentRunStarted: '启动 Agent', AgentRunFinished: 'Agent 完成', ArtifactCreated: '生成产物', TaskReviewed: '审核通过', DailyLogConfirmed: '结束今天' }

export default function History({ data, run, open }) {
  const [day, setDay] = useState(data.today)
  const days = [...new Set([data.today, ...data.daily_logs.map(item => item.date), ...data.events.map(item => item.created_at.slice(0, 10))])].sort().reverse()
  const log = data.daily_logs.find(item => item.date === day)
  const events = data.events.filter(item => item.created_at.slice(0, 10) === day).slice().reverse()
  const done = events.filter(item => item.type === 'TaskCompleted').length
  const decisions = events.filter(item => item.type === 'DecisionCreated').length
  const runs = events.filter(item => item.type === 'AgentRunStarted').length
  const artifacts = events.filter(item => item.type === 'ArtifactCreated').length
  useEffect(() => { if (!days.includes(day)) setDay(data.today) }, [data.today])

  return <div className="page history-page"><div className="page-toolbar"><strong>{dateLabel(day)} · 工作记录</strong><div className="tabs"><button className="active">日</button><button disabled title="后续版本">周</button><button disabled title="后续版本">月</button><button disabled title="后续版本">年</button></div></div>
    <div className="history-grid"><Panel className="date-rail" title="日期">{days.map(item => <button key={item} className={`date-option ${day === item ? 'selected' : ''}`} onClick={() => setDay(item)}><strong>{dateLabel(item)}</strong><small>{item === data.today ? '今天' : ''}</small></button>)}</Panel>
      <Panel className="log-panel" title="每日工作记录" action={log && <span className={`status ${log.confirmed_at ? 'status-Done' : 'status-Review'}`}>{log.confirmed_at ? '已确认' : '待确认'}</span>}>
        <div className="log-stats"><span><strong>{done}</strong>已完成任务</span><span><strong>{runs}</strong>Agent Run</span><span><strong>{decisions}</strong>决策</span><span><strong>{artifacts}</strong>产物</span></div>
        {log ? <><div className="log-text">{log.summary}</div><div className="detail-actions">{!log.confirmed_at && <>{data.runtime?.codex_available && <Button onClick={() => run('summarize_log', { id: log.id })}>AI 整理</Button>}<Button onClick={() => open('log-edit', log)}>修改日报</Button><Button variant="primary" onClick={() => run('confirm_log', { id: log.id })}>结束今天</Button></>}</div></> : <Empty title={day === data.today ? '今天的日报尚未生成' : '这天没有日报'} detail="日报根据真实任务与事件整理，生成后可以修改。" action={day === data.today && <Button variant="primary" onClick={() => run('draft_log', {})}>生成今日日报</Button>} />}
      </Panel><Panel className="timeline-panel" title="当日时间线" action={<small>共 {events.length} 条记录</small>}>
        {events.length ? <div className="timeline">{events.map(item => <div className="timeline-item" key={item.id}><time>{timeLabel(item.created_at)}</time><span className="timeline-dot" /><div><strong>{eventNames[item.type] || item.type}</strong><small>{item.details.title || item.details.name || ''}</small></div></div>)}</div> : <Empty title="这天没有记录" />}
      </Panel></div>
  </div>
}
