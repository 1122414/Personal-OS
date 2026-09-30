import React, { useRef, useState } from 'react'
import { recentObsidian } from '../api.js'
import Markdown from '../Markdown.jsx'
import { Button, Empty } from '../ui.jsx'
import { Capture, ExportNote, Materials, filePayload, materialUrl } from '../workspace.jsx'

function MaterialAction({ material, run, reload }) {
  async function parse() {
    if (await run('parse_material', { id: material.id })) await reload()
  }
  return (
    <div className="material-action">
      <span>{material.name}</span>
      <Button disabled={material.read_status === 'parsing'} onClick={parse}>
        {material.read_status === 'parsing' ? '正在解析…' : material.parsed_at ? '重新读取' : '提取文字'}
      </Button>
      {material.extracted_pages?.some(Boolean) && (
        <span className="page-links">
          {material.extracted_pages.filter(Boolean).map(page => (
            <a key={page} href={materialUrl(material) + '#page=' + page} target="_blank" rel="noreferrer">第 {page} 页</a>
          ))}
        </span>
      )}
    </div>
  )
}

export default function TopicMaterials({ topic, data, detail, run, reload }) {
  const [adding, setAdding] = useState(false)
  const [recordId, setRecordId] = useState('')
  const [obsidian, setObsidian] = useState(null)
  const [obsidianError, setObsidianError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const fileInput = useRef(null)
  const records = data.records.filter(record => topic.record_ids.includes(record.id))
  const availableRecords = data.records.filter(record => !topic.record_ids.includes(record.id) && record.origin !== 'topic')
  const excluded = new Set(topic.card_excluded_record_ids || [])

  async function upload(event) {
    const files = [...event.target.files]
    event.target.value = ''
    setUploading(true); setUploadError('')
    try {
      for (const file of files) {
        const name = file.name.toLowerCase()
        let record
        if (name.endsWith('.pdf')) {
          record = await run('create_record', { title: file.name, content: '', record_type: 'resource', origin: 'topic' }, { quiet: true })
          const material = await run('add_material', { record_id: record.id, ...await filePayload(file) }, { quiet: true })
          await run('parse_material', { id: material.id }, { quiet: true })
        } else if (/\.(md|markdown|txt)$/.test(name)) {
          const text = await file.text()
          if (text.length > 100000) throw new Error(`${file.name} 超过 10 万字，请拆分后上传`)
          record = await run('create_record', { title: file.name, content: text, record_type: 'resource', origin: 'topic' }, { quiet: true })
        } else {
          throw new Error(`${file.name}：只支持 md、txt、pdf`)
        }
        await run('link_record', { id: topic.id, record_id: record.id }, { quiet: true })
      }
    } catch (error) {
      setUploadError(error.message)
    }
    setUploading(false)
    await reload()
    setTimeout(reload, 4000)
  }

  async function removeUpload(record) {
    if (!window.confirm(`删除资料「${record.title}」？原件一并删除，无法恢复。`)) return
    if (await run('delete_record', { id: record.id })) await reload()
  }

  function toggleSource(recordId, enabled) {
    setUploadError('')
    run('set_card_source', { id: topic.id, record_id: recordId, enabled }, { quiet: true }).catch(error => setUploadError(error.message))
  }

  async function linkRecord(id, remove = false) {
    if (!await run('link_record', { id: topic.id, record_id: id, remove })) return false
    await reload()
    return true
  }

  async function loadObsidian() {
    try {
      setObsidian(await recentObsidian())
      setObsidianError('')
    } catch (error) {
      setObsidianError(error.message)
    }
  }

  async function importObsidian(path) {
    if (path && await run('import_obsidian_record', { id: topic.id, path })) await reload()
  }

  return (
    <div className="topic-materials">
      <div className="workspace-actions">
        <Button variant="primary" disabled={uploading} onClick={() => fileInput.current.click()}>{uploading ? '正在上传…' : '上传文件（md / txt / pdf）'}</Button>
        <input ref={fileInput} type="file" hidden multiple accept=".md,.markdown,.txt,.pdf,text/markdown,text/plain,application/pdf" onChange={upload} />
        <Button onClick={() => setAdding(!adding)}>＋ 添加记录或资料</Button>
        <select aria-label="选择记录加入主题" value={recordId} onChange={event => setRecordId(event.target.value)}>
          <option value="">关联已有记录…</option>
          {availableRecords.map(record => <option key={record.id} value={record.id}>{record.title}</option>)}
        </select>
        <Button disabled={!recordId} onClick={async () => {
          if (await linkRecord(recordId)) setRecordId('')
        }}>关联</Button>
      </div>
      <div className="workspace-actions obsidian-import">
        <Button onClick={loadObsidian}>引用 Obsidian 笔记</Button>
        {obsidian && (
          <select aria-label="选择 Obsidian 笔记" value="" onChange={event => importObsidian(event.target.value)}>
            <option value="">{obsidian.configured ? '选择最近修改的笔记…' : '请先在设置中配置仓库'}</option>
            {obsidian.files.map(file => <option key={file.path} value={file.path}>{file.path}</option>)}
          </select>
        )}
        {obsidianError && <span className="inline-error">{obsidianError}</span>}
        {obsidian && <small className="muted">只读入所选笔记的快照，不修改原文件。</small>}
      </div>
      {uploadError && <p className="inline-error" role="alert">{uploadError}</p>}
      {adding && (
        <Capture run={run} onSaved={async record => {
          if (await linkRecord(record.id)) setAdding(false)
        }} />
      )}
      {!records.length && (
        <Empty title="上传资料，卡片会优先依据它出题" detail="比如简历、笔记、题库（md / txt / pdf）。关联到主题的资料默认用于生成卡片，可以逐份关掉；对话时仍由你勾选发送。" />
      )}
      {records.map(record => {
        const materials = detail.materials.filter(material => material.record_id === record.id)
        return (
          <section className="topic-record" key={record.id}>
            <div className="detail-title">
              {record.origin === 'topic' ? <strong>{record.title}</strong> : <a href={'#records/' + record.id}>{record.title} → 原文</a>}
              <span className="topic-record-tools">
                <label className="card-source-toggle"><input type="checkbox" checked={!excluded.has(record.id)} onChange={event => toggleSource(record.id, event.target.checked)} />用于卡片</label>
                {record.origin === 'topic' ? <Button onClick={() => removeUpload(record)}>删除</Button> : <Button onClick={() => linkRecord(record.id, true)}>取消关联</Button>}
              </span>
            </div>
            {record.content.length > 600
              ? <details className="topic-record-text"><summary>查看全文（{record.content.length} 字）</summary><Markdown text={record.content} /></details>
              : <Markdown text={record.content} />}
            <Materials items={materials} />
            {materials.filter(material => material.kind !== 'image').map(material => (
              <MaterialAction key={material.id} material={material} run={run} reload={reload} />
            ))}
          </section>
        )
      })}
      <ExportNote kind="learning_topic" id={topic.id} run={run} />
    </div>
  )
}
