import React, { useState } from 'react'
import Markdown from '../Markdown.jsx'
import { Button, Empty, Panel, STATUS, dateLabel } from '../ui.jsx'
import { Capture, RECORD_TYPES, TopicForm, recordDate } from '../workspace.jsx'
import PersonalState, { RecallCard } from '../PersonalState.jsx'
import Today from './Today.jsx'

export default function Home({ data, run, open, navigate }) {
  const [view, setView] = useState('workspace')
  const [creating, setCreating] = useState(false)
  const topics = [...data.learning_topics].sort((a, b) => (b.last_activity_at || b.updated_at).localeCompare(a.last_activity_at || a.updated_at)).slice(0, 3)
  const plan = data.daily_plans.find(item => item.date === data.today)
  const tasks = (plan?.task_ids || []).map(id => data.tasks.find(task => task.id === id)).filter(Boolean)
  const review = data.weekly_review?.items || []
  return <div className="page home-page"><div className="home-viewbar"><div className="tabs"><button className={view === 'workspace' ? 'active' : ''} onClick={() => setView('workspace')}>个人工作台</button><button className={view === 'work' ? 'active' : ''} onClick={() => setView('work')}>今日计划</button></div><small>{dateLabel(data.today)}</small></div>
    {view === 'work' ? <Today data={data} run={run} open={open} navigate={navigate} /> : <div className="home-scroll">
      <Panel title="随手记" className="home-capture" action={<small>先留下，不急着分类</small>}><Capture compact run={run} /></Panel>
      <div className="home-columns"><div className="home-primary">
        <Panel title="继续学习" action={<button className="text-link" onClick={() => navigate('learning')}>全部主题 →</button>}>
          {topics.length ? topics.map(topic => <article className="continue-topic" key={topic.id}><div className="continue-topic-heading"><span className="topic-symbol">▤</span><div><h3>{topic.title}</h3><small>Codex · {topic.mode === 'guided' ? '带着学' : '随问随答'}{topic.summary_at && topic.last_completed_at > topic.summary_at ? ' · 有新对话待整理' : ''}</small></div></div><Markdown text={topic.brief || topic.goal || '从一个问题开始，留下可以继续的线索。'} /><div className="workspace-actions"><Button variant="primary" onClick={() => navigate('learning', `${topic.id}/chat`)}>继续对话 →</Button><button className="text-link" onClick={() => navigate('learning', topic.id)}>查看总结</button></div></article>) : <Empty title="把好奇的事留成一个主题" detail="随问随答，或让 Codex 带着学。" action={<Button variant="primary" onClick={() => setCreating(true)}>开始学习 →</Button>} />}
        </Panel>
        <Panel title="最近记录" action={<button className="text-link" onClick={() => navigate('records')}>全部记录 →</button>}>
          {data.records.length ? data.records.slice(0, 4).map(record => <button className="recent-record" key={record.id} onClick={() => navigate('records', record.id)}><span className="small-symbol">{record.record_type === 'idea' ? '✦' : '▤'}</span><span><strong>{record.title}</strong><small>{RECORD_TYPES[record.record_type]} · {recordDate(record)}</small></span><span>↗</span></button>) : <p className="muted">第一条记录，可以只是刚刚想到的一句话。</p>}
        </Panel>
      </div><div className="home-secondary">
        <Panel title="近期状态"><PersonalState data={data} run={run} /></Panel>
        <Panel title="今日任务" action={<button className="text-link" onClick={() => setView('work')}>查看计划 →</button>}>
          {tasks.length ? tasks.slice(0, 4).map(task => <button key={task.id} className="mini-row" onClick={() => navigate('tasks', task.id)}><span className={`task-ring ${task.status === 'Done' ? 'checked' : ''}`}>{task.status === 'Done' ? '✓' : ''}</span><span>{task.title}</span><small>{STATUS[task.status]}</small></button>) : <p className="muted">{plan ? '今天留些空白，也可以。' : '还没有确认今天的计划。'}</p>}
          {!plan && <Button onClick={() => setView('work')}>安排今天</Button>}
        </Panel>
        {review.length > 0 && <Panel title="本周，想起这些点子" action={<small>{review.length} 条</small>}>{review.map(item => <RecallCard key={item.record_id} item={item} record={item.record} topicTitle={item.topic_title} run={run} />)}</Panel>}
      </div></div>
    </div>}
    {creating && <TopicForm run={run} close={() => setCreating(false)} onSaved={topic => navigate('learning', topic.id)} />}
  </div>
}
