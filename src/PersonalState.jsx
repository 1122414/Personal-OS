import React, { useState } from 'react'
import { createPortal } from 'react-dom'
import { Button, Field, Modal, dateLabel } from './ui.jsx'

const PACE = { normal: '照常推进', light: '小段推进', rest: '以休息为主' }
function localDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export function StateForm({ state, record, run, close }) {
  const [busy, setBusy] = useState(false)
  return <Modal title={state ? '修正近期状态' : '记下近期状态'} onClose={close}><form onSubmit={async event => {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    setBusy(true)
    const result = await run(state ? 'update_personal_state' : 'create_personal_state', {
      ...values, avoid_new_projects: values.avoid_new_projects === 'on',
      ...(state ? { id: state.id, expected_updated_at: state.updated_at } : record ? { record_id: record.id } : {}),
    })
    setBusy(false)
    if (result) close()
  }}>
    <Field label="你的原话"><textarea name="text" defaultValue={state?.text || record?.content || ''} readOnly={!!record} rows={4} maxLength={4000} required autoFocus /></Field>
    <Field label="新建议的节奏"><select name="pace" defaultValue={state?.pace || 'normal'}>{Object.entries(PACE).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></Field>
    <label className="state-preference"><input type="checkbox" name="avoid_new_projects" defaultChecked={state?.avoid_new_projects || false} />这段时间不推荐开新项目</label>
    <Field label="有效至（留空默认 7 天）"><input type="datetime-local" name="expires_at" defaultValue={localDateTime(state?.expires_at)} /></Field>
    <p className="muted">到期停止影响新建议，原话会保留在记录中。已确认计划仍由你调整。</p>
    <div className="modal-actions"><Button type="button" onClick={close}>取消</Button><Button variant="primary" disabled={busy}>{state ? '保存修正' : '保存并生效'}</Button></div>
  </form></Modal>
}

export default function PersonalState({ data, run }) {
  const [editing, setEditing] = useState(null)
  const [creating, setCreating] = useState(false)
  const states = data.personal_states || []
  const active = states.filter(state => state.active || (!state.confirmed_at && !state.ended_at && !state.expired))
  const past = states.filter(state => !active.includes(state))
  return <div className="personal-states">
    {active.length ? active.map(state => <article className="state-card" key={state.id}>
      <p>{state.text}</p><small>{state.confirmed_at ? PACE[state.pace] : '待确认的推测 · 尚未生效'}{state.avoid_new_projects ? ' · 不开新项目' : ''} · 至 {dateLabel(state.expires_at)}</small>
      <div className="workspace-actions"><a href={`#records/${state.record_id}`}>原话 ↗</a>{!state.confirmed_at && <Button onClick={() => run('confirm_personal_state', { id: state.id, expected_updated_at: state.updated_at })}>符合我的状态</Button>}<button className="text-link" onClick={() => setEditing(state)}>修正</button><button className="text-link" onClick={() => run('end_personal_state', { id: state.id, expected_updated_at: state.updated_at })}>{state.confirmed_at ? '提前结束' : '不采纳'}</button></div>
    </article>) : <p className="muted">记下你此刻的节奏，让后续建议更贴近你。</p>}
    <Button onClick={() => setCreating(true)}>＋ 记下状态</Button>
    {past.length > 0 && <details className="state-history"><summary>过去的状态 · {past.length}</summary>{past.map(state => <article key={state.id}><p>{state.text}</p><small>{state.ended_at ? '已结束' : '已过期'} · 不再影响建议</small><a href={`#records/${state.record_id}`}>查看原话 ↗</a></article>)}</details>}
    {(creating || editing) && <StateForm state={editing} run={run} close={() => { setEditing(null); setCreating(false) }} />}
  </div>
}

export function StateChip({ data, run }) {
  const [open, setOpen] = useState(false)
  const states = data.personal_states || []
  const current = states.find(state => state.active) || states.find(state => !state.confirmed_at && !state.ended_at && !state.expired)
  const label = current ? `${current.confirmed_at ? '' : '待确认 · '}${current.text} · 至 ${dateLabel(current.expires_at)}` : '＋ 记下近期状态'
  return <>
    <button className="state-chip" title={current ? `近期状态：${current.text}` : '记下近期状态'} onClick={() => setOpen(true)}>{label}</button>
    {open && createPortal(<Modal title="近期状态" onClose={() => setOpen(false)}><PersonalState data={data} run={run} /></Modal>, document.querySelector('.app-shell') || document.body)}
  </>
}

export function RecallCard({ item, record, run, onChange, topicId, topicTitle }) {
  const [busy, setBusy] = useState(false)
  if (!record) return null
  async function feedback(choice) {
    setBusy(true)
    const result = await run('recall_feedback', { id: record.id, choice })
    setBusy(false)
    if (result) { onChange?.(); if (choice === 'continue') window.location.hash = `records/${record.id}` }
  }
  return <article className="recall-card"><a href={`#records/${record.id}`}>{record.title} ↗</a>{topicTitle && <small>与「{topicTitle}」有关</small>}<p>{item.reason}</p><div className="workspace-actions"><Button disabled={busy} onClick={() => feedback('continue')}>继续想想</Button>{topicId && <Button disabled={busy} onClick={async () => { setBusy(true); if (await run('link_record', { id: topicId, record_id: record.id })) onChange?.(); setBusy(false) }}>加入本主题</Button>}<button className="text-link" disabled={busy} onClick={() => feedback('defer')}>搁置 7 天</button><button className="text-link" disabled={busy} onClick={() => feedback('never')}>不再推荐</button></div></article>
}

export function RelatedRecords({ detail, data, run, reload, topicId }) {
  if (!detail.related_records?.length) return null
  return <section className="related-suggestions"><h3>想起一条旧记录</h3>{detail.related_records.map(item => <RecallCard key={item.record_id} item={item} record={data.records.find(record => record.id === item.record_id)} run={run} topicId={topicId} onChange={reload} />)}</section>
}
