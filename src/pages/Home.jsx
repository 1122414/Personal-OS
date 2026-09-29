import React from 'react'
import { Button, Empty, Panel } from '../ui.jsx'
import { Capture } from '../workspace.jsx'
import PersonalState, { RecallCard } from '../PersonalState.jsx'
import { HomeItems, LastWork, RepoOnboarding } from '../HomePanels.jsx'
import TodayPlan from './Today.jsx'

function Attention({ data, navigate }) {
  const waiting = data.tasks.filter(task => task.status === 'Review')
  const blocked = data.tasks.filter(task => task.status === 'Blocked' && !task.archived_at)
  const running = data.agent_runs.filter(run => run.status === 'Running')
  if (!waiting.length && !blocked.length && !running.length) return null
  return <div className="attention-bar" role="status">
    {waiting.length > 0 && <button onClick={() => navigate('review', waiting[0].id)}>{waiting.length} 个结果等待审核 →</button>}
    {blocked.length > 0 && <button onClick={() => navigate('tasks', blocked[0].id)}>{blocked.length} 个任务阻塞 →</button>}
    {running.length > 0 && <span>{running.length} 个 Agent 正在执行</span>}
  </div>
}

function DailyReportPanel({ data, navigate }) {
  const reports = data.daily_reports?.reports.filter(item => item.date === data.daily_reports.latest_date).slice(0, 4) || []
  return <Panel title="AI 日报" action={<button className="text-link" onClick={() => navigate('intelligence')}>阅读全文 →</button>}>
    {reports.length ? <><p className="muted">{data.daily_reports.latest_date === data.today ? '今日报告' : `今天尚未发布 · 最新 ${data.daily_reports.latest_date}`}</p>{reports.map(item => <button className="mini-row" key={item.id} onClick={() => navigate('intelligence', item.id)}><span className="small-symbol">▤</span><span>{item.title}</span></button>)}</> : <Empty title="尚未发现 AI 日报" detail="读取 Obsidian 日报目录中的成品报告。" action={<Button onClick={() => navigate('settings')}>检查来源</Button>} />}
  </Panel>
}

export default function Home({ data, run, open, navigate, refresh }) {
  const review = data.weekly_review?.items || []
  return <div className="page home-page"><div className="home-scroll">
    <Panel className="home-capture"><Capture compact run={run} /></Panel>
    <Attention data={data} navigate={navigate} />
    {data.projects.length === 0 && <RepoOnboarding run={run} />}
    <div className="home-grid">
      <LastWork data={data} run={run} />
      <HomeItems data={data} run={run} refresh={refresh} navigate={navigate} />
      <TodayPlan data={data} run={run} open={open} navigate={navigate} />
      <DailyReportPanel data={data} navigate={navigate} />
    </div>
    <div className="home-extras">
      {review.length > 0 && <Panel title="本周，想起这些点子" action={<small>{review.length} 条</small>}>{review.map(item => <RecallCard key={item.record_id} item={item} record={item.record} topicTitle={item.topic_title} run={run} />)}</Panel>}
      <Panel className="home-states"><details><summary>近期状态</summary><PersonalState data={data} run={run} /></details></Panel>
    </div>
  </div></div>
}
