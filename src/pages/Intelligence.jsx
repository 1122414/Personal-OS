import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, dateLabel } from '../ui.jsx'
import DailyReports from './DailyReports.jsx'

export default function Intelligence(props) {
  return <div className="page intelligence-shell"><DailyReports {...props} /></div>
}

function SourceIntelligence({ data, run, open, focus, conversations }) {
  const [channelId, setChannel] = useState('all')
  const [selectedId, select] = useState(focus || null)
  useEffect(() => { if (focus) select(focus) }, [focus])
  const channels = data.intelligence_channels.filter(item => (item.connector === 'workbuddy') === conversations)
  const items = data.intelligence_items.filter(item => (item.source_kind === 'workbuddy') === conversations && item.feedback !== 'ignore' && (channelId === 'all' || item.channel_id === channelId))
  const selected = items.find(item => item.id === selectedId) || items[0]
  const channel = data.intelligence_channels.find(item => item.id === selected?.channel_id)
  const project = data.projects.find(item => item.id === selected?.project_id)

  return <div className="page intelligence-page"><div className="intelligence-layout">
    <Panel className="channel-rail" title="频道" action={<button className="icon-button" onClick={() => open('channel')} title="新建频道">＋</button>}><button className={`channel-option ${channelId === 'all' ? 'selected' : ''}`} onClick={() => setChannel('all')}>✦ <span>全部内容</span></button>{channels.map(item => <button className={`channel-option ${channelId === item.id ? 'selected' : ''}`} onClick={() => setChannel(item.id)} key={item.id}>◎ <span>{item.name}</span></button>)}<Button className="channel-add" onClick={() => open('channel')}>＋ 新建频道</Button>{channelId !== 'all' && <div className="channel-tools"><p className="muted">{channelId === 'workbuddy' ? '按原会话更新时间排序；同步范围在设置中调整。' : '按关键词筛选；收藏和忽略暂不训练推荐模型。'}</p>{channelId !== 'workbuddy' && <Button onClick={() => open('channel-edit', data.intelligence_channels.find(item => item.id === channelId))}>编辑边界</Button>}<Button onClick={() => run(channelId === 'workbuddy' ? 'sync_workbuddy' : 'refresh_channel', { id: channelId })}>刷新来源</Button>{data.intelligence_channels.find(item => item.id === channelId)?.last_refresh?.errors?.map((error, index) => <p className="notice" role="alert" key={index}>{error.source}：{error.error}</p>)}</div>}</Panel>
    <Panel className="intelligence-list" title={conversations ? "历史会话（可选）" : "情报与资料"} action={<span className="overline">{items.length} 条</span>}>
      {items.length ? items.map(item => <button key={item.id} className={`intelligence-card ${selected?.id === item.id ? 'selected' : ''}`} onClick={() => { select(item.id); if (item.feedback === 'unread') run('feedback_intelligence', { id: item.id, feedback: 'read' }) }}><span className="article-image">✧</span><span><strong>{item.title}</strong><p>{item.summary || item.why_recommended}</p><small>{item.source} · {item.published_at ? `发布于 ${dateLabel(item.published_at)}` : '发布时间未知'}</small></span></button>) : <Empty title="还没有精选内容" detail="先建立频道，定义边界，再添加值得关注的信息。" action={<Button onClick={() => open('channel')}>新建频道</Button>} />}
      <Button onClick={() => open('intelligence')} className="full-width">＋ 添加情报</Button>
    </Panel>
    <Panel className="intelligence-detail">{selected ? <><div className="detail-title"><div><span className="overline">{channel?.name || 'INTELLIGENCE'} · {selected.source}</span><h2>{selected.title}</h2><small>{selected.published_at ? `发布于 ${dateLabel(selected.published_at)}` : '发布时间未知'} · 收录于 {dateLabel(selected.fetched_at || selected.created_at)}</small></div></div>
      <div className="article-cover" aria-hidden="true">✧</div>
      {selected.source_kind === 'workbuddy' && <div className="detail-section"><h3>WorkBuddy 来源</h3><p>原会话状态：{selected.source_status} · 更新于 {dateLabel(selected.source_updated_at)}</p><FieldPath value={selected.source_path} />{selected.content_incomplete && <p className="notice">正文有截断或不可解析片段，请在 WorkBuddy 中核对原会话。</p>}<details><summary>查看会话文本</summary><pre className="knowledge-preview">{selected.content}</pre></details></div>}<div className="detail-section"><h3>摘要 / 最近回复</h3><p>{selected.summary || '暂无摘要。'}</p></div><div className="detail-section"><h3>为什么与你有关</h3><p>{selected.why_recommended}</p></div><div className="detail-section"><h3>关联项目</h3><p>{project?.name || '尚未关联'}</p></div>
      {selected.url && <div className="detail-section"><h3>来源</h3><a href={selected.url} target="_blank" rel="noopener noreferrer">打开原始来源 ↗</a></div>}
      <div className="detail-actions wrap"><Button onClick={() => run('feedback_intelligence', { id: selected.id, feedback: 'ignore' })}>忽略</Button><Button onClick={() => run('feedback_intelligence', { id: selected.id, feedback: 'save' })}>{selected.feedback === 'save' ? '已收藏' : '收藏'}</Button><Button onClick={() => run('research_intelligence', { id: selected.id })}>深入研究</Button><Button onClick={() => run('propose_intelligence_knowledge', { id: selected.id })}>提出知识沉淀</Button><Button variant="primary" onClick={() => run('create_todo', { title: `研究：${selected.title}`.slice(0, 200), note: `来源：${selected.source}\n${selected.source_path || selected.url || ''}\n\n${selected.summary || ''}`.slice(0, 2000) })}>加入待办</Button></div>
    </> : <Empty title="选择一条情报" detail="推荐原因和来源会在此呈现。" />}</Panel>
  </div></div>
}

function FieldPath({ value }) { return <label className="field">原始会话文件<input readOnly value={value || ''} /></label> }
