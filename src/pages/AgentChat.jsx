import React, { useEffect, useRef, useState } from 'react'
import Markdown from '../Markdown.jsx'
import { Button, runDuration, timeLabel } from '../ui.jsx'

export const RUN_STATUS = { Running: '运行中', Finished: '已回复', Failed: '失败', Canceled: '已取消', Interrupted: '已中断' }
const CHANGE = { Created: '新建', Modified: '修改', Deleted: '删除' }

export function mergeChanges(artifacts) {
  const merged = new Map()
  for (const item of [...artifacts].sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''))) {
    const earlier = merged.get(item.name)
    const change = earlier === undefined ? item.change
      : earlier === 'Created' ? (item.change === 'Deleted' ? null : 'Created')
      : earlier === null ? (item.change === 'Deleted' ? null : 'Created')
      : earlier === 'Deleted' ? (item.change === 'Created' ? 'Modified' : 'Deleted')
      : item.change === 'Deleted' ? 'Deleted' : 'Modified'
    merged.set(item.name, change)
  }
  return [...merged].filter(([, change]) => change).map(([name, change]) => ({ name, change }))
}

function Transcript({ entries }) {
  const blocks = []
  for (const entry of entries) {
    const last = blocks.at(-1)
    if (entry.type === 'tool' && last?.type === 'tools') last.items.push(entry.text)
    else blocks.push(entry.type === 'tool' ? { type: 'tools', items: [entry.text] } : entry)
  }
  return blocks.map((block, index) => block.type === 'tools'
    ? <details className="chat-steps" key={index}><summary>执行了 {block.items.length} 步</summary><ul>{block.items.map((text, i) => <li key={i}>{text}</li>)}</ul></details>
    : <Markdown key={index} text={block.text} />)
}

function AgentTurn({ run }) {
  const running = run.status === 'Running'
  const entries = run.transcript || []
  return <article className="chat-turn agent">
    <div className="chat-meta"><strong>{run.agent_id}</strong><span className={`run-status run-${run.status}`}>{RUN_STATUS[run.status] || run.status}</span>{run.resumed && <span className="chat-tag">接着原会话</span>}{run.resume_failed && <span className="chat-tag">原会话无法续接，已开新会话</span>}<span className="chat-time">{timeLabel(run.started_at)} · {runDuration(run)}</span></div>
    {running ? <p className="muted">正在执行，回复后可以接着说。</p> : entries.length ? <Transcript entries={entries} /> : run.result ? <Markdown text={run.result} /> : !run.error && <p className="muted">没有回复。</p>}
    {!running && run.error && <p className="notice chat-error">{run.error}</p>}
    {run.outside_writes?.length > 0 && <p className="notice">尝试写入工作目录以外：{run.outside_writes.join('、')}</p>}
    {run.log_tail?.length > 0 && <details open={running}><summary>执行日志 · 最近 {run.log_tail.length} 行</summary><pre className="run-log">{run.log_tail.join('\n')}</pre></details>}
  </article>
}

function UserTurn({ label, text }) {
  return <article className="chat-turn user"><div className="chat-meta"><strong>我</strong>{label && <span>{label}</span>}</div><p className="pre-wrap">{text}</p></article>
}

export function Conversation({ task, runs, agents }) {
  const ordered = [...runs].reverse()
  const meta = agents.find(agent => agent.id === (runs[0]?.runtime || task.runtime))
  const end = useRef(null)
  const seen = useRef(null)
  const progress = `${task.id}:${runs.length}:${runs[0]?.status}`
  useEffect(() => {
    if (seen.current?.startsWith(`${task.id}:`) && seen.current !== progress) end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    seen.current = progress
  }, [progress, task.id])
  return <div className="chat">
    <UserTurn label="任务要求" text={task.description || task.title} />
    {ordered.map(run => <React.Fragment key={run.id}>{run.message && <UserTurn text={run.message} />}<AgentTurn run={run} /></React.Fragment>)}
    {runs.length > 0 && <p className="chat-note">{meta?.remote ? '在 Multica 的执行环境中运行，只有它改动本机工作目录时才会记录改动。' : meta?.sandboxed ? `${meta.label} 在系统沙箱中运行，只能写入工作目录和临时目录。` : '直接修改工作目录。'}验收不撤销已有改动，失败或取消后也请核对。</p>}
    <div ref={end} />
  </div>
}

export function Composer({ task, runs, run }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const running = task.status === 'Running'
  async function send() {
    const value = text.trim()
    if (!value || sending) return
    setSending(true)
    const result = await run('send_agent_message', { task_id: task.id, text: value })
    setSending(false)
    if (result) setText('')
  }
  function finish() {
    if (window.confirm('结束这段对话并验收？累计改动会标为已确认。')) run('review_agent', { task_id: task.id, choice: 'approve' })
  }
  return <div className="agent-composer">
    <textarea aria-label="接着说" rows={2} maxLength={4000} value={text} disabled={running || sending}
      placeholder={running ? 'Agent 正在执行，回复后再接着说…' : '接着说，Enter 发送，Shift+Enter 换行'}
      onChange={event => setText(event.target.value)}
      onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send() } }} />
    <div className="chat-actions">{running
      ? runs[0] && <Button onClick={() => run('cancel_agent', { id: runs[0].id })}>取消执行</Button>
      : <><Button onClick={finish}>结束并验收</Button><Button variant="primary" disabled={!text.trim() || sending} onClick={send}>{sending ? '发送中…' : '发送'}</Button></>}</div>
  </div>
}

export function Changes({ artifacts }) {
  const changes = mergeChanges(artifacts)
  if (!changes.length) return null
  return <details className="detail-section chat-changes"><summary>累计改动 · {changes.length} 个文件</summary>{changes.map(item => <div className="artifact-row" key={item.name}>{item.name} · {CHANGE[item.change] || '变更'}</div>)}</details>
}
