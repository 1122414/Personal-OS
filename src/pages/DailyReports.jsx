import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel } from '../ui.jsx'
import Markdown from '../Markdown.jsx'

export default function DailyReports({ data, focus, refresh, navigate }) {
  const index = data.daily_reports || { reports: [], dates: [], errors: [] }
  const [day, setDay] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [article, setArticle] = useState(null)
  const [error, setError] = useState('')
  const [refreshError, setRefreshError] = useState('')
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [revision, setRevision] = useState(0)
  const focused = index.reports.find(item => item.id === focus)
  useEffect(() => { if (focused) { setDay(focused.date); setSelectedId(focused.id) } }, [focused?.id])
  const selectedDay = day || index.latest_date
  const reports = index.reports.filter(item => item.date === selectedDay)
  const modules = index.modules || []
  const selected = reports.find(item => item.id === selectedId) || reports[0]
  useEffect(() => {
    setArticle(null); setError('')
    if (!selected) { setLoading(false); return }
    const controller = new AbortController()
    setLoading(true)
    fetch(`/api/obsidian/report?module=${encodeURIComponent(selected.folder)}&path=${encodeURIComponent(selected.path)}`, { signal: controller.signal })
      .then(async response => { const value = await response.json(); if (!response.ok) throw new Error(value.error); return value })
      .then(value => { if (!controller.signal.aborted) setArticle(value) })
      .catch(error => { if (!controller.signal.aborted) setError(error.message || '正文读取失败') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [selected?.id, selected?.version, data.settings.obsidian_vault, data.settings.daily_reports_folder, data.settings.report_modules, revision])

  async function reload() {
    setRefreshing(true); setRefreshError('')
    try { await refresh(); setRevision(value => value + 1) } catch (error) { setRefreshError(error.message) }
    finally { setRefreshing(false) }
  }

  return <div className="daily-reports-layout">
    <Panel title="AI 日报" className="report-list" action={<Button disabled={refreshing} onClick={reload}>{refreshing ? '读取中…' : '刷新'}</Button>}>
      <p className="muted">直接读取 Obsidian 中的报告正文，按 {modules.map(module => module.name).join(' / ')} 分组</p>
      <label className="field">报告日期<select aria-label="报告日期" value={selectedDay || ''} onChange={event => { setDay(event.target.value); setSelectedId(null) }}><option value="" disabled>选择日期</option>{index.dates.map(date => <option key={date} value={date}>{date}{date === data.today ? ' · 今天' : ''}</option>)}</select></label>
      {index.latest_date && index.latest_date !== data.today && <p className="notice subtle">今天尚未发现报告，最新一期为 {index.latest_date}。</p>}
      {refreshError && <p role="alert" className="notice">{refreshError}</p>}
      {index.errors.map((message, i) => <p role="alert" className="notice" key={i}>{message}</p>)}
      {reports.length > 0 && modules.map(module => {
        const items = reports.filter(item => item.folder === module.folder)
        return <details className="report-group" open key={module.folder}><summary>{module.name}<small>{items.length} 篇</small></summary>
          {items.length ? items.map(item => <button className={`report-option ${selected?.id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => setSelectedId(item.id)}><small>{item.kind} · {item.date}</small><strong>{item.title}</strong><span>{item.filename}</span></button>) : <p className="muted">这天没有{module.name}报告。</p>}
        </details>
      })}
      {!reports.length && <Empty title="此日期还没有报告" detail="WorkBuddy 写入日期目录后会自动出现。" action={<Button onClick={() => navigate('settings')}>查看日报目录设置</Button>} />}
    </Panel>
    <Panel className="report-reader" title={selected ? selected.title : '日报正文'} action={selected && <span className="overline">{selected.date}</span>}>
      {selected && <p className="report-provenance">Obsidian · {selected.folder}/{selected.path} · 只读<br />笔记更新：{new Date(selected.modified_at).toLocaleString()}</p>}
      {loading ? <p role="status">正在读取正文…</p> : error ? <p role="alert" className="notice">{error}</p> : article && article.id === selected?.id ? <Markdown text={article.content} /> : <Empty title="选择一期报告开始阅读" />}
    </Panel>
  </div>
}
