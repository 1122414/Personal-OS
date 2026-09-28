import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, dateLabel } from '../ui.jsx'

export default function Review({ data, run, open, focus }) {
  const [tab, setTab] = useState('all')
  const [selectedId, select] = useState(focus || null)
  useEffect(() => { if (focus) select(focus) }, [focus])
  const tasks = data.tasks.filter(task => task.status === 'Review').map(task => ({ id: task.id, kind: 'task', title: task.title, subtitle: 'Agent 结果 · 待确认', created_at: task.updated_at, raw: task }))
  const knowledge = data.knowledge_proposals.filter(item => item.status === 'Review').map(item => ({ id: item.id, kind: 'knowledge', title: item.title, subtitle: '知识写入 · 待确认', created_at: item.created_at, raw: item }))
  const queue = [...tasks, ...knowledge].filter(item => tab === 'all' || item.kind === tab)
  const selected = queue.find(item => item.id === selectedId) || queue[0]
  const task = selected?.kind === 'task' ? selected.raw : data.tasks.find(item => item.id === selected?.raw.task_id)
  const runs = data.agent_runs.filter(item => item.task_id === task?.id)
  const artifacts = data.artifacts.filter(item => item.task_id === task?.id)

  return <div className="page review-page"><div className="split-layout review-split"><Panel className="review-queue" title="审核队列" action={<span className="overline">{tasks.length + knowledge.length} 项待处理</span>}>
    <div className="tabs compact">{[['all', '全部'], ['task', 'Agent 结果'], ['knowledge', '知识写入']].map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div>
    {queue.length ? queue.map(item => <button key={item.id} className={`review-row ${selected?.id === item.id ? 'selected' : ''}`} onClick={() => select(item.id)}><span className="review-icon">{item.kind === 'task' ? '✓' : '▤'}</span><span><strong>{item.title}</strong><small>{item.subtitle}</small><small>{dateLabel(item.created_at)}</small></span></button>) : <Empty title="所有需要决定的事都处理好了" />}
  </Panel><Panel className="review-detail">
    {selected ? <><div className="detail-title"><div><span className="overline">{selected.kind === 'task' ? 'AGENT RESULT' : 'KNOWLEDGE REVIEW'}</span><h2>{selected.title}</h2><p>{selected.subtitle}</p></div><span className="status status-Review">待审核</span></div>
      {selected.kind === 'task' ? <><div className="meta-grid"><div><small>所属任务</small><strong>{task.title}</strong></div><div><small>所属项目</small><strong>{data.projects.find(item => item.id === task.project_id)?.name || '无项目'}</strong></div><div><small>执行方式</small><strong>{task.agent_id || 'Agent'}</strong></div><div><small>当前状态</small><strong>结果返回 · 待你确认</strong></div></div>
        <div className="detail-section"><h3>结果</h3><p>{task.result || runs[0]?.result || 'Agent 尚未提交可阅读的结果。'}</p></div><div className="detail-section"><h3>执行证据与产物</h3>{artifacts.length ? artifacts.map(item => <div className="artifact-row" key={item.id}>{item.name} · {{ Created: '新建', Modified: '修改', Deleted: '删除' }[item.change] || '变更'} · {item.status === 'Review' ? '待审核' : '已确认'}</div>) : <p className="muted">未检测到文件变更；请检查结果内容。</p>}</div>
        <div className="detail-actions"><Button variant="primary" onClick={() => run('review_agent', { task_id: task.id, choice: 'approve' })}>确认完成</Button><Button onClick={() => open('agent-revision', task)}>继续修改</Button><Button onClick={() => run('review_agent', { task_id: task.id, choice: 'rerun' })}>重新执行</Button></div>
      </> : <><div className="detail-section"><h3>{task ? '关联任务' : '来源资料'}</h3><p>{task?.title || selected.raw.source_title || '外部资料'}</p></div><div className="detail-section"><h3>拟写入内容</h3><pre className="knowledge-preview">{selected.raw.content}</pre></div><p className="notice subtle">知识库写入是单独决定。批准后才会创建文件。</p><div className="detail-actions wrap"><Button variant="primary" onClick={() => run('approve_knowledge', { id: selected.id, choice: 'write' })}>写入 Obsidian</Button><Button onClick={() => open('knowledge-edit', selected.raw)}>修改后写入</Button><Button onClick={() => run('approve_knowledge', { id: selected.id, choice: 'keep' })}>{task ? '仅保留任务' : '仅保留资料'}</Button><Button onClick={() => run('approve_knowledge', { id: selected.id, choice: 'discard' })}>不保存</Button></div></>}
    </> : <Empty title="选择待审核事项" detail="Agent 完成不等于任务完成，最终决定由你作出。" />}
  </Panel></div></div>
}
