import React, { useRef, useState } from 'react'
import { Button, Field, Modal, dateLabel, timeLabel } from './ui.jsx'

export const RECORD_TYPES = { note: '笔记', idea: '点子', resource: '资料', status: '状态原话' }
export const materialUrl = material => material.url || `/api/material/${material.id}`
export const recordDate = item => `${dateLabel(item.created_at)} ${timeLabel(item.created_at)}`

export async function filePayload(file) {
  if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name} 超过 20 MB`)
  const base64 = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error(`无法读取 ${file.name}`))
    reader.onload = () => resolve(reader.result.split(',')[1])
    reader.readAsDataURL(file)
  })
  return { name: file.name, base64 }
}

export function Capture({ run, onSaved, recordId = null, compact = false }) {
  const [content, setContent] = useState('')
  const [url, setUrl] = useState('')
  const [files, setFiles] = useState([])
  const [attachments, setAttachments] = useState(!!recordId)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [savedRecord, setSavedRecord] = useState(null)
  const picker = useRef(null)

  async function save(event) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      let record = recordId ? { id: recordId } : savedRecord
      if (!record) {
        record = await run('create_record', { content, title: content.trim() ? '' : files[0]?.name || url, record_type: files.length || url ? 'resource' : 'note' })
        if (!record) return
        setSavedRecord(record)
      }
      if (url) {
        if (!await run('add_material', { record_id: record.id, url })) { setError('原文已保存，链接未保存。请修正后重试。'); return }
        setUrl('')
      }
      for (const file of files) {
        const payload = await filePayload(file)
        if (!await run('add_material', { record_id: record.id, ...payload })) { setError('原文已保存，仍有附件未保存。请重试。'); return }
        setFiles(current => current.filter(item => item !== file))
      }
      setContent(''); setSavedRecord(null); setAttachments(!!recordId)
      if (picker.current) picker.current.value = ''
      onSaved?.(record)
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }

  return <form className={`capture ${compact ? 'compact' : ''}`} onSubmit={save}>
    {!recordId && <textarea aria-label="随手记内容" placeholder="此刻，有什么想记下来？" rows={compact ? 2 : 3} maxLength={100000} value={content} disabled={busy || !!savedRecord} onChange={event => setContent(event.target.value)} />}
    {attachments && <div className="capture-attachments"><Field label="网页或视频链接（可选）"><input type="url" value={url} disabled={busy} onChange={event => setUrl(event.target.value)} placeholder="https://" /></Field><input ref={picker} type="file" multiple accept="image/png,image/jpeg,image/gif,image/webp,application/pdf" aria-label="选择图片或 PDF" disabled={busy} onChange={event => setFiles(current => [...current, ...Array.from(event.target.files)])} /><small>图片 / PDF，每个最多 20 MB。保存后再选择是否解读。</small>{files.map((file, i) => <div className="attachment-name" key={`${file.name}-${i}`}>{file.name}<button type="button" disabled={busy} onClick={() => setFiles(current => current.filter((_, n) => n !== i))} aria-label={`移除 ${file.name}`}>×</button></div>)}</div>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    <div className="capture-actions">{!recordId && <Button type="button" onClick={() => setAttachments(!attachments)} disabled={busy}>＋ 添加资料</Button>}<Button type="submit" variant="primary" disabled={busy || (!content.trim() && !url && !files.length && !savedRecord)}>{busy ? '正在保存…' : recordId ? '保存资料' : savedRecord ? '重试保存附件' : '保存记录'}</Button></div>
  </form>
}

export function Materials({ items }) {
  return <div className="materials-list">{items.map(item => <article key={item.id} className="material-row" id={`material-${item.id}`}>
    {item.kind === 'image' && <a href={materialUrl(item)} target="_blank" rel="noreferrer"><img src={materialUrl(item)} alt={item.name} loading="lazy" /></a>}
    <div><a href={materialUrl(item)} target="_blank" rel="noreferrer">{item.name} ↗</a><small>{item.read_note}</small>{item.used_in?.length > 0 && <small>曾用于 {item.used_in.length} 次对话；具体范围见消息来源</small>}</div>
  </article>)}</div>
}

export function TopicForm({ run, close, onSaved, record, topic }) {
  const [busy, setBusy] = useState(false)
  const [version] = useState(topic?.updated_at)
  async function submit(event) {
    event.preventDefault(); setBusy(true)
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    const result = await run(topic ? 'update_learning_topic' : 'create_learning_topic', { ...fields, record_id: record?.id, ...(topic ? { id: topic.id, expected_updated_at: version } : {}) })
    setBusy(false)
    if (result) { close(); onSaved?.(result) }
  }
  return <Modal title={topic ? '修改学习主题' : '开始一个主题'} onClose={close}><form onSubmit={submit}>
    <Field label="主题"><input name="title" defaultValue={topic?.title || record?.title || ''} maxLength={200} required autoFocus /></Field>
    <Field label="想弄清楚什么（可选）"><textarea name="goal" rows={3} maxLength={3000} defaultValue={topic?.goal || ''} /></Field>
    <Field label="学习方式"><select name="mode" defaultValue={topic?.mode || 'guided'}><option value="guided">带着学 · 小段解释、提问或练习</option><option value="quick">随问随答 · 自己掌握节奏</option></select></Field>
    <p className="muted">创建主题会保留关联原文；发送消息后才开始对话。</p>
    <div className="modal-actions"><Button type="button" onClick={close}>取消</Button><Button variant="primary" disabled={busy}>{busy ? '保存中…' : '保存主题'}</Button></div>
  </form></Modal>
}

export function ExportNote({ kind, id, run }) {
  const [result, setResult] = useState(null)
  return <div className="export-note"><div className="workspace-actions"><Button onClick={async () => setResult(await run('export_workspace_note', { kind, id }))}>导出 Markdown</Button><Button onClick={async () => setResult(await run('export_workspace_note', { kind, id, destination: 'obsidian' }))}>导出至 Obsidian</Button></div>{result && <p className="muted" role="status">已保存：<span className="export-path">{result.path}</span></p>}</div>
}
