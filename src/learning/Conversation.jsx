import React, { useEffect, useRef, useState } from 'react'
import Markdown from '../Markdown.jsx'
import { Button, Empty, dateLabel, timeLabel } from '../ui.jsx'

const RUN_LABELS = {
  Running: '正在回复', Completed: '回复完成', Cancelled: '已取消',
  Interrupted: '已中断', Failed: '回复失败',
}

function MessageSources({ sources = [] }) {
  if (!sources.length) return null
  return (
    <details className="message-sources">
      <summary>本次上下文 · {sources.length} 份原文或资料</summary>
      {sources.map(source => (
        <article key={source.id}>
          <a
            href={source.kind === 'record' ? '#records/' + source.id : source.url || '/api/material/' + source.id}
            target={source.kind === 'material' ? '_blank' : undefined}
            rel="noreferrer"
          >
            {source.title} ↗
          </a>
          <small>版本 {source.revision} · {source.note}</small>
          {source.text && <details><summary>发送时的原文</summary><Markdown text={source.text} /></details>}
          {source.pages?.map((page, index) => (
            <details key={index}>
              <summary>{page.page ? '第 ' + page.page + ' 页' : '网页文字'} · 发送时快照</summary>
              {page.page && (
                <a href={'/api/material/' + source.id + '#page=' + page.page} target="_blank" rel="noreferrer">
                  打开原文件这一页 ↗
                </a>
              )}
              <Markdown text={page.text} />
            </details>
          ))}
          {source.format === 'image' && <small>提供的是原图；理解程度以本次回答为准。</small>}
        </article>
      ))}
    </details>
  )
}

function LearningMessage({ message, run, reload }) {
  async function update(name, payload) {
    if (await run(name, { id: message.id, ...payload })) await reload()
  }
  const pendingText = message.status !== 'Running'
    ? '没有收到正文。原始问题已保留。'
    : message.progress === 'thinking' ? 'Codex 正在思考，问题已保存…' : '正在连接 Codex，问题已保存…'

  return (
    <article className={'learning-message ' + message.role} id={'message-' + message.id}>
      <div className="message-meta">
        <strong>{message.role === 'user' ? '我' : 'Codex'}</strong>
        <span>{dateLabel(message.created_at)} {timeLabel(message.created_at)}</span>
        {message.role === 'assistant' && <span>{RUN_LABELS[message.status]}</span>}
        <button className="text-link" onClick={() => update('mark_learning_message', { important: !message.important })}>
          {message.important ? '★ 已标重点' : '☆ 标重点'}
        </button>
      </div>
      {message.content ? <Markdown text={message.content} /> : <p className="muted">{pendingText}</p>}
      {message.error && <p className="inline-error" role="status">{message.error}</p>}
      {message.role === 'user' && <MessageSources sources={message.sources} />}
      {message.state_context?.states.length > 0 && (
        <details className="message-sources">
          <summary>这次建议参考的近期状态</summary>
          {message.state_context.states.map(state => (
            <article key={state.source_record_id}>
              <p>{state.text}</p>
              <small>当时有效至 {dateLabel(state.expires_at)}</small>
              <a href={'#records/' + state.source_record_id}>状态原话 ↗</a>
            </article>
          ))}
        </details>
      )}
      {message.role === 'user' && (
        <label className="learning-evidence">
          理解证据
          <select
            aria-label="理解证据"
            value={message.learning_signal || 'none'}
            onChange={event => update('set_learning_evidence', { signal: event.target.value })}
          >
            <option value="none">未标记</option>
            <option value="understood">我表示理解了</option>
            <option value="exercise_verified">这条练习我已核对</option>
          </select>
        </label>
      )}
    </article>
  )
}

