import React, { useEffect, useState } from 'react'
import LearningSummary from '../LearningSummary.jsx'
import { RelatedRecords } from '../PersonalState.jsx'
import { Button, Empty, Panel } from '../ui.jsx'
import { TopicForm, recordDate } from '../workspace.jsx'
import Conversation from '../learning/Conversation.jsx'
import TopicMaterials from '../learning/TopicMaterials.jsx'
import { CardRules, CardsTab } from '../learning/Cards.jsx'
import { todayCards } from '../learning/cards.js'
import { useLearningDetail, useLearningDraft } from '../learning/useLearningWorkspace.js'

function TopicWorkspace({ topic, data, run, navigate }) {
  const { detail, error, reload } = useLearningDetail(topic.id)
  const draft = useLearningDraft(topic.id, run, reload, detail?.materials)
  const [tab, setTab] = useState(() => window.location.hash.split('/')[2] ? 'chat' : 'cards')
  const [editing, setEditing] = useState(false)
  const current = detail?.topic?.updated_at > topic.updated_at ? detail.topic : topic
  const hasRelated = !!detail?.related_records?.length

  useEffect(() => {
    function navigateMessage() {
      if (window.location.hash.split('/')[2]) setTab('chat')
    }
    window.addEventListener('hashchange', navigateMessage)
    return () => window.removeEventListener('hashchange', navigateMessage)
  }, [])

  async function changeMode(mode) {
    if (await run('update_learning_topic', { id: current.id, expected_updated_at: current.updated_at, mode })) await reload()
  }

  let content = <Empty title="正在读取对话…" />
  if (tab === 'cards') {
    content = <CardsTab topic={topic} data={data} run={run} />
  } else if (detail && tab === 'summary') {
    content = <LearningSummary topic={current} detail={detail} data={data} run={run} reload={reload} setTab={setTab} />
  } else if (detail && tab === 'chat') {
    content = (
      <div className={hasRelated ? 'conversation-layout has-related' : 'conversation-layout'}>
        <Conversation topic={current} detail={detail} run={run} reload={reload} draft={draft} />
        {hasRelated && (
          <aside className="chat-related">
            <RelatedRecords detail={detail} data={data} run={run} reload={reload} topicId={topic.id} />
          </aside>
        )}
      </div>
    )
  } else if (detail) {
    content = <TopicMaterials topic={current} data={data} detail={detail} run={run} reload={reload} />
  }

  return (
    <div className="topic-workspace panel">
      <div className="topic-heading">
        <div>
          <button className="text-link" onClick={() => navigate('learning')}>学习 / 全部主题</button>
          <h1>{current.title}</h1>
          <p>{current.goal || '从问题出发，逐步明确想弄清楚的事。'}</p>
        </div>
        <div className="workspace-actions">
          <select aria-label="学习 Agent" value="codex" onChange={() => {}}><option value="codex">Codex</option></select>
          <select aria-label="学习模式" value={current.mode} onChange={event => changeMode(event.target.value)}>
            <option value="guided">带着学</option>
            <option value="quick">随问随答</option>
          </select>
          <Button onClick={() => setEditing(true)}>修改目标</Button>
        </div>
      </div>
      <div className="tabs topic-tabs">
        <button className={tab === 'cards' ? 'active' : ''} onClick={() => setTab('cards')}>卡片</button>
        <button className={tab === 'summary' ? 'active' : ''} onClick={() => setTab('summary')}>总结</button>
        <button className={tab === 'chat' ? 'active' : ''} onClick={() => setTab('chat')}>对话</button>
        <button className={tab === 'materials' ? 'active' : ''} onClick={() => setTab('materials')}>资料</button>
      </div>
      {error && <p className="inline-error" role="alert">{error}<Button onClick={reload}>重新读取</Button></p>}
      {content}
      {editing && <TopicForm topic={current} run={run} close={() => setEditing(false)} onSaved={reload} />}
    </div>
  )
}

function cardSummary(topic, data) {
  const cards = (data.learning_cards || []).filter(card => card.topic_id === topic.id && !card.mastered_at)
  const due = todayCards(cards, data.today).length
  const push = topic.push_enabled ? ` · 每天推送 ${topic.daily_count || 3} 张` : ''
  return `${cards.length} 张卡片${due ? `，今天 ${due} 张` : ''}${push}`
}

export default function Learning({ data, run, focus, navigate }) {
  const [creating, setCreating] = useState(false)
  const topic = data.learning_topics.find(item => item.id === focus)
  return (
    <div className="page learning-page">
      {topic ? <TopicWorkspace key={topic.id} topic={topic} data={data} run={run} navigate={navigate} /> : (
        <>
          <div className="page-toolbar">
            <span>随时回来，接着上次继续。</span>
            <Button variant="primary" onClick={() => setCreating(true)}>＋ 新主题</Button>
          </div>
          <CardRules data={data} run={run} />
          <Panel className="topic-list">
            {data.learning_topics.length ? data.learning_topics.map(item => (
              <button className="topic-card" key={item.id} onClick={() => navigate('learning', item.id)}>
                <span className="topic-symbol">▤</span>
                <div>
                  <h2>{item.title}</h2>
                  <p>{item.goal || '从上次的想法继续探索。'}</p>
                  <small>{cardSummary(item, data)} · Codex · {item.mode === 'guided' ? '带着学' : '随问随答'} · {recordDate(item)}</small>
                </div>
                <span>继续学习 →</span>
              </button>
            )) : (
              <Empty
                title="想学习什么，就从这里开始"
                detail="临时问题可以随问随答，持续目标可以带着学。"
                action={<Button onClick={() => setCreating(true)}>创建第一个主题</Button>}
              />
            )}
          </Panel>
        </>
      )}
      {creating && <TopicForm run={run} close={() => setCreating(false)} onSaved={item => navigate('learning', item.id)} />}
    </div>
  )
}
