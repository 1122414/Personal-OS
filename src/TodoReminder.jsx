import React, { useEffect, useRef } from 'react'
import { Button, Modal } from './ui.jsx'
import { PRIORITIES } from './todos.js'

export const REMINDER_HOUR = 20

/** Once a day from 20:00 until midnight, while today's to-dos are unfinished. */
export default function TodoReminder({ data, run, navigate }) {
  const pending = (data.today_todos || []).filter(todo => !todo.done_at)
  const due = new Date().getHours() >= REMINDER_HOUR && data.settings?.todo_reminder_date !== data.today && pending.length > 0
  const notified = useRef(null)
  useEffect(() => {
    if (!due || notified.current === data.today) return
    notified.current = data.today
    const titles = pending.slice(0, 3).map(todo => todo.title).join('、')
    window.webkit?.messageHandlers?.notify?.postMessage({ title: `今天还有 ${pending.length} 件待办没完成`, body: pending.length > 3 ? `${titles} 等` : titles, taskId: '' })
  }, [due, data.today])
  if (!due) return null
  const dismiss = () => run('dismiss_todo_reminder', {})
  return <Modal title={`晚上 8 点了，今天还有 ${pending.length} 件没完成`} onClose={dismiss}>
    <div className="reminder-list">{pending.map(todo => <div className="reminder-row" key={todo.id}>
      <button className="task-ring todo-check" aria-label={`完成：${todo.title}`} onClick={() => run('toggle_todo', { id: todo.id }, { quiet: true }).catch(() => {})} />
      <span className={`todo-priority priority-${todo.priority || 'medium'}`}>{PRIORITIES[todo.priority || 'medium']}</span>
      <span className="reminder-title">{todo.title}</span>
    </div>)}</div>
    <p className="muted">勾掉做完的；没做完的明天会继续留在「今天」。</p>
    <div className="modal-actions"><Button onClick={() => { dismiss(); navigate('todos') }}>去待办页</Button><Button variant="primary" onClick={dismiss}>知道了，今晚不再提醒</Button></div>
  </Modal>
}
