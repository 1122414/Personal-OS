import React, { useRef, useState } from 'react'
import Markdown from '../Markdown.jsx'
import { Button, CollapseTitle, Empty, Field, Modal, Panel, useCollapsed } from '../ui.jsx'
import { RATINGS, deckOrder, dueLabel, isNewCard, sourceLabel, todayCards } from './cards.js'

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

function Flashcard({ card, flipped, onFlip, label }) {
  return <div className={`flashcard ${flipped ? 'flipped' : ''}`} role="button" tabIndex={0} aria-label={flipped ? '翻回正面' : '翻面看答案'}
    onClick={onFlip} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onFlip() } }}>
    <div className="flashcard-inner">
      <div className="flashcard-face flashcard-front" aria-hidden={flipped}>
        <small className="flashcard-label">{label}</small>
        <strong>{card.front}</strong>
        <span className="flashcard-hint">点击翻面看答案</span>
      </div>
      <div className="flashcard-face flashcard-back" aria-hidden={!flipped}>
        <small className="flashcard-label">答案</small>
        <div className="flashcard-answer">{card.back ? <Markdown text={card.back} /> : <p className="muted">背面还没写。</p>}</div>
        {card.basis && <small className="flashcard-basis">依据：{card.basis}</small>}
      </div>
    </div>
  </div>
}

function useRating(run) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function rate(card, rating) {
    setBusy(true); setError('')
    try {
      await run('review_card', { id: card.id, rating }, { quiet: true })
      return true
    } catch (failure) {
      setError(failure.message)
      return false
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, rate }
}

function RatingRow({ busy, onRate }) {
  return <div className="rating-row">{RATINGS.map(([rating, label]) => <Button key={rating} disabled={busy} variant={rating === 'remembered' ? 'primary' : 'secondary'} onClick={() => onRate(rating)}>{label}</Button>)}</div>
}

function PushSettings({ topic, data, run, openMaterials }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const engines = (data.runtime?.agents || []).filter(agent => !agent.remote)
  const engine = topic.card_engine || 'codex'
  const excluded = new Set(topic.card_excluded_record_ids || [])
  const references = topic.record_ids.filter(id => !excluded.has(id) && data.records.some(record => record.id === id)).length
  const set = fields => { setError(''); run('set_card_push', { id: topic.id, ...fields }, { quiet: true }).catch(failure => setError(failure.message)) }
  async function generate() {
    setBusy(true); await run('generate_cards', { topic_id: topic.id }); setBusy(false)
  }
  return <div className="card-push">
    <label className="card-push-toggle"><input type="checkbox" checked={!!topic.push_enabled} onChange={event => set({ push_enabled: event.target.checked })} />每天推送</label>
    <select aria-label="每天张数" value={topic.daily_count || 3} onChange={event => set({ daily_count: Number(event.target.value) })}>{Array.from({ length: 10 }, (_, index) => index + 1).map(count => <option key={count} value={count}>每天 {count} 张</option>)}</select>
    <select aria-label="生成通道" value={engine} onChange={event => set({ card_engine: event.target.value })}>{engines.map(agent => <option key={agent.id} value={agent.id}>{agent.label}{agent.available ? '' : '（本机未找到）'}</option>)}</select>
    <Button onClick={generate} disabled={busy}>{busy ? '正在生成…' : `现在生成 ${topic.daily_count || 3} 张`}</Button>
    <small className="muted">
      <button className="text-link" onClick={openMaterials}>{references ? `参考 ${references} 份资料` : '还没有参考资料，去上传'}</button>
      {data.settings?.card_rules ? ' + 通用参考' : ''}
      {topic.push_enabled ? ' · 每天 8 点后客户端开着时自动生成一次' : ''}{topic.last_push_date === data.today ? ' · 今天已推送' : ''}
      {data.settings?.obsidian_vault ? ' · 写入 Obsidian「学习卡片」' : ''}
    </small>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {topic.last_push_error && <p className="inline-error" role="alert">上次生成失败：{topic.last_push_error}</p>}
  </div>
}

function CardRow({ card, today, run, edit, show }) {
  async function remove() {
    if (window.confirm(`删除卡片「${card.front.slice(0, 40)}」？删除后无法恢复。`)) await run('delete_card', { id: card.id })
  }
  return <div className="study-row">
    {show ? <button className="study-row-front" onClick={() => show(card)} title="在上面的卡片里查看">{card.front}</button> : <span className="study-row-front">{card.front}</span>}
    <small>{sourceLabel(card)} · {dueLabel(card, today)}</small>
    {card.mastered_at ? <button className="text-link" onClick={() => run('restore_card', { id: card.id })}>恢复复习</button>
      : <button className="text-link" onClick={() => edit(card)}>编辑</button>}
    <button className="text-link" onClick={remove}>删除</button>
  </div>
}

