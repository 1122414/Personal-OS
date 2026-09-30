import React from 'react'

const ICONS = {
  today: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9v12h14V9" /><path d="M10 21v-6h4v6" /></>,
  records: <><path d="M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6" /><path d="M18.4 2.6a2 2 0 0 1 2.9 2.9L12 14.8 8 16l1.2-4z" /></>,
  learning: <><path d="M2 5h6a4 4 0 0 1 4 4v11a3 3 0 0 0-3-3H2z" /><path d="M22 5h-6a4 4 0 0 0-4 4v11a3 3 0 0 1 3-3h7z" /></>,
  todos: <><path d="M9 6h11M9 12h11M9 18h11" /><path d="m3.5 6 1.2 1.2L7 5M3.5 12l1.2 1.2L7 11M3.5 18l1.2 1.2L7 17" /></>,
  tasks: <><rect x="3" y="3" width="18" height="18" rx="3" /><path d="m8 12 3 3 5-6" /></>,
  projects: <><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 13 9 5 9-5" /></>,
  intelligence: <><path d="M4 5h12v14a2 2 0 0 0 2 2H6a2 2 0 0 1-2-2z" /><path d="M16 9h4v10a2 2 0 0 1-2 2" /><path d="M8 9h4M8 13h4M8 17h2" /></>,
  review: <><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="m9 14 2 2 4-4" /></>,
  history: <><path d="M3.5 12a8.5 8.5 0 1 0 2.5-6L3 9" /><path d="M3 3.5V9h5.5" /><path d="M12 7.5V12l3 2" /></>,
  settings: <><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" /><circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></>,
}

export function Icon({ name }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
}

export const NAV = [
  ['today', '首页', 'Today'],
  ['records', '记录', 'Records'],
  ['todos', '待办', 'To-dos'],
  ['learning', '学习', 'Learning'],
  ['tasks', 'Agent 任务', 'Agents'],
  ['projects', '项目', 'Projects'],
  ['intelligence', 'AI 日报', 'Reports'],
  ['history', '工作日报', 'Daily Log'],
  ['settings', '设置', 'Settings'],
]

export const STATUS = {
  Inbox: '待派出', Planned: '待派出', Running: '运行中',
  Reply: '等你回复', Review: '待验收', Done: '已完成', Blocked: '失败或取消',
}

export function taskState(task, runs) {
  if (task.status === 'Planned') return 'Inbox'
  return task.status === 'Review' && runs.find(run => run.task_id === task.id)?.needs_reply ? 'Reply' : task.status
}

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

export function runDuration(run, now = Date.now()) {
  if (!run?.started_at) return ''
  const end = run.finished_at ? new Date(run.finished_at).getTime() : now
  const seconds = Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000))
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor(seconds % 3600 / 60)} 分`
}
