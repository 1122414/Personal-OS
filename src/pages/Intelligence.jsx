import React, { useEffect, useState } from 'react'
import { Button, Empty, Panel, dateLabel } from '../ui.jsx'

export default function Intelligence({ data, run, open, focus }) {
  const [channelId, setChannel] = useState('all')
  const [selectedId, select] = useState(focus || null)
  useEffect(() => { if (focus) select(focus) }, [focus])
  const items = data.intelligence_items.filter(item => item.feedback !== 'ignore' && (channelId === 'all' || item.channel_id === channelId))
  const selected = items.find(item => item.id === selectedId) || items[0]
  const channel = data.intelligence_channels.find(item => item.id === selected?.channel_id)
  const project = data.projects.find(item => item.id === selected?.project_id)

  return <div className="page intelligence-page"><div className="intelligence-layout">
    <Panel className="channel-rail" title="频道" action={<button className="icon-button" onClick={() => open('channel')} title="新建频道">＋</button>}><button className={`channel-option ${channelId === 'all' ? 'selected' : ''}`} onClick={() => setChannel('all')}>✦ <span>为你推荐</span></button>{data.intelligence_channels.map(item => <button className={`channel-option ${channelId === item.id ? 'selected' : ''}`} onClick={() => setChannel(item.id)} key={item.id}>◎ <span>{item.name}</span></button>)}<Button className="channel-add" onClick={() => open('channel')}>＋ 新建频道</Button>{channelId !== 'all' && <div className="channel-tools"><Button onClick={() => open('channel-edit', data.intelligence_channels.find(item => item.id === channelId))}>编辑边界</Button><Button onClick={() => run('refresh_channel', { id: channelId })}>刷新来源</Button></div>}</Panel>
    <Panel className="intelligence-list" title="今日精选" action={<span className="overline">{items.length} 条</span>}>
      {items.length ? items.map(item => <button key={item.id} className={`intelligence-card ${selected?.id === item.id ? 'selected' : ''}`} onClick={() => { select(item.id); if (item.feedback === 'unread') run('feedback_intelligence', { id: item.id, feedback: 'read' }) }}><span className="article-image">✧</span><span><strong>{item.title}</strong><p>{item.summary || item.why_recommended}</p><small>{item.source} · {dateLabel(item.published_at)}</small></span></button>) : <Empty title="还没有精选内容" detail="先建立频道，定义边界，再添加值得关注的信息。" action={<Button onClick={() => open('channel')}>新建频道</Button>} />}
      <Button onClick={() => open('intelligence')} className="full-width">＋ 添加情报</Button>
    </Panel>
    <Panel className="intelligence-detail">{selected ? <><div className="detail-title"><div><span className="overline">{channel?.name || 'INTELLIGENCE'} · {selected.source}</span><h2>{selected.title}</h2><small>{dateLabel(selected.published_at)}</small></div></div>
      <div className="article-cover" aria-hidden="true">✧</div>
      <div className="detail-section"><h3>摘要</h3><p>{selected.summary || '暂无摘要。'}</p></div><div className="detail-section"><h3>为什么与你有关</h3><p>{selected.why_recommended}</p></div><div className="detail-section"><h3>关联项目</h3><p>{project?.name || '尚未关联'}</p></div>
      {selected.url && <div className="detail-section"><h3>来源</h3><a href={selected.url} target="_blank" rel="noopener noreferrer">打开原始来源 ↗</a></div>}
      <div className="detail-actions wrap"><Button onClick={() => run('feedback_intelligence', { id: selected.id, feedback: 'ignore' })}>忽略</Button><Button onClick={() => run('feedback_intelligence', { id: selected.id, feedback: 'save' })}>{selected.feedback === 'save' ? '已收藏' : '收藏'}</Button><Button onClick={() => run('research_intelligence', { id: selected.id })}>深入研究</Button><Button variant="primary" onClick={() => open('task', { title: `研究：${selected.title}`, source: 'Intelligence', project_id: selected.project_id })}>创建任务</Button></div>
    </> : <Empty title="选择一条情报" detail="推荐原因和来源会在此呈现。" />}</Panel>
  </div></div>
}
