import React, { useState } from 'react'
import { Button, Empty, Panel, dateLabel } from '../ui.jsx'
import { PRIORITIES, dropBefore, nextPriority, todoOrder } from '../todos.js'

export function carriedLabel(days) {
  return days === 1 ? '昨天未完成' : `${days} 天前`
}

/** Drag to reorder within a column or move between the pool and today. */
export function useTodoDrag(run) {
  const [dragging, setDragging] = useState(null)
  const [target, setTarget] = useState(null)
  const [error, setError] = useState('')
  function reset() { setDragging(null); setTarget(null) }
  function drop(event) {
    event.preventDefault(); event.stopPropagation()
    if (dragging && target && target.before !== dragging) {
      setError('')
      run('move_todo', { id: dragging, today: target.column === 'today', before_id: target.before }, { quiet: true }).catch(failure => setError(failure.message))
    }
    reset()
  }
  const row = (todo, column, list) => todo.done_at || todo.archived_at ? {} : {
    draggable: true,
    onDragStart: event => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', todo.id); setDragging(todo.id) },
    onDragEnd: reset,
    onDragOver: event => {
      if (!dragging) return
      event.preventDefault(); event.stopPropagation()
      const rect = event.currentTarget.getBoundingClientRect()
      const before = dropBefore(list, todo.id, event.clientY > rect.top + rect.height / 2)
      if (target?.column !== column || target?.before !== before) setTarget({ column, before })
    },
    onDrop: drop,
    className: `${dragging === todo.id ? 'dragging' : ''} ${target?.column === column && target.before === todo.id && dragging !== todo.id ? 'drop-before' : ''}`,
  }
  const column = name => ({
    onDragOver: event => { if (!dragging) return; event.preventDefault(); if (target?.column !== name) setTarget({ column: name, before: null }) },
    onDrop: drop,
    className: target?.column === name && target.before === null ? 'drop-end' : '',
  })
  return { row, column, error }
}

export function TodoRow({ todo, run, open, actions, drag = {} }) {
  const done = !!todo.done_at
  const priority = todo.priority || 'medium'
  const { className = '', ...handlers } = drag
  return <div className={`todo-row ${done ? 'done' : ''} ${handlers.draggable ? 'draggable' : ''} ${className}`} {...handlers}>
    <button className={`task-ring todo-check ${done ? 'checked' : ''}`} aria-label={done ? `取消完成：${todo.title}` : `完成：${todo.title}`} onClick={() => run('toggle_todo', { id: todo.id }, { quiet: true })}>{done ? '✓' : ''}</button>
    <div className="todo-text">
      <div className="todo-head">
        <button className={`todo-priority priority-${priority}`} title="点击切换优先级" aria-label={`优先级${PRIORITIES[priority]}，点击切换`} onClick={() => run('update_todo', { id: todo.id, priority: nextPriority(priority) }, { quiet: true })}>{PRIORITIES[priority]}</button>
        <button className="todo-title" onClick={() => open('todo-edit', todo)} title="编辑待办">{todo.title}</button>
        {todo.carried_days > 0 && <span className="todo-carry">{carriedLabel(todo.carried_days)}</span>}
      </div>
      {todo.note && <p>{todo.note}</p>}
    </div>
    {actions && <div className="todo-actions">{actions}</div>}
  </div>
}

export function AddTodo({ run, today = false, placeholder }) {
  const [title, setTitle] = useState('')
  async function submit(event) {
    event.preventDefault()
    if (!title.trim()) return
    if (await run('create_todo', { title, today }, { quiet: true })) setTitle('')
  }
  return <form className="todo-add" onSubmit={submit}><input value={title} onChange={event => setTitle(event.target.value)} maxLength={200} placeholder={placeholder} aria-label={placeholder} /></form>
}

export default function Todos({ data, run, open }) {
  const todos = data.todos.filter(todo => !todo.archived_at)
  const todayIds = new Set((data.today_todos || []).map(todo => todo.id))
  const pool = todos.filter(todo => !todo.done_at && !todayIds.has(todo.id)).sort(todoOrder)
  const todayOpen = (data.today_todos || []).filter(todo => !todo.done_at)
  const drag = useTodoDrag(run)
  const done = todos.filter(todo => todo.done_at && !todayIds.has(todo.id)).sort((a, b) => b.done_at.localeCompare(a.done_at))
  const archived = data.todos.filter(todo => todo.archived_at)
  const archive = todo => <button className="text-link" onClick={() => run('archive_todo', { id: todo.id }, { quiet: true })}>归档</button>
  return <div className="page todos-page">{drag.error && <p className="inline-error" role="alert">{drag.error}</p>}<div className="todo-columns">
    <Panel title="待办池" action={<small>{pool.length} 件</small>}>
      <AddTodo run={run} placeholder="记一件以后要做的事，回车保存" />
      <div {...drag.column('pool')} className={`panel-body ${drag.column('pool').className}`}>{pool.length ? pool.map(todo => <TodoRow key={todo.id} todo={todo} run={run} open={open} drag={drag.row(todo, 'pool', pool)} actions={<><Button onClick={() => run('plan_todo', { id: todo.id, today: true }, { quiet: true })}>→ 今天</Button>{archive(todo)}</>} />) : <Empty title="待办池是空的" detail="随手记里的内容也可以转成待办。" />}</div>
    </Panel>
    <Panel title="今天" action={<small>{(data.today_todos || []).filter(todo => todo.done_at).length} / {todayIds.size} 已完成</small>}>
      <AddTodo run={run} today placeholder="加一件今天要做的事，回车保存" />
      <div {...drag.column('today')} className={`panel-body ${drag.column('today').className}`}>{todayIds.size ? data.today_todos.map(todo => <TodoRow key={todo.id} todo={todo} run={run} open={open} drag={drag.row(todo, 'today', todayOpen)} actions={!todo.done_at && <button className="text-link" onClick={() => run('plan_todo', { id: todo.id, today: false }, { quiet: true })}>移回待办池</button>} />) : <Empty title="今天还没有待办" detail="从左边挑几件，或直接写一件。" />}</div>
    </Panel>
    <Panel title="已完成" action={<small>{done.length} 件</small>}>
      <div className="panel-body">{done.length ? done.slice(0, 50).map(todo => <TodoRow key={todo.id} todo={todo} run={run} open={open} actions={<><small className="muted">{dateLabel(todo.done_at)}</small>{archive(todo)}</>} />) : <p className="muted">完成的待办会在第二天移到这里。</p>}
        {archived.length > 0 && <details className="todo-archived"><summary>已归档 · {archived.length}</summary>{archived.map(todo => <TodoRow key={todo.id} todo={todo} run={run} open={open} actions={<><button className="text-link" onClick={() => run('archive_todo', { id: todo.id, restore: true }, { quiet: true })}>取消归档</button><button className="text-link" onClick={() => { if (window.confirm(`删除待办「${todo.title}」？删除后无法恢复。`)) run('delete_todo', { id: todo.id }) }}>删除</button></>} />)}</details>}
      </div>
    </Panel>
  </div></div>
}
