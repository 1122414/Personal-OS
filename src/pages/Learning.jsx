import React, { useEffect, useRef, useState } from 'react'
import { loadLearning, recentObsidian } from '../api.js'
import Markdown from '../Markdown.jsx'
import LearningSummary from '../LearningSummary.jsx'
import { Button, Empty, Panel, dateLabel, timeLabel } from '../ui.jsx'
import { Capture, ExportNote, Materials, TopicForm, materialUrl, recordDate } from '../workspace.jsx'

const RUN_LABELS = { Running: '正在回复', Completed: '回复完成', Cancelled: '已取消', Interrupted: '已中断', Failed: '回复失败' }

export function MessageSources({ sources = [] }) {
  if (!sources.length) return null
  return <details className="message-sources"><summary>本次上下文 · {sources.length} 份原文或资料</summary>{sources.map(source => <article key={source.id}>
    <a href={source.kind === 'record' ? `#records/${source.id}` : source.url || `/api/material/${source.id}`} target={source.kind === 'material' ? '_blank' : undefined} rel="noreferrer">{source.title} ↗</a><small>版本 {source.revision} · {source.note}</small>
    {source.text && <details><summary>发送时的原文</summary><Markdown text={source.text} /></details>}
    {source.pages?.map((page, index) => <details key={index}><summary>{page.page ? `第 ${page.page} 页` : '网页文字'} · 发送时快照</summary>{page.page && <a href={`/api/material/${source.id}#page=${page.page}`} target="_blank" rel="noreferrer">打开原文件这一页 ↗</a>}<Markdown text={page.text} /></details>)}
    {source.format === 'image' && <small>提供的是原图；理解程度以本次回答为准。</small>}
  </article>)}</details>
}

function Conversation({ topic, detail, run, reload }) {
  const [text, setText] = useState('')
  const [selected, setSelected] = useState([])
  const [sending, setSending] = useState(false)
  const requestId = useRef(null)
  const end = useRef(null)
  const composer = useRef(null)
  const [follow, setFollow] = useState(true)
  const active = detail.runs.find(item => item.status === 'Running')
  const latest = detail.runs[0]
  const failed = latest && !['Completed', 'Running'].includes(latest.status)
  useEffect(() => { if (follow) end.current?.scrollIntoView({ block: 'nearest' }) }, [detail.messages.map(message => message.content.length).join(','), follow])
  useEffect(() => {
    const jump = () => {
      const messageId = window.location.hash.split('/')[2]
      if (messageId && messageId !== 'chat') { setFollow(false); document.getElementById(`message-${messageId}`)?.scrollIntoView({ block: 'center' }) }
    }
    jump()
    window.addEventListener('hashchange', jump)
    return () => window.removeEventListener('hashchange', jump)
  }, [detail.messages.length])

  async function send(value = text) {
    if (!value.trim() || sending || active) return
    setSending(true)
    requestId.current ||= crypto.randomUUID()
    const result = await run('send_learning_message', { id: topic.id, text: value, material_ids: selected, request_id: requestId.current })
    setSending(false)
    if (result) { setText(''); setSelected([]); requestId.current = null; setFollow(true); await reload() }
  }

  return <div className="conversation"><div className="messages" onScroll={event => { const el = event.currentTarget; setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 100) }}>
    {!detail.messages.length && <Empty title="从一个问题开始" detail={topic.mode === 'guided' ? '说说你已经知道什么，或先让 Codex 带你迈出一小步。' : '直接问你此刻想弄清楚的事。'} />}
    {detail.messages.map(message => <article className={`learning-message ${message.role}`} key={message.id} id={`message-${message.id}`}><div className="message-meta"><strong>{message.role === 'user' ? '我' : 'Codex'}</strong><span>{dateLabel(message.created_at)} {timeLabel(message.created_at)}</span>{message.role === 'assistant' && <span>{RUN_LABELS[message.status]}</span>}<button className="text-link" onClick={async () => { if (await run('mark_learning_message', { id: message.id, important: !message.important })) reload() }}>{message.important ? '★ 已标重点' : '☆ 标重点'}</button></div>
      {message.content ? <Markdown text={message.content} /> : <p className="muted">{message.status === 'Running' ? message.progress === 'thinking' ? 'Codex 正在思考，问题已保存…' : '正在连接 Codex，问题已保存…' : '没有收到正文。原始问题已保留。'}</p>}
      {message.error && <p className="inline-error" role="status">{message.error}</p>}
      {message.role === 'user' && <MessageSources sources={message.sources} />}
      {message.role === 'user' && <label className="learning-evidence">理解证据<select aria-label="理解证据" value={message.learning_signal || 'none'} onChange={async event => { if (await run('set_learning_evidence', { id: message.id, signal: event.target.value })) reload() }}><option value="none">未标记</option><option value="understood">我表示理解了</option><option value="exercise_verified">这条练习我已核对</option></select></label>}
    </article>)}<div ref={end} />
  </div>
  {failed && <div className="learning-retry"><span>{RUN_LABELS[latest.status]} · 可以重试最近的问题</span><Button onClick={async () => { if (await run('retry_learning', { id: latest.user_message_id })) reload() }}>重试</Button><Button title="原生会话无法恢复时，用 POS 保存的对话重建" onClick={async () => { if (await run('retry_learning', { id: latest.user_message_id, reset_session: true })) reload() }}>重建会话后重试</Button></div>}
  <form className="chat-composer" onSubmit={event => { event.preventDefault(); send() }}>
    {detail.materials.length > 0 && <details className="choose-materials"><summary>本轮使用资料{selected.length ? ` · 已选 ${selected.length}` : ''}</summary>{detail.materials.map(material => {
      const ready = material.kind === 'image' || ['parsed', 'partial'].includes(material.read_status)
      return <label key={material.id}><input type="checkbox" disabled={!ready || !!active} checked={selected.includes(material.id)} onChange={event => setSelected(current => event.target.checked ? [...current, material.id] : current.filter(id => id !== material.id))} /><span>{material.name}<small>{ready ? material.kind === 'image' ? '将发送原图，能力不支持时会显示失败' : material.read_note : '尚不能使用，请先到资料页解析'}</small></span></label>
    })}</details>}
    <textarea ref={composer} aria-label="学习消息" value={text} maxLength={30000} onChange={event => { setText(event.target.value); requestId.current = null }} placeholder={active ? '可以先写下一个问题，当前回复结束后发送…' : '继续上次的问题，或换一个方向…'} rows={3} onKeyDown={event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') { event.preventDefault(); send() } }} />
    <div className="chat-composer-actions"><span className="muted">Codex · {topic.mode === 'guided' ? '带着学' : '随问随答'} · ⌘ Enter 发送</span><div className="workspace-actions">{topic.mode === 'guided' && !active && detail.messages.length > 0 && <Button type="button" onClick={() => { setText('先跳过这个练习，换一个例子解释。'); composer.current?.focus() }}>跳过 / 换方向</Button>}{active ? <Button type="button" onClick={async () => { if (await run('cancel_learning', { id: active.id })) reload() }}>停止回复</Button> : <Button variant="primary" disabled={sending || !text.trim()}>{sending ? '保存中…' : '发送'}</Button>}</div></div>
  </form></div>
}

