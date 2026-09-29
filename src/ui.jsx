import React from 'react'

export const NAV = [
  ['today', '⌂', '首页', 'Today'],
  ['records', '▤', '记录', 'Records'],
  ['tasks', '☑', '任务', 'Tasks'],
  ['projects', '◇', '项目', 'Projects'],
  ['intelligence', '◎', 'AI 日报', 'Reports'],
  ['review', '✓', '审核', 'Review'],
  ['history', '◷', '历史', 'History'],
  ['settings', '⚙', '设置', 'Settings'],
]

export const STATUS = {
  Inbox: '收件箱', Planned: '已计划', Running: '进行中',
  Review: '待审核', Done: '已完成', Blocked: '已阻塞',
}

export const PRIORITY = { High: '高', Medium: '中', Low: '低' }

export function Button({ children, variant = 'secondary', className = '', ...rest }) {
  return <button className={`button ${variant} ${className}`} {...rest}>{children}</button>
}

export function Panel({ title, action, children, className = '' }) {
  return <section className={`panel ${className}`}>
    {(title || action) && <div className="panel-heading"><h2>{title}</h2>{action}</div>}
    {children}
  </section>
}

export function Empty({ title, detail, action }) {
  return <div className="empty"><div className="empty-mark">✧</div><strong>{title}</strong>{detail && <p>{detail}</p>}{action}</div>
}

export function Field({ label, children }) {
  return <label className="field"><span>{label}</span>{children}</label>
}

export function Modal({ title, onClose, children }) {
  return <div className="modal-backdrop" onMouseDown={onClose}>
    <section className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={event => event.stopPropagation()}>
      <div className="modal-heading"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭">×</button></div>
      {children}
    </section>
  </div>
}

export function dateLabel(iso) {
  if (!iso) return '未设置'
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return Number.isNaN(date.getTime()) ? iso : new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(date)
}

export function timeLabel(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(date)
}
