import React, { useEffect, useRef, useState } from 'react'
import Markdown from './Markdown.jsx'
import { Button, Empty, Field, Modal, dateLabel, timeLabel } from './ui.jsx'
import { ExportNote } from './workspace.jsx'
import { RelatedRecords } from './PersonalState.jsx'

export const SECTION_TITLES = { brief: '接续摘要', goal: '当前目标', understanding: '关键理解', questions: '尚未解决', next: '下一步', related: '相关内容' }
const SUMMARY_STATES = { ready: '已整理', updating: '正在后台更新', stale: '有新内容待整理', pending: '等待恢复整理', failed: '更新失败' }

function Source({ source, detail, data, topicId }) {
  const message = source.kind === 'message' && detail.messages.find(item => item.id === source.id)
  const title = message ? `${message.role === 'user' ? '我' : 'Codex'} · ${dateLabel(message.created_at)} ${timeLabel(message.created_at)}` : source.title
  const material = source.kind === 'material' && data.materials.find(item => item.id === source.id)
  const exists = source.kind === 'message' ? detail.messages.some(item => item.id === source.id) : source.kind === 'record' ? data.records.some(item => item.id === source.id) : source.kind === 'material' ? !!material : true
  const href = source.kind === 'message' ? `#learning/${topicId}/${source.id}` : source.kind === 'record' ? `#records/${source.id}` : source.kind === 'material' ? source.url || `/api/material/${source.id}${source.page ? `#page=${source.page}` : ''}` : `#learning/${topicId}`
  return <details className="summary-source"><summary>{title}{source.page ? ` · 第 ${source.page} 页` : ''}</summary><small>来源版本 {source.revision}{source.partial ? ' · 仅纳入部分原文' : ''}</small>{exists ? <a href={href} target={source.kind === 'material' ? '_blank' : undefined} rel="noreferrer">打开原文{source.page ? ` · 第 ${source.page} 页` : ''} ↗</a> : <p className="inline-error">原始对象已不在当前数据中，以下为整理时快照。</p>}<Markdown text={source.text || '主题目标尚未填写。'} /></details>
}

function SectionEditor({ topicId, sectionKey, section, run, reload, close }) {
  const [body, setBody] = useState(section?.body || '')
  const [owner, setOwner] = useState(section?.owner || 'ai_suggestion')
  const [status, setStatus] = useState('已保存')
  const [error, setError] = useState('')
  const [pulse, setPulse] = useState(0)
  const draft = useRef({ body, owner })
  draft.current = { body, owner }
  const saved = useRef({ body: section?.body || '', owner: section?.owner || 'ai_suggestion' })
  const revision = useRef(section?.revision || 0)
  const busy = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const dirty = () => draft.current.body !== saved.current.body || draft.current.owner !== saved.current.owner
  async function save() {
    if (busy.current || !dirty()) return !dirty()
    busy.current = true; setStatus('正在保存…')
    const snapshot = { ...draft.current }
    try {
      const result = await run('edit_summary_section', { id: topicId, key: sectionKey, expected_revision: revision.current, ...snapshot }, { quiet: true })
      revision.current = result.revision
      saved.current = snapshot
      if (mounted.current) { setStatus('已自动保存 · 后续 AI 更新会保留你的修改'); setError(''); reload() }
      return !dirty()
    } catch (failure) { if (mounted.current) { setError(failure.message); setStatus('未保存，输入仍在这里') }; return false }
    finally { busy.current = false; if (mounted.current) setPulse(value => value + 1) }
  }
  useEffect(() => {
    if (!dirty() || error) return
    setStatus('等待自动保存…')
    const timer = setTimeout(save, 800)
    return () => clearTimeout(timer)
  }, [body, owner, pulse, error])
  async function safeClose() { if (!busy.current && (!dirty() || await save())) close() }
  return <Modal title={`编辑 · ${SECTION_TITLES[sectionKey]}`} onClose={safeClose}><Field label="Markdown 正文"><textarea rows={14} value={body} maxLength={20000} autoFocus onChange={event => setBody(event.target.value)} /></Field>{sectionKey === 'next' && <Field label="下一步的归属"><select value={owner} onChange={event => setOwner(event.target.value)}><option value="ai_suggestion">AI 建议</option><option value="user_plan">我的计划</option></select></Field>}<p className="muted" role="status">{status}</p>{error && <div className="inline-error" role="alert"><p>{error}</p><details><summary>核对服务器当前版本</summary><Markdown text={section?.body || '当前部分为空'} /></details><Button onClick={() => { revision.current = section?.revision || 0; setError(''); setPulse(value => value + 1) }}>基于当前版本保存我的输入</Button></div>}<div className="modal-actions"><Button onClick={() => { setBody(saved.current.body); setOwner(saved.current.owner); setError('') }}>撤回未保存输入</Button><Button variant="primary" onClick={safeClose}>完成</Button></div></Modal>
}

