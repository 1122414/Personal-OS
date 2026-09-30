import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, dateLabel, timeLabel } from '../ui.jsx'
import Markdown from '../Markdown.jsx'

const eventNames = { DailyPlanConfirmed: '确认今日计划', TaskCreated: '创建任务', TaskCompleted: '完成任务', DecisionCreated: '记录决策', AgentRunStarted: '启动 Agent', AgentRunFinished: 'Agent 完成', ArtifactCreated: '生成产物', TaskReviewed: '审核通过', DailyLogConfirmed: '结束今天', DailyLogDrafted: '生成日报草稿', DailyLogSummarized: 'AI 生成日报', RecordCreated: '保存记录', RecordUpdated: '修改记录', LearningTopicCreated: '建立学习主题', PersonalStateCreated: '记下近期状态', MaterialSaved: '保存资料原件', TraceCommit: '代码提交', TraceSession: 'Agent 会话', HomeItemUpdated: '更新长线事项', ProjectCreated: '登记项目' }

function ReportTools({ data, run, day, log }) {
  const engines = (data.runtime?.agents || []).filter(agent => !agent.remote)
  const [engine, setEngine] = useState(data.settings?.report_engine || engines.find(agent => agent.available)?.id || 'codex')
  const [busy, setBusy] = useState(false)
  const available = engines.find(agent => agent.id === engine)?.available
  async function generate() {
    setBusy(true)
    try { await run('summarize_log', log ? { id: log.id, engine } : { date: day, engine }) } finally { setBusy(false) }
  }
  return <span className="report-tools">
    <select aria-label="日报生成通道" value={engine} onChange={event => setEngine(event.target.value)}>{engines.map(agent => <option key={agent.id} value={agent.id}>{agent.label}{agent.available ? '' : '（本机未找到）'}</option>)}</select>
    <Button variant="primary" disabled={busy || !available} onClick={generate}>{busy ? '生成中…' : log ? '重新生成（保留旧稿）' : '生成日报'}</Button>
  </span>
}

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

  return <div className="page history-page"><div className="page-toolbar"><strong>{dateLabel(day)} · 工作日报</strong><input aria-label="查看日期" type="date" max={data.today} value={day} onChange={event => { if (event.target.value) setDay(event.target.value) }} /><div className="tabs"><button className="active">日</button><button disabled title="后续版本">周</button><button disabled title="后续版本">月</button><button disabled title="后续版本">年</button></div></div>
    <div className="history-grid"><Panel className="date-rail" title="日期">{days.map(item => <button key={item} className={`date-option ${day === item ? 'selected' : ''}`} onClick={() => setDay(item)}><strong>{dateLabel(item)}</strong><small>{item === data.today ? '今天' : ''}</small></button>)}</Panel>
      <Panel className="log-panel" title="工作日报" action={log && <span className={`status ${log.confirmed_at ? 'status-Done' : 'status-Review'}`}>{log.confirmed_at ? '已确认' : '待确认'}</span>}>
        <div className="log-stats"><span><strong>{done}</strong>已完成任务</span><span><strong>{runs}</strong>Agent Run</span><span><strong>{decisions}</strong>决策</span><span><strong>{artifacts}</strong>产物</span></div>
        {error ? <p role="alert">{error}</p> : !history ? <p>正在读取当日记录…</p> : log ? <>
          {log.stale && <p className="notice">有新增事件尚未纳入{log.confirmed_at ? "，这份记录已封存，请对照时间线核对。" : "，可以重新生成，或核对修改后再确认。"}</p>}
          <div className="log-text"><Markdown text={log.summary} /></div>
          {log.engine && <small className="muted">由 {log.engine} 生成</small>}
          <details><summary>旧稿（{log.revisions?.length || 0}）</summary>{log.revisions?.map((item, index) => <pre className="knowledge-preview" key={index}>{item.summary}</pre>)}</details>
          {!log.confirmed_at && <div className="detail-actions wrap"><ReportTools data={data} run={run} day={day} log={log} /><Button onClick={() => run('draft_log', { date: day, regenerate: true })}>不用 AI，按记录重排</Button><Button onClick={() => open('log-edit', log)}>修改日报</Button><Button variant="primary" disabled={log.stale} onClick={() => run('confirm_log', { id: log.id })}>结束今天</Button></div>}
        </> : <Empty title={day === data.today ? '今天的日报尚未生成' : '这天没有日报'} detail="选一个通道，根据当天完成和没完成的待办、Agent 任务、代码提交与会话，写出「今日工作总结」和「明日工作计划」。生成后可以修改。" action={<span className="detail-actions wrap"><ReportTools data={data} run={run} day={day} log={null} /><Button onClick={() => run('draft_log', { date: day })}>不用 AI，按记录生成草稿</Button></span>} />}
      </Panel><Panel className="timeline-panel" title="当日时间线" action={<small>共 {events.length} 条记录</small>}>
        {events.length ? <div className="timeline">{events.map(item => <div className="timeline-item" key={item.id}><time>{timeLabel(item.created_at)}</time><span className="timeline-dot" /><div><strong>{eventNames[item.type] || item.type}</strong><small>{item.details.title || item.details.name || ''}</small></div></div>)}</div> : <Empty title="这天没有记录" />}
      </Panel></div>
  </div>
}