export function CardsTab({ topic, data, run, openMaterials }) {
  const [editing, setEditing] = useState(null)
  const [currentId, setCurrentId] = useState(null)
  const [flipped, setFlipped] = useState(false)
  const { busy, error, rate } = useRating(run)
  const cards = (data.learning_cards || []).filter(card => card.topic_id === topic.id)
  const deck = deckOrder(cards, data.today)
  const mastered = cards.filter(card => card.mastered_at)
  const due = todayCards(cards, data.today)
  const index = Math.max(0, deck.findIndex(card => card.id === currentId))
  const card = deck[index]
  const show = next => { setCurrentId(next.id); setFlipped(false) }
  const step = delta => show(deck[(index + delta + deck.length) % deck.length])
  async function review(rating) {
    const next = deck[(index + 1) % deck.length]
    if (await rate(card, rating)) show(next)
  }
  async function remove() {
    if (window.confirm(`删除卡片「${card.front.slice(0, 40)}」？删除后无法恢复。`) && await run('delete_card', { id: card.id })) setFlipped(false)
  }
  const isDue = card && due.some(item => item.id === card.id)
  return <div className="cards-tab">
    <PushSettings topic={topic} data={data} run={run} openMaterials={openMaterials} />
    {card ? <section className="deck">
      <div className="deck-meta">
        <span>{deck.length} 张在复习{due.length ? ` · 今天 ${due.length} 张` : ''}{mastered.length ? ` · 已掌握 ${mastered.length}` : ''}</span>
        <Button variant="primary" onClick={() => setEditing('new')}>＋ 写一张卡片</Button>
      </div>
      <Flashcard card={card} flipped={flipped} onFlip={() => setFlipped(!flipped)} label={`${isNewCard(card) ? '新卡片' : '复习'} · ${dueLabel(card, data.today)} · ${sourceLabel(card)}`} />
      {flipped && isDue && <RatingRow busy={busy} onRate={review} />}
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="deck-nav">
        <button className="deck-arrow" onClick={() => step(-1)} disabled={deck.length < 2} aria-label="上一张">‹</button>
        <span>{index + 1} / {deck.length}</span>
        <button className="deck-arrow" onClick={() => step(1)} disabled={deck.length < 2} aria-label="下一张">›</button>
        <span className="deck-tools"><button className="text-link" onClick={() => setEditing(card)}>编辑</button><button className="text-link" onClick={remove}>删除</button></span>
      </div>
    </section> : <Empty title={mastered.length ? '卡片都掌握了' : '还没有卡片'} detail="上传资料后让 AI 生成，或自己写一张。" action={<Button variant="primary" onClick={() => setEditing('new')}>＋ 写一张卡片</Button>} />}
    {cards.length > 0 && <details className="cards-manage"><summary>管理全部卡片 · {cards.length}</summary>
      {deck.map(item => <CardRow key={item.id} card={item} today={data.today} run={run} edit={setEditing} show={show} />)}
      {mastered.length > 0 && <><p className="cards-manage-label">已掌握 · {mastered.length}</p>{mastered.map(item => <CardRow key={item.id} card={item} today={data.today} run={run} edit={setEditing} />)}</>}
    </details>}
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
  const [flippedId, setFlippedId] = useState(null)
  const [collapsed, toggle] = useCollapsed('personal-os.today-cards-collapsed')
  const { busy, error, rate } = useRating(run)
  const topics = Object.fromEntries((data.learning_topics || []).map(topic => [topic.id, topic]))
  const due = todayCards(data.learning_cards, data.today).filter(card => topics[card.topic_id])
  const card = due[0]
  const title = <CollapseTitle collapsed={collapsed} onToggle={toggle}>今日学习</CollapseTitle>
  const action = <button className="text-link" onClick={() => navigate('learning')}>学习 →</button>
  if (!data.learning_topics?.length) return <Panel title="今日学习" action={action} className="today-cards"><p className="muted">在「学习」里建一个主题，写卡片或让 AI 每天推送。</p></Panel>
  if (collapsed) return <Panel title={title} action={<small>{card ? `还剩 ${due.length} 张` : '今天学完了'}</small>} className="today-cards collapsed" />
  if (!card) return <Panel title={title} action={action} className="today-cards"><p className="muted">今天的卡片都学完了。</p></Panel>
  const flipped = flippedId === card.id
  return <Panel title={title} action={<span className="panel-tools"><small>还剩 {due.length} 张</small><button className="text-link" onClick={() => navigate('learning', card.topic_id)}>{topics[card.topic_id].title} →</button></span>} className="today-cards">
    <Flashcard card={card} flipped={flipped} onFlip={() => setFlippedId(flipped ? null : card.id)} label={isNewCard(card) ? '新卡片' : '复习'} />
    {flipped && <RatingRow busy={busy} onRate={async rating => { if (await rate(card, rating)) setFlippedId(null) }} />}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </Panel>
}