function SummaryHistory({ summary, topicId, run, reload, close }) {
  const [versionId, setVersionId] = useState(summary.versions[0]?.id || '')
  const version = summary.versions.find(item => item.id === versionId)
  return <Modal title="总结历史版本" onClose={close}><Field label="历史版本"><select value={versionId} onChange={event => setVersionId(event.target.value)}>{summary.versions.map(item => <option key={item.id} value={item.id}>{dateLabel(item.created_at)} {timeLabel(item.created_at)} · {item.reason}</option>)}</select></Field>{version ? Object.entries(version.sections).filter(([, section]) => section.body).map(([key, section]) => <section className="history-section" key={key}><h3>{SECTION_TITLES[key]}</h3><Markdown text={section.body} /><Button onClick={async () => { if (await run('restore_summary_section', { id: topicId, version_id: version.id, key, expected_revision: summary.report?.sections[key]?.revision || 0 })) reload() }}>恢复这一部分</Button></section>) : <Empty title="还没有更早的版本" detail="自动更新、人工编辑和采纳候选前，都会保留版本。" />}</Modal>
}

export default function LearningSummary({ topic, detail, data, run, reload, setTab }) {
  const summary = detail.summary
  const report = summary.report
  const [editing, setEditing] = useState(null)
  const [history, setHistory] = useState(false)
  const sources = [...new Map(Object.values(report?.sections || {}).flatMap(section => section.sources || []).map(source => [source.ref, source])).values()]
  const canGenerate = detail.messages.some(message => message.role === 'assistant' && message.status === 'Completed')
  async function refresh() { if (await run('refresh_learning_summary', { id: topic.id })) reload() }
  return <div className="summary-layout"><article className="summary-reader"><div className="summary-toolbar"><small>{SUMMARY_STATES[summary.state]}{report?.cutoff ? ` · 来源截至 ${dateLabel(report.cutoff)} ${timeLabel(report.cutoff)}` : ''}</small><Button disabled={!canGenerate || summary.state === 'updating'} onClick={refresh}>{summary.state === 'failed' ? '重试整理' : '更新总结'}</Button></div>
    {summary.error && <p className="inline-error" role="status">{summary.error}；原始对话和旧总结均保留。</p>}
    {summary.state === 'updating' && <p className="muted">更新期间仍可阅读和编辑。生成时新来的消息，会标为待整理。</p>}
    {!report?.generated_at && !Object.values(report?.sections || {}).some(section => section.body) ? <Empty title="聊过之后，把理解留下来" detail="完整回复后静默 2 分钟自动整理，也可以立即更新。" action={<Button onClick={() => setTab('chat')}>继续对话 →</Button>} /> : <>
      {report?.coverage && (report.coverage.omitted_messages > 0 || report.coverage.partial_sources > 0) && <p className="notice subtle">本次纳入 {report.coverage.message_count} 条消息；{report.coverage.omitted_messages} 条较早消息未纳入，{report.coverage.partial_sources} 份来源只纳入部分文字。原文仍可查看。</p>}
      {Object.entries(SECTION_TITLES).map(([key, title]) => {
        const section = report?.sections[key]
        if (!section?.body && key !== editing) return null
        return <section className={`summary-section summary-${key}`} key={key}><div className="summary-section-heading"><h3>{title}{key === 'next' ? ` · ${section?.owner === 'user_plan' ? '我的计划' : 'AI 建议'}` : ''}</h3><div>{section?.manual && <small>人工修订 · 已保护</small>}<button className="text-link" onClick={() => setEditing(key)}>编辑</button></div></div><Markdown text={section?.body || ''} />{section?.sources?.length > 0 && <details className="section-citations"><summary>{section.sources.length} 条来源</summary>{section.sources.map(source => <Source key={source.ref} source={source} detail={detail} data={data} topicId={topic.id} />)}</details>}{key === 'understanding' && <p className="notice subtle">ⓘ {summary.evidence}</p>}{key === 'next' && section?.body && <Button variant="primary" onClick={() => setTab('chat')}>接着讨论这一步 →</Button>}</section>
      })}
      <details className="summary-add-section"><summary>补充或修改其他部分</summary><div className="workspace-actions">{Object.entries(SECTION_TITLES).map(([key, title]) => <Button key={key} onClick={() => setEditing(key)}>{title}</Button>)}</div></details>
    </>}
    {summary.candidates.length > 0 && <section className="summary-candidates"><h3>候选变化 · 你的修改已保留</h3>{summary.candidates.map(candidate => <details key={candidate.id}><summary>{SECTION_TITLES[candidate.key]} · 来源截至 {timeLabel(candidate.cutoff)}</summary><div className="candidate-compare"><div><small>当前内容</small><Markdown text={report?.sections[candidate.key]?.body || '（为空）'} /></div><div><small>AI 候选</small><Markdown text={candidate.generated.body || '（建议留空）'} />{candidate.generated.sources.map(source => <Source key={source.ref} source={source} detail={detail} data={data} topicId={topic.id} />)}</div></div><div className="workspace-actions"><Button onClick={async () => { if (await run('resolve_summary_candidate', { id: candidate.id, choice: 'keep' })) reload() }}>保留我的版本</Button><Button onClick={async () => { if (await run('resolve_summary_candidate', { id: candidate.id, choice: 'accept', expected_revision: report?.sections[candidate.key]?.revision || 0 })) reload() }}>采纳候选</Button></div></details>)}</section>}
  </article><aside className="summary-sidebar"><section><h3>来源</h3>{sources.length ? sources.map(source => <Source key={source.ref} source={source} detail={detail} data={data} topicId={topic.id} />) : <p className="muted">整理后可以定位到原话、资料与页码。</p>}</section><section><h3>关联记录</h3>{topic.record_ids.map(id => data.records.find(record => record.id === id)).filter(Boolean).map(record => <a className="related-record" key={record.id} href={`#records/${record.id}`}>{record.title}<small>你已关联到这个主题 · 查看原文 →</small></a>)}</section><RelatedRecords detail={detail} data={data} run={run} reload={reload} topicId={topic.id} /><div className="summary-footer"><small>总结由 Codex 整理 · 可修改<br />Personal OS 保存主版本</small><Button onClick={() => setHistory(true)}>历史版本</Button>{report && <ExportNote kind="learning_topic" id={topic.id} run={run} />}</div></aside>
    {editing && <SectionEditor key={editing} topicId={topic.id} sectionKey={editing} section={report?.sections[editing]} run={run} reload={reload} close={() => setEditing(null)} />}
    {history && <SummaryHistory summary={summary} topicId={topic.id} run={run} reload={reload} close={() => setHistory(false)} />}
  </div>
}
