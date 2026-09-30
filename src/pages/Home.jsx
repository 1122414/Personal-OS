import React, { useState } from 'react'
import { Modal, Panel, taskState } from '../ui.jsx'
import { Capture } from '../workspace.jsx'
import { RecallCard } from '../PersonalState.jsx'
import { HomeItems, RepoOnboarding } from '../HomePanels.jsx'
import { TodayCards } from '../learning/Cards.jsx'
import TodayPlan from './Today.jsx'

function Attention({ data, navigate }) {
  const replying = data.tasks.filter(task => taskState(task, data.agent_runs) === 'Reply')
  const waiting = data.tasks.filter(task => taskState(task, data.agent_runs) === 'Review')
  const blocked = data.tasks.filter(task => task.status === 'Blocked' && !task.archived_at)
  const running = data.agent_runs.filter(run => run.status === 'Running')
  if (!replying.length && !waiting.length && !blocked.length && !running.length) return null
  return <div className="attention-bar" role="status">
    {replying.length > 0 && <button onClick={() => navigate('tasks', replying[0].id)}>{replying.length} 个 Agent 等你回复 →</button>}
    {waiting.length > 0 && <button onClick={() => navigate('tasks', waiting[0].id)}>{waiting.length} 个 Agent 任务待验收 →</button>}
    {blocked.length > 0 && <button onClick={() => navigate('tasks', blocked[0].id)}>{blocked.length} 个 Agent 任务失败或取消 →</button>}
    {running.length > 0 && <span>{running.length} 个 Agent 正在执行</span>}
  </div>
}

function ReportDigest({ index, today, navigate }) {
  const modules = index.modules || []
  const [folder, setFolder] = useState(null)
  const module = modules.find(item => item.folder === folder) || modules[0]
  const summary = (index.summaries || []).find(item => item.folder === module?.folder)
  return <div className="report-digest">
    <div className="digest-head"><span className="overline">日报{summary ? ` · ${summary.date === today ? '今天' : summary.date}` : ''}</span>
      <div className="tabs compact">{modules.map(item => <button key={item.folder} className={item.folder === module?.folder ? 'active' : ''} onClick={() => setFolder(item.folder)}>{item.name}</button>)}</div></div>
    {summary ? <>
      <button className="strip-title" onClick={() => navigate('intelligence', summary.id)}>{summary.title}</button>
      {summary.items.length > 0 && <ul className="digest-items">{summary.items.map((item, index) => <li key={index}>{item}</li>)}</ul>}
      <button className="text-link" onClick={() => navigate('intelligence', summary.id)}>阅读全文 →</button>
    </> : <span className="muted">尚未发现{module?.name}报告</span>}
  </div>
}

function HomeStrip({ data, run, navigate }) {
  const [recall, setRecall] = useState(false)
  const index = data.daily_reports || { reports: [], modules: [], configured: false }
  const review = data.weekly_review?.items || []
  return <Panel className="home-strip">
    {index.configured ? <ReportDigest index={index} today={data.today} navigate={navigate} />
      : <div className="strip-row"><span className="overline">日报</span><span className="muted">尚未配置报告目录</span><button className="text-link" onClick={() => navigate('settings')}>检查来源 →</button></div>}
    {review.length > 0 && <div className="strip-row"><span className="overline">回想</span><button className="strip-title" onClick={() => setRecall(true)}>本周想起 {review.length} 条点子 →</button></div>}
    {recall && <Modal title="本周，想起这些点子" onClose={() => setRecall(false)}>{review.map(item => <RecallCard key={item.record_id} item={item} record={item.record} topicTitle={item.topic_title} run={run} />)}</Modal>}
  </Panel>
}

export default function Home({ data, run, open, navigate, refresh }) {
  return <div className="page home-page"><div className="home-scroll">
    <Panel className="home-capture"><Capture compact run={run} /></Panel>
    <Attention data={data} navigate={navigate} />
    <div className={`home-grid ${data.projects.length ? 'no-last' : ''}`}>
      <TodayPlan data={data} run={run} open={open} navigate={navigate} />
      {data.projects.length === 0 && <RepoOnboarding run={run} />}
      <div className="home-side">
        <TodayCards data={data} run={run} navigate={navigate} />
        <HomeItems data={data} run={run} refresh={refresh} navigate={navigate} />
        <HomeStrip data={data} run={run} navigate={navigate} />
      </div>
    </div>
  </div></div>
}
