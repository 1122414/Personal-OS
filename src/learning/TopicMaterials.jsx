import React, { useState } from 'react'
import { recentObsidian } from '../api.js'
import Markdown from '../Markdown.jsx'
import { Button, Empty } from '../ui.jsx'
import { Capture, ExportNote, Materials, materialUrl } from '../workspace.jsx'

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
  const records = data.records.filter(record => topic.record_ids.includes(record.id))
  const availableRecords = data.records.filter(record => !topic.record_ids.includes(record.id))

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
      {adding && (
        <Capture run={run} onSaved={async record => {
          if (await linkRecord(record.id)) setAdding(false)
        }} />
      )}
      {!records.length && (
        <Empty title="保存的资料，由你选择何时使用" detail="添加图片、PDF 或链接；文字解析和发送给 Agent 都有单独操作。" />
      )}
      {records.map(record => {
        const materials = detail.materials.filter(material => material.record_id === record.id)
        return (
          <section className="topic-record" key={record.id}>
            <div className="detail-title">
              <a href={'#records/' + record.id}>{record.title} → 原文</a>
              <Button onClick={() => linkRecord(record.id, true)}>取消关联</Button>
            </div>
            <Markdown text={record.content} />
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
