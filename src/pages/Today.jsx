import React from 'react'
import { Button, Empty, Panel } from '../ui.jsx'
import { AddTodo, TodoRow, useTodoDrag } from './Todos.jsx'

export default function TodayPlan({ data, run, open, navigate }) {
  const log = data.daily_logs.find(item => item.date === data.today)
  const todos = data.today_todos || []
  const todayIds = new Set(todos.map(todo => todo.id))
  const pool = data.todos.filter(todo => !todo.done_at && !todo.archived_at && !todayIds.has(todo.id))
  const suggestions = data.brief || []
  const done = todos.filter(todo => todo.done_at).length
  const pending = todos.filter(todo => !todo.done_at)
  const drag = useTodoDrag(run)
  const hour = new Date().getHours()
  const review = hour >= 20 || hour < 6
  const canSuggest = data.runtime?.codex_available && !suggestions.length && (pool.length + todos.length - done) > 1

  return <Panel className="work-panel today-plan" title={review ? '今天 · 回顾' : '今天'} action={<span className="panel-tools"><span className="overline">{done} / {todos.length} 已完成</span><button className="text-link" onClick={() => navigate('todos')}>全部待办 →</button><Button variant="primary" className="compact" onClick={() => navigate('history')}>{log ? (log.confirmed_at ? '查看今日日报' : '核对并结束今天') : '生成今日日报'}</Button></span>}>
    <div className="todo-toolbar">
      <AddTodo run={run} today placeholder="加一件今天要做的事，回车保存" />
      {pool.length > 0 && <select aria-label="从待办池里挑" value="" onChange={event => event.target.value && run('plan_todo', { id: event.target.value, today: true }, { quiet: true })}><option value="">从待办池里挑…</option>{pool.map(todo => <option key={todo.id} value={todo.id}>{todo.title}</option>)}</select>}
      {canSuggest && <Button className="compact" onClick={() => run('generate_brief', {})}>AI 建议先做</Button>}
    </div>
    {suggestions.length > 0 && <p className="todo-suggest"><span className="overline">建议先做</span>{suggestions.map(item => <button key={item.todo_id} title={item.reason} onClick={() => !todayIds.has(item.todo_id) && run('plan_todo', { id: item.todo_id, today: true }, { quiet: true })}>{item.title}{todayIds.has(item.todo_id) ? '' : ' ＋'}</button>)}</p>}
    {drag.error && <p className="inline-error" role="alert">{drag.error}</p>}
    <div {...drag.column('today')} className={`work-list ${drag.column('today').className}`}>{todos.length ? todos.map(todo => <TodoRow key={todo.id} todo={todo} run={run} open={open} drag={drag.row(todo, 'today', pending)}
      actions={!todo.done_at && <button className="icon-button" title="移回待办池" aria-label={`移回待办池：${todo.title}`} onClick={() => run('plan_todo', { id: todo.id, today: false }, { quiet: true })}>×</button>} />)
      : <Empty title="今天还没有待办" detail="写一件，或从待办池里挑几件。" />}</div>
  </Panel>
}