export default function Conversation({ topic, detail, run, reload, draft }) {
  const end = useRef(null)
  const composer = useRef(null)
  const [follow, setFollow] = useState(true)
  const active = detail.runs.find(item => item.status === 'Running')
  const latest = detail.runs[0]
  const failed = latest && !['Completed', 'Running'].includes(latest.status)
  const messageLengths = detail.messages.map(message => message.content.length).join(',')

  useEffect(() => {
    if (follow) end.current?.scrollIntoView({ block: 'nearest' })
  }, [messageLengths, follow])

  useEffect(() => {
    function jump() {
      const messageId = window.location.hash.split('/')[2]
      if (messageId && messageId !== 'chat') {
        setFollow(false)
        document.getElementById('message-' + messageId)?.scrollIntoView({ block: 'center' })
      }
    }
    jump()
    window.addEventListener('hashchange', jump)
    return () => window.removeEventListener('hashchange', jump)
  }, [detail.messages.length])

  async function send() {
    if (!active && await draft.send()) setFollow(true)
  }

  async function retry(resetSession = false) {
    if (await run('retry_learning', { id: latest.user_message_id, reset_session: resetSession })) await reload()
  }

  return (
    <div className="conversation">
      <div className="messages" onScroll={event => {
        const element = event.currentTarget
        setFollow(element.scrollHeight - element.scrollTop - element.clientHeight < 100)
      }}>
        {!detail.messages.length && (
          <Empty
            title="从一个问题开始"
            detail={topic.mode === 'guided' ? '说说你已经知道什么，或先让 Codex 带你迈出一小步。' : '直接问你此刻想弄清楚的事。'}
          />
        )}
        {detail.messages.map(message => <LearningMessage key={message.id} message={message} run={run} reload={reload} />)}
        <div ref={end} />
      </div>
      {failed && (
        <div className="learning-retry">
          <span>{RUN_LABELS[latest.status]} · 可以重试最近的问题</span>
          <Button onClick={() => retry()}>重试</Button>
          <Button title="原生会话无法恢复时，用 POS 保存的对话重建" onClick={() => retry(true)}>重建会话后重试</Button>
        </div>
      )}
      <form className="chat-composer" onSubmit={event => { event.preventDefault(); send() }}>
        {detail.materials.length > 0 && (
          <details className="choose-materials">
            <summary>本轮使用资料{draft.materialIds.length ? ' · 已选 ' + draft.materialIds.length : ''}</summary>
            {detail.materials.map(material => {
              const ready = material.kind === 'image' || ['parsed', 'partial'].includes(material.read_status)
              const note = !ready ? '尚不能使用，请先到资料页解析'
                : material.kind === 'image' ? '将发送原图，能力不支持时会显示失败' : material.read_note
              return (
                <label key={material.id}>
                  <input
                    type="checkbox"
                    disabled={!ready || !!active}
                    checked={draft.materialIds.includes(material.id)}
                    onChange={event => draft.selectMaterial(material.id, event.target.checked)}
                  />
                  <span>{material.name}<small>{note}</small></span>
                </label>
              )
            })}
          </details>
        )}
        <textarea
          ref={composer}
          aria-label="学习消息"
          value={draft.text}
          maxLength={30000}
          onChange={event => draft.setText(event.target.value)}
          placeholder={active ? '可以先写下一个问题，当前回复结束后发送…' : '继续上次的问题，或换一个方向…'}
          rows={3}
          onKeyDown={event => {
            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
              event.preventDefault()
              send()
            }
          }}
        />
        <div className="chat-composer-actions">
          <span className="muted">Codex · {topic.mode === 'guided' ? '带着学' : '随问随答'} · ⌘ Enter 发送</span>
          <div className="workspace-actions">
            {topic.mode === 'guided' && !active && detail.messages.length > 0 && (
              <Button type="button" onClick={() => {
                draft.setText('先跳过这个练习，换一个例子解释。')
                composer.current?.focus()
              }}>跳过 / 换方向</Button>
            )}
            {active ? (
              <Button type="button" onClick={async () => {
                if (await run('cancel_learning', { id: active.id })) await reload()
              }}>停止回复</Button>
            ) : (
              <Button variant="primary" disabled={draft.sending || !draft.text.trim()}>
                {draft.sending ? '保存中…' : '发送'}
              </Button>
            )}
          </div>
        </div>
      </form>
    </div>
  )
}
