import React, { useState } from 'react'
import { Button, Empty, Panel } from '../ui.jsx'
import { ExportNote, Materials, TopicForm, recordDate } from '../workspace.jsx'

export default function Learning({ data, run, focus, navigate }) {
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(false)
  const topic = data.learning_topics.find(item => item.id === focus)
  const records = topic ? data.records.filter(record => topic.record_ids.includes(record.id)) : []
  return <div className="page learning-page"><div className="page-toolbar"><div className="workspace-actions">{topic && <Button onClick={() => navigate('learning')}>← 全部主题</Button>}<span>{topic ? `${topic.mode === 'guided' ? '带着学' : '随问随答'} · Codex` : '随时回来，接着上次继续。'}</span></div><Button variant="primary" onClick={() => setCreating(true)}>＋ 新主题</Button></div>
    {topic ? <Panel className="workspace-reader topic-overview"><div className="detail-title"><div><h2>{topic.title}</h2><p>{topic.goal || '还没有明确目标，可以从一个问题开始。'}</p></div><Button onClick={() => setEditing(true)}>修改主题</Button></div><h3>关联记录与资料</h3>{records.length ? records.map(record => <div className="topic-record" key={record.id}><button className="text-link" onClick={() => navigate('records', record.id)}>{record.title} → 原文</button><p>{record.content}</p><Materials items={data.materials.filter(item => item.record_id === record.id)} /><Button onClick={() => run('link_record', { id: topic.id, record_id: record.id, remove: true })}>取消关联</Button></div>) : <Empty title="主题已保存" detail="在记录页选择这个主题，可以把已有想法和资料带过来。" action={<Button onClick={() => navigate('records')}>查看记录</Button>} />}<ExportNote kind="learning_topic" id={topic.id} run={run} /></Panel> : <Panel className="topic-list">{data.learning_topics.length ? data.learning_topics.map(item => <button className="topic-card" key={item.id} onClick={() => navigate('learning', item.id)}><span className="topic-symbol">▤</span><div><h2>{item.title}</h2><p>{item.goal || '从上次的想法继续探索。'}</p><small>Codex · {item.mode === 'guided' ? '带着学' : '随问随答'} · {recordDate(item)}</small></div><span>查看主题 →</span></button>) : <Empty title="想学习什么，就从这里开始" detail="临时问题可以随问随答，持续目标可以带着学。" action={<Button onClick={() => setCreating(true)}>创建第一个主题</Button>} />}</Panel>}
    {(creating || editing) && <TopicForm topic={editing ? topic : null} run={run} close={() => { setCreating(false); setEditing(false) }} onSaved={item => navigate('learning', item.id)} />}
  </div>
}