function TopicMaterials({ topic, data, detail, run, navigate, reload }) {
  const [adding, setAdding] = useState(false)
  const [recordId, setRecordId] = useState('')
  const [obsidian, setObsidian] = useState(null)
  const [obsidianError, setObsidianError] = useState('')
  const records = data.records.filter(record => topic.record_ids.includes(record.id))
  return <div className="topic-materials"><div className="workspace-actions"><Button onClick={() => setAdding(!adding)}>＋ 添加记录或资料</Button><select aria-label="选择记录加入主题" value={recordId} onChange={event => setRecordId(event.target.value)}><option value="">关联已有记录…</option>{data.records.filter(record => !topic.record_ids.includes(record.id)).map(record => <option key={record.id} value={record.id}>{record.title}</option>)}</select><Button disabled={!recordId} onClick={async () => { if (await run('link_record', { id: topic.id, record_id: recordId })) { setRecordId(''); reload() } }}>关联</Button></div>
    <div className="workspace-actions obsidian-import"><Button onClick={async () => { try { setObsidian(await recentObsidian()); setObsidianError('') } catch (error) { setObsidianError(error.message) } }}>引用 Obsidian 笔记</Button>{obsidian && <select aria-label="选择 Obsidian 笔记" value="" onChange={async event => { if (event.target.value && await run('import_obsidian_record', { id: topic.id, path: event.target.value })) reload() }}><option value="">{obsidian.configured ? '选择最近修改的笔记…' : '请先在设置中配置仓库'}</option>{obsidian.files.map(file => <option key={file.path} value={file.path}>{file.path}</option>)}</select>}{obsidianError && <span className="inline-error">{obsidianError}</span>}{obsidian && <small className="muted">只读入所选笔记的快照，不修改原文件。</small>}</div>
    {adding && <Capture run={run} onSaved={async record => { await run('link_record', { id: topic.id, record_id: record.id }); setAdding(false); reload() }} />}
    {!records.length && <Empty title="保存的资料，由你选择何时使用" detail="添加图片、PDF 或链接；文字解析和发送给 Agent 都有单独操作。" />}
    {records.map(record => <section className="topic-record" key={record.id}><div className="detail-title"><a href={`#records/${record.id}`}>{record.title} → 原文</a><Button onClick={async () => { await run('link_record', { id: topic.id, record_id: record.id, remove: true }); reload() }}>取消关联</Button></div><Markdown text={record.content} />
      <Materials items={detail.materials.filter(material => material.record_id === record.id)} />
      {detail.materials.filter(material => material.record_id === record.id && material.kind !== 'image').map(material => <div className="material-action" key={material.id}><span>{material.name}</span><Button disabled={material.read_status === 'parsing'} onClick={async () => { await run('parse_material', { id: material.id }); reload() }}>{material.read_status === 'parsing' ? '正在解析…' : material.parsed_at ? '重新读取' : '提取文字'}</Button>{material.extracted_pages?.some(Boolean) && <span className="page-links">{material.extracted_pages.filter(Boolean).map(page => <a key={page} href={`${materialUrl(material)}#page=${page}`} target="_blank" rel="noreferrer">第 {page} 页</a>)}</span>}</div>)}
    </section>)}<ExportNote kind="learning_topic" id={topic.id} run={run} />
  </div>
}

