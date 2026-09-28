import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, dateLabel, timeLabel } from '../ui.jsx'

const eventNames = { DailyPlanConfirmed: '确认今日计划', TaskCreated: '创建任务', TaskCompleted: '完成任务', DecisionCreated: '记录决策', AgentRunStarted: '启动 Agent', AgentRunFinished: 'Agent 完成', ArtifactCreated: '生成产物', TaskReviewed: '审核通过', DailyLogConfirmed: '结束今天' }

export default function History({ data, run, open }) {
  const [day, setDay] = useState(data.today)
  const days = [...new Set([day, ...(data.history_dates || [data.today])])].sort().reverse()
  const [history, setHistory] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setHistory(null); setError('')
    fetch(`/api/history?date=${encodeURIComponent(day)}`, { signal: controller.signal }).then(async response => {
      const result = await response.json()
      if (!response.ok) throw new Error(result.error || '历史读取失败')
      setHistory(result)
    }).catch(error => { if (error.name !== 'AbortError') setError(error.message) })
    return () => controller.abort()
  }, [day, data])
  const log = history?.date === day ? history.log : null
  const events = history?.date === day ? history.events.slice().reverse() : []
  const done = events.filter(item => item.type === 'TaskCompleted').length
  const decisions = events.filter(item => item.type === 'DecisionCreated').length
  const runs = events.filter(item => item.type === 'AgentRunStarted').length
  const artifacts = events.filter(item => item.type === 'ArtifactCreated').length
  useEffect(() => { if (!days.includes(day)) setDay(data.today) }, [data.today])

  return <div className="page history-page"><div className="page-toolbar"><strong>{dateLabel(day)} · 工作记录</strong><input aria-label="查看日期" type="date" max={data.today} value={day} onChange={event => { if (event.target.value) setDay(event.target.value) }} /><div className="tabs"><button className="active">日</button><button disabled title="后续版本">周</button><button disabled title="后续版本">月</button><button disabled title="后续版本">年</button></div></div>
    <div className="history-grid"><Panel className="date-rail" title="日期">{days.map(item => <button key={item} className={`date-option ${day === item ? 'selected' : ''}`} onClick={() => setDay(item)}><strong>{dateLabel(item)}</strong><small>{item === data.today ? '今天' : ''}</small></button>)}</Panel>
      <Panel className="log-panel" title="每日工作记录" action={log && <span className={`status ${log.confirmed_at ? 'status-Done' : 'status-Review'}`}>{log.confirmed_at ? '已确认' : '待确认'}</span>}>
        <div className="log-stats"><span><strong>{done}</strong>已完成任务</span><span><strong>{runs}</strong>Agent Run</span><span><strong>{decisions}</strong>决策</span><span><strong>{artifacts}</strong>产物</span></div>
        {error ? <p role="alert">{error}</p> : !history ? <p>正在读取当日记录…</p> : log ? <>{log.stale && <p className="notice">有新增事件尚未纳入{log.confirmed_at ? "，这份记录已封存，请对照时间线核对。" : "，请刷新草稿或核对修改后再确认。"}</p>}<div className="log-text">{log.summary}</div><details><summary>旧稿（{log.revisions?.length || 0}）</summary>{log.revisions?.map((item, index) => <pre className="knowledge-preview" key={index}>{item.summary}</pre>)}</details><div className="detail-actions wrap">{!log.confirmed_at && <>{data.runtime?.codex_available && <Button onClick={() => run('summarize_log', { id: log.id })}>AI 整理</Button>}<Button onClick={() => run('draft_log', { date: day, regenerate: true })}>按事件更新（保留旧稿）</Button><Button onClick={() => open('log-edit', log)}>修改日报</Button><Button variant="primary" disabled={log.stale} onClick={() => run('confirm_log', { id: log.id })}>结束今天</Button></>}</div></> : <Empty title={day === data.today ? '今天的日报尚未生成' : '这天没有日报'} detail="日报根据真实任务与事件整理，生成后可以修改。" action={<Button variant="primary" onClick={() => run('draft_log', { date: day })}>生成所选日期日报</Button>} />}
      </Panel><Panel className="timeline-panel" title="当日时间线" action={<small>共 {events.length} 条记录</small>}>
        {events.length ? <div className="timeline">{events.map(item => <div className="timeline-item" key={item.id}><time>{timeLabel(item.created_at)}</time><span className="timeline-dot" /><div><strong>{eventNames[item.type] || item.type}</strong><small>{item.details.title || item.details.name || ''}</small></div></div>)}</div> : <Empty title="这天没有记录" />}
      </Panel></div>
  </div>
}
