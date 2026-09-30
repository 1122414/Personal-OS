import React, { useState } from 'react'
import Markdown from '../Markdown.jsx'
import { StateForm } from '../PersonalState.jsx'
import { Button, Empty, Field, Modal, Panel } from '../ui.jsx'
import { Capture, ExportNote, Materials, RECORD_TYPES, TopicForm, recordDate } from '../workspace.jsx'

function RecordEditor({ item, run, close }) {
  const [busy, setBusy] = useState(false)
  const [version] = useState(item.updated_at)
  return <Modal title="编辑记录" onClose={close}><form onSubmit={async event => {
    event.preventDefault(); setBusy(true)
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    const result = await run('update_record', { id: item.id, expected_updated_at: version, ...fields })
    setBusy(false); if (result) close()
  }}>
    <Field label="标题"><input name="title" defaultValue={item.title} maxLength={200} autoFocus /></Field>
    <Field label="原文"><textarea name="content" defaultValue={item.content} rows={12} maxLength={100000} /></Field>
    <Field label="类型"><select name="record_type" defaultValue={item.record_type}>{Object.entries(RECORD_TYPES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field>
    <details className="record-preferences"><summary>回顾偏好（可选）</summary><Field label="这个点子涉及"><select name="idea_scope" defaultValue={item.idea_scope || 'unknown'}><option value="unknown">还没想好</option><option value="existing">正在做或学习的事</option><option value="new_project">需要开启新项目</option></select></Field><Field label="主动找回"><select name="recall_policy" defaultValue={item.recall_policy || 'normal'}><option value="normal">有相关线索时推荐</option><option value="never">不再主动推荐</option></select></Field></details>
    <div className="modal-actions"><Button type="button" onClick={close}>取消</Button><Button variant="primary" disabled={busy}>保存修改</Button></div>
  </form></Modal>
}

function RecordDetail({ item, data, run, navigate, open }) {
  const [editing, setEditing] = useState(false)
  const [newTopic, setNewTopic] = useState(false)
  const [adding, setAdding] = useState(false)
  const [link, setLink] = useState('')
  const [stateForm, setStateForm] = useState(false)
  const materials = data.materials.filter(material => material.record_id === item.id)
  const topics = data.learning_topics.filter(topic => topic.record_ids.includes(item.id))
  async function remove() {
    const attached = materials.length ? `和它的 ${materials.length} 份资料` : ''
    if (!window.confirm(`删除「${item.title}」${attached}？删除后无法恢复；由它转成的待办和 Agent 任务会保留。`)) return
    if (await run('delete_record', { id: item.id })) navigate('records')
  }
  return <><div className="detail-title"><div><small className="muted">{RECORD_TYPES[item.record_type]} · {recordDate(item)}</small><h2>{item.title}</h2></div><div className="workspace-actions"><Button onClick={() => setEditing(true)}>编辑</Button><Button variant="danger" onClick={remove}>删除</Button></div></div>
    <Markdown text={item.content} />
    {item.source?.kind === 'obsidian' && <p className="muted">来自 Obsidian：{item.source.path} · 保存时快照，原文件不会同步修改。</p>}
    {item.original_content !== item.content && <details className="original-record"><summary>最初记下的原文</summary><Markdown text={item.original_content} /></details>}
    <Materials items={materials} />
    <div className="workspace-actions"><Button variant="primary" onClick={() => setNewTopic(true)}>开始讨论</Button><Button onClick={() => setAdding(!adding)}>添加资料</Button><Button onClick={async () => { const todo = item.todo_id ? { id: item.todo_id } : await run('record_to_todo', { id: item.id }); if (todo) navigate('todos', todo.id) }}>{item.todo_id ? '查看关联待办' : '转为待办'}</Button>{item.task_id ? <Button onClick={() => navigate('tasks', item.task_id)}>查看关联 Agent 任务</Button> : <Button onClick={() => open('task', { title: item.title, description: item.content, record_id: item.id })}>转为 Agent 任务</Button>}</div>
    {adding && <Capture recordId={item.id} run={run} onSaved={() => setAdding(false)} />}
    <section className="detail-section"><h3>关联主题</h3>{topics.map(topic => <button key={topic.id} className="mini-row" onClick={() => navigate('learning', topic.id)}>{topic.title} →</button>)}<div className="workspace-actions"><select aria-label="关联已有主题" value={link} onChange={event => setLink(event.target.value)}><option value="">选择已有主题…</option>{data.learning_topics.filter(topic => !topic.record_ids.includes(item.id)).map(topic => <option key={topic.id} value={topic.id}>{topic.title}</option>)}</select><Button disabled={!link} onClick={async () => { if (await run('link_record', { id: link, record_id: item.id })) setLink('') }}>关联</Button></div></section>
    <ExportNote kind="record" id={item.id} run={run} />
    {item.content.trim() && item.content.length <= 4000 && <div className="record-state-action"><Button onClick={() => setStateForm(true)}>将这段原话设为近期状态</Button></div>}
    {stateForm && <StateForm record={item} run={run} close={() => setStateForm(false)} />}
    {editing && <RecordEditor item={item} run={run} close={() => setEditing(false)} />}
    {newTopic && <TopicForm record={item} run={run} close={() => setNewTopic(false)} onSaved={topic => navigate('learning', topic.id)} />}
  </>
}

export default function Records({ data, run, focus, navigate, open }) {
  const [query, setQuery] = useState('')
  const [type, setType] = useState('all')
  const [topicId, setTopicId] = useState('')
  const [creating, setCreating] = useState(false)
  const topic = data.learning_topics.find(item => item.id === topicId)
  const items = data.records.filter(item => item.origin !== 'topic' && (type === 'all' || item.record_type === type) && (!topic || topic.record_ids.includes(item.id)) && `${item.title}\n${item.content}`.toLowerCase().includes(query.toLowerCase()))
  const selected = items.find(item => item.id === focus) || items[0]
  return <div className="page records-page"><div className="page-toolbar workspace-toolbar"><input aria-label="搜索记录" placeholder="搜索原文或标题…" value={query} onChange={event => setQuery(event.target.value)} /><select aria-label="记录类型" value={type} onChange={event => setType(event.target.value)}><option value="all">所有类型</option>{Object.entries(RECORD_TYPES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><select aria-label="按主题筛选" value={topicId} onChange={event => setTopicId(event.target.value)}><option value="">所有主题</option>{data.learning_topics.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select><Button variant="primary" onClick={() => setCreating(true)}>＋ 随手记</Button></div>
    <div className="workspace-split"><Panel className="workspace-list">{items.length ? items.map(item => <button key={item.id} className={`record-option ${selected?.id === item.id ? 'selected' : ''}`} onClick={() => navigate('records', item.id)}><small>{RECORD_TYPES[item.record_type]} · {recordDate(item)}</small><strong>{item.title}</strong><p>{item.content}</p></button>) : <Empty title={query || type !== 'all' || topicId ? '没有匹配记录' : '把此刻的想法记下来'} detail="点子、学习心得、资料和状态都可以留在这里。" />}</Panel><Panel className="workspace-reader">{selected ? <RecordDetail open={open} key={selected.id} item={selected} data={data} run={run} navigate={navigate} /> : <Empty title="记录可以从一句话开始" detail="不用分类，也不必变成任务。" />}</Panel></div>
    {creating && <Modal title="随手记" onClose={() => setCreating(false)}><Capture run={run} onSaved={item => { setCreating(false); navigate('records', item.id) }} /></Modal>}
  </div>
}
