import React, { useRef, useState } from 'react'
import Markdown from '../Markdown.jsx'
import { Button, Empty, Field, Modal, Panel } from '../ui.jsx'
import { RATINGS, dueLabel, isNewCard, sourceLabel, todayCards } from './cards.js'

function CardForm({ topic, card, run, close }) {
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault(); setBusy(true)
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    const result = await run(card ? 'update_card' : 'create_card', card ? { id: card.id, ...fields } : { topic_id: topic.id, ...fields })
    setBusy(false); if (result) close()
  }
  return <Modal title={card ? '编辑卡片' : '写一张卡片'} onClose={close}><form onSubmit={submit} className="form-grid">
    <Field label="正面：问题或概念"><textarea name="front" rows={2} maxLength={500} defaultValue={card?.front || ''} required autoFocus /></Field>
    <Field label="背面：解答（可用 Markdown）"><textarea name="back" rows={7} maxLength={4000} defaultValue={card?.back || ''} /></Field>
    <div className="modal-actions"><Button type="button" onClick={close}>取消</Button><Button variant="primary" disabled={busy}>{card ? '保存修改' : '保存卡片'}</Button></div>
  </form></Modal>
}

function PushSettings({ topic, data, run }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const engines = (data.runtime?.agents || []).filter(agent => !agent.remote)
  const engine = topic.card_engine || 'codex'
  const set = fields => { setError(''); run('set_card_push', { id: topic.id, ...fields }, { quiet: true }).catch(failure => setError(failure.message)) }
  async function generate() {
    setBusy(true); await run('generate_cards', { topic_id: topic.id }); setBusy(false)
  }
  return <div className="card-push">
    <label className="card-push-toggle"><input type="checkbox" checked={!!topic.push_enabled} onChange={event => set({ push_enabled: event.target.checked })} />每天推送</label>
    <select aria-label="每天张数" value={topic.daily_count || 3} onChange={event => set({ daily_count: Number(event.target.value) })}>{Array.from({ length: 10 }, (_, index) => index + 1).map(count => <option key={count} value={count}>每天 {count} 张</option>)}</select>
    <select aria-label="生成通道" value={engine} onChange={event => set({ card_engine: event.target.value })}>{engines.map(agent => <option key={agent.id} value={agent.id}>{agent.label}{agent.available ? '' : '（本机未找到）'}</option>)}</select>
    <Button onClick={generate} disabled={busy}>{busy ? '正在生成…' : `现在生成 ${topic.daily_count || 3} 张`}</Button>
    <small className="muted">{topic.push_enabled ? '每天 8 点后客户端开着时自动生成一次' : '开启后每天自动生成'}{topic.last_push_date ? ` · 上次推送 ${topic.last_push_date}` : ''}{data.settings?.obsidian_vault ? ' · 当天新卡片写入 Obsidian「学习卡片」' : ' · 配置 Obsidian 后会同步写入'}</small>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {topic.last_push_error && <p className="inline-error" role="alert">上次生成失败：{topic.last_push_error}</p>}
  </div>
}

function CardRow({ card, today, run, edit }) {
  async function remove() {
    if (window.confirm(`删除卡片「${card.front.slice(0, 40)}」？删除后无法恢复。`)) await run('delete_card', { id: card.id })
  }
  return <article className="study-row">
    <details><summary><strong>{card.front}</strong></summary>{card.back ? <Markdown text={card.back} /> : <p className="muted">背面还没写。</p>}</details>
    <div className="study-row-meta"><small>{sourceLabel(card)} · {dueLabel(card, today)}</small>
      {card.mastered_at ? <button className="text-link" onClick={() => run('restore_card', { id: card.id })}>恢复复习</button>
        : <button className="text-link" onClick={() => edit(card)}>编辑</button>}
      <button className="text-link" onClick={remove}>删除</button>
    </div>
  </article>
}