function TopicWorkspace({ topic, data, run, navigate }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState(() => window.location.hash.split('/')[2] ? 'chat' : 'summary')
  const [editing, setEditing] = useState(false)
  const mounted = useRef(true)
  async function reload() {
    try { const result = await loadLearning(topic.id); if (mounted.current) { setDetail(result); setError('') }; return result }
    catch (failure) { if (mounted.current) setError(failure.message) }
  }
  useEffect(() => {
    mounted.current = true
    let timer
    async function tick() { const next = await reload(); if (mounted.current) timer = setTimeout(tick, next?.runs.some(run => run.status === 'Running') || next?.materials.some(item => item.read_status === 'parsing') || next?.summary.state === 'updating' ? 700 : 5000) }
    tick()
    const navigateMessage = () => { if (window.location.hash.split('/')[2]) setTab('chat') }
    window.addEventListener('hashchange', navigateMessage)
    return () => { mounted.current = false; clearTimeout(timer); window.removeEventListener('hashchange', navigateMessage) }
  }, [topic.id])
  const current = detail?.topic?.updated_at > topic.updated_at ? detail.topic : topic
  return <div className="topic-workspace panel"><div className="topic-heading"><div><button className="text-link" onClick={() => navigate('learning')}>学习 / 全部主题</button><h2>{current.title}</h2><p>{current.goal || '从问题出发，逐步明确想弄清楚的事。'}</p></div><div className="workspace-actions"><select aria-label="学习 Agent" value="codex" onChange={() => {}}><option value="codex">Codex</option></select><select aria-label="学习模式" value={current.mode} onChange={async event => { await run('update_learning_topic', { id: current.id, expected_updated_at: current.updated_at, mode: event.target.value }); reload() }}><option value="guided">带着学</option><option value="quick">随问随答</option></select><Button onClick={() => setEditing(true)}>修改目标</Button></div></div>
    <div className="tabs topic-tabs"><button className={tab === 'summary' ? 'active' : ''} onClick={() => setTab('summary')}>总结</button><button className={tab === 'chat' ? 'active' : ''} onClick={() => setTab('chat')}>对话</button><button className={tab === 'materials' ? 'active' : ''} onClick={() => setTab('materials')}>资料</button></div>
    {error && <p className="inline-error" role="alert">{error}<Button onClick={reload}>重新读取</Button></p>}
    {!detail ? <Empty title="正在读取对话…" /> : tab === 'summary' ? <LearningSummary topic={current} detail={detail} data={data} run={run} reload={reload} setTab={setTab} /> : tab === 'chat' ? <Conversation topic={current} detail={detail} run={run} reload={reload} /> : <TopicMaterials topic={current} detail={detail} data={data} run={run} navigate={navigate} reload={reload} />}
    {editing && <TopicForm topic={current} run={run} close={() => setEditing(false)} onSaved={reload} />}
  </div>
}

export default function Learning({ data, run, focus, navigate }) {
  const [creating, setCreating] = useState(false)
  const topic = data.learning_topics.find(item => item.id === focus)
  return <div className="page learning-page">{topic ? <TopicWorkspace key={topic.id} topic={topic} data={data} run={run} navigate={navigate} /> : <><div className="page-toolbar"><span>随时回来，接着上次继续。</span><Button variant="primary" onClick={() => setCreating(true)}>＋ 新主题</Button></div><Panel className="topic-list">{data.learning_topics.length ? data.learning_topics.map(item => <button className="topic-card" key={item.id} onClick={() => navigate('learning', item.id)}><span className="topic-symbol">▤</span><div><h2>{item.title}</h2><p>{item.goal || '从上次的想法继续探索。'}</p><small>Codex · {item.mode === 'guided' ? '带着学' : '随问随答'} · {recordDate(item)}</small></div><span>继续学习 →</span></button>) : <Empty title="想学习什么，就从这里开始" detail="临时问题可以随问随答，持续目标可以带着学。" action={<Button onClick={() => setCreating(true)}>创建第一个主题</Button>} />}</Panel></>}
    {creating && <TopicForm run={run} close={() => setCreating(false)} onSaved={item => navigate('learning', item.id)} />}
  </div>
}