export function CardsTab({ topic, data, run }) {
  const [editing, setEditing] = useState(null)
  const cards = (data.learning_cards || []).filter(card => card.topic_id === topic.id).sort((a, b) => b.created_at.localeCompare(a.created_at))
  const active = cards.filter(card => !card.mastered_at)
  const mastered = cards.filter(card => card.mastered_at)
  const due = todayCards(active, data.today).length
  return <div className="cards-tab">
    <PushSettings topic={topic} data={data} run={run} />
    <div className="cards-heading"><span>{active.length} 张在复习{due ? ` · 今天 ${due} 张` : ''}{mastered.length ? ` · 已掌握 ${mastered.length}` : ''}</span><Button variant="primary" onClick={() => setEditing('new')}>＋ 写一张卡片</Button></div>
    {active.length ? active.map(card => <CardRow key={card.id} card={card} today={data.today} run={run} edit={setEditing} />)
      : <Empty title="还没有卡片" detail="自己写一张，或让 AI 按主题目标现在生成。" />}
    {mastered.length > 0 && <details className="cards-mastered"><summary>已掌握 · {mastered.length}</summary>{mastered.map(card => <CardRow key={card.id} card={card} today={data.today} run={run} edit={setEditing} />)}</details>}
    {editing && <CardForm topic={topic} card={editing === 'new' ? null : editing} run={run} close={() => setEditing(null)} />}
  </div>
}

export function CardRules({ data, run }) {
  const saved = data.settings?.card_rules || ''
  const [text, setText] = useState(saved)
  const [open, setOpen] = useState(false)
  const fileInput = useRef(null)
  async function importFile(event) {
    const file = event.target.files[0]
    event.target.value = ''
    if (!file) return
    const content = await file.text()
    setText(current => `${current.trim()}${current.trim() ? '\n\n' : ''}${content.trim()}`.slice(0, 20000))
    setOpen(true)
  }
  return <Panel className="card-rules" title="通用参考" action={<button className="text-link" onClick={() => setOpen(!open)}>{open ? '收起' : saved ? '查看 / 修改' : '添加'}</button>}>
    <p className="muted">所有主题生成卡片时都会遵守，比如答题风格、语言、深度、你的背景。{saved ? `当前 ${saved.length} 字。` : '还没有填写。'}</p>
    {open && <>
      <textarea rows={8} maxLength={20000} value={text} onChange={event => setText(event.target.value)} placeholder={'例如：\n- 答案先给结论，再给原因和例子\n- 面向后端开发岗面试，深度到能回答追问'} />
      <div className="card-rules-actions">
        <Button onClick={() => fileInput.current.click()}>导入 md / txt</Button>
        <input ref={fileInput} type="file" hidden accept=".md,.markdown,.txt,text/markdown,text/plain" onChange={importFile} />
        <small className="muted">{text.length} / 20000</small>
        <Button variant="primary" disabled={text.trim() === saved} onClick={() => run('set_card_rules', { text })}>保存</Button>
      </div>
    </>}
  </Panel>
}

export function TodayCards({ data, run, navigate }) {
  const [revealed, setRevealed] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const topics = Object.fromEntries((data.learning_topics || []).map(topic => [topic.id, topic]))
  const due = todayCards(data.learning_cards, data.today).filter(card => topics[card.topic_id])
  const card = due[0]
  async function rate(rating) {
    setBusy(true); setError('')
    try {
      await run('review_card', { id: card.id, rating }, { quiet: true })
      setRevealed(null)
    } catch (failure) {
      setError(failure.message)
    }
    setBusy(false)
  }
  const action = <button className="text-link" onClick={() => navigate('learning')}>学习 →</button>
  if (!data.learning_topics?.length) return <Panel title="今日学习" action={action} className="today-cards"><p className="muted">在「学习」里建一个主题，写卡片或让 AI 每天推送。</p></Panel>
  if (!card) return <Panel title="今日学习" action={action} className="today-cards"><p className="muted">今天的卡片都学完了。</p></Panel>
  const open = revealed === card.id
  return <Panel title="今日学习" action={<small>还剩 {due.length} 张</small>} className="today-cards">
    <article className="study-card">
      <small className="muted">{isNewCard(card) ? '新卡片' : '复习'} · <button className="text-link" onClick={() => navigate('learning', card.topic_id)}>{topics[card.topic_id].title}</button></small>
      <strong>{card.front}</strong>
      {open ? <>
        <div className="study-card-back">{card.back ? <Markdown text={card.back} /> : <p className="muted">背面还没写。</p>}</div>
        <div className="rating-row">{RATINGS.map(([rating, label]) => <Button key={rating} disabled={busy} variant={rating === 'remembered' ? 'primary' : 'secondary'} onClick={() => rate(rating)}>{label}</Button>)}</div>
      </> : <Button onClick={() => setRevealed(card.id)}>看答案</Button>}
      {error && <p className="inline-error" role="alert">{error}</p>}
    </article>
  </Panel>
}
