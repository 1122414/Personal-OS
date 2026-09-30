import React, { useEffect, useMemo, useRef, useState } from 'react'
import useWorkspaceData from './useWorkspaceData.js'
import { Button, Field, Icon, Modal, NAV } from './ui.jsx'
import Home from './pages/Home.jsx'
import Tasks from './pages/Tasks.jsx'
import Todos from './pages/Todos.jsx'
import Projects from './pages/Projects.jsx'
import Intelligence from './pages/Intelligence.jsx'
import Review from './pages/Review.jsx'
import History from './pages/History.jsx'
import Settings from './pages/Settings.jsx'
import Records from './pages/Records.jsx'
import Learning from './pages/Learning.jsx'
import { StateChip } from './PersonalState.jsx'
import TodoReminder from './TodoReminder.jsx'

function themeByTime() {
  const hour = new Date().getHours()
  return hour >= 10 && hour < 14 ? 'morning' : hour >= 14 && hour < 20 ? 'afternoon' : 'night'
}

function initialPage() {
  const key = window.location.hash.slice(1).split('/')[0]
  return key in pageTitles ? key : 'today'
}

const pageTitles = {
  today: '早上好', records: '记录', todos: '待办', learning: '学习', tasks: 'Agent 任务', projects: '项目', intelligence: 'AI 日报',
  review: '审核', history: '工作日报', settings: '设置',
}

function greeting() {
  const hour = new Date().getHours()
  return hour >= 6 && hour < 12 ? '早上好' : hour >= 12 && hour < 18 ? '下午好' : '晚上好'
}

function useClock() {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 60_000); return () => clearInterval(id) }, [])
  return now
}

function FormModal({ modal, data, run, close }) {
  const item = modal.value || {}
  const kind = modal.kind
  const editing = kind.endsWith('-edit')
  const names = {
    task: '新建 Agent 任务', 'task-edit': '编辑 Agent 任务', 'todo-edit': '编辑待办', project: '新建项目', 'project-edit': '编辑项目',
    decision: '记录决策', 'decision-edit': '编辑决策', pulse: '编辑项目脉搏',
    'log-edit': '修改日报', channel: '新建频道', 'channel-edit': '编辑频道', intelligence: '添加情报',
    rule: '新建规则', 'rule-edit': '编辑规则', knowledge: '提出知识沉淀',
    'knowledge-edit': '修改并写入 Obsidian',
  }

  const agentProjects = data.projects.filter(project => project.workspace_path && project.status !== 'Completed')

  async function submit(event) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget).entries())
    const dispatch = event.nativeEvent.submitter?.value === 'dispatch'
    let operation
    let payload = values
    if (kind === 'task' || kind === 'task-edit') {
      operation = editing ? 'update_task' : 'create_task'
      payload = editing ? { ...values, id: item.id } : { ...values, intelligence_id: item.intelligence_id || null, record_id: item.record_id || null }
    } else if (kind === 'todo-edit') {
      operation = 'update_todo'; payload = { id: item.id, title: values.title, note: values.note, project_id: values.project_id || null, priority: values.priority }
    } else if (kind === 'project' || kind === 'project-edit') {
      operation = editing ? 'update_project' : 'create_project'
      if (editing) payload.id = item.id
    } else if (kind === 'decision' || kind === 'decision-edit') {
      operation = editing ? 'update_decision' : 'create_decision'
      if (editing) payload.id = item.id
      if (!payload.project_id) delete payload.project_id
    } else if (kind === 'pulse') {
      operation = 'update_project'; payload = { id: item.id, pulse: values.pulse }
    } else if (kind === 'log-edit') {
      operation = 'update_log'; payload.id = item.id; payload.source_event_ids = item.latest_source_event_ids || []; payload.acknowledge_events = values.acknowledge_events === 'on'
    } else if (kind === 'channel' || kind === 'channel-edit') {
      operation = editing ? 'update_channel' : 'create_channel'; if (editing) payload.id = item.id
    } else if (kind === 'intelligence') {
      operation = 'create_intelligence'; payload.project_id ||= null
    } else if (kind === 'rule' || kind === 'rule-edit') {
      operation = editing ? 'update_rule' : 'create_rule'; if (editing) payload.id = item.id
    } else if (kind === 'knowledge') {
      operation = 'propose_knowledge'; payload.task_id = item.id
    } else if (kind === 'knowledge-edit') {
      operation = 'approve_knowledge'; payload = { ...values, id: item.id, choice: 'write' }
    }
    const result = await run(operation, payload)
    if (result && dispatch) await run('start_agent', { task_id: result.id, runtime: result.runtime })
    if (result) close()
  }

  return <Modal title={names[kind] || kind} onClose={close}><form onSubmit={submit} className="form-grid">
    {(kind === 'task' || kind === 'task-edit') && <>
      <Field label="任务标题"><input name="title" defaultValue={item.title || ''} required autoFocus maxLength={200} /></Field>
      <Field label="要求与完成标准（Agent 会照着这里做和自检）"><textarea name="description" defaultValue={item.description || ''} rows={5} /></Field>
      {agentProjects.length ? <div className="form-columns"><Field label="在哪个项目目录里做"><select name="project_id" defaultValue={agentProjects.some(project => project.id === item.project_id) ? item.project_id : agentProjects[0].id} required disabled={['Running', 'Review'].includes(item.status)}>{agentProjects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></Field><Field label="执行通道"><select name="runtime" defaultValue={item.runtime || (data.runtime?.agents || []).find(agent => agent.available)?.id || 'codex'} required disabled={['Running', 'Review'].includes(item.status)}>{(data.runtime?.agents || []).map(agent => <option key={agent.id} value={agent.id}>{agent.label}{agent.available ? '' : '（本机未找到）'}</option>)}</select></Field></div>
        : <p className="form-hint">还没有设置本地目录的项目。Agent 任务必须在某个项目目录里执行，请先到「项目」里给项目填写本地工作目录。</p>}
      {!editing && <input type="hidden" name="source" value={item.source || 'Manual'} />}
    </>}
    {kind === 'todo-edit' && <>
      <Field label="待办"><input name="title" defaultValue={item.title} required autoFocus maxLength={200} /></Field>
      <Field label="备注"><textarea name="note" defaultValue={item.note || ''} rows={4} maxLength={2000} /></Field>
      <Field label="优先级"><select name="priority" defaultValue={item.priority || 'medium'}><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></Field>
      <Field label="关联项目（可选）"><select name="project_id" defaultValue={item.project_id || ''}><option value="">无</option>{data.projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></Field>
      {item.home_item_note && <p className="muted">来自长线事项：{item.home_item_note}</p>}
      <Button type="button" variant="danger" onClick={async () => { if (window.confirm(`删除待办「${item.title}」？删除后无法恢复。`)) { const result = await run('delete_todo', { id: item.id }); if (result) close() } }}>删除待办</Button>
    </>}
    {(kind === 'project' || kind === 'project-edit') && <><Field label="项目名称"><input name="name" defaultValue={item.name || ''} required autoFocus /></Field><Field label="项目说明"><textarea name="description" rows={3} defaultValue={item.description || ''} /></Field><Field label="当前阶段"><input name="stage" defaultValue={item.stage || '规划中'} /></Field>{editing && <Field label="状态"><select name="status" defaultValue={item.status}><option value="Active">进行中</option><option value="Paused">已暂停</option><option value="Completed">已完成</option></select></Field>}<Field label="本地工作目录（派给 Agent 执行时使用，可选）"><input name="workspace_path" defaultValue={item.workspace_path || ''} placeholder="/path/to/repository" /></Field></>}
    {(kind === 'decision' || kind === 'decision-edit') && <><Field label="决策标题"><input name="title" defaultValue={item.title || ''} required autoFocus /></Field><Field label="决定内容"><textarea name="content" rows={4} defaultValue={item.content || ''} required /></Field><Field label="原因"><textarea name="reason" rows={2} defaultValue={item.reason || ''} /></Field>{!editing && <Field label="所属项目"><select name="project_id" defaultValue={item.project_id || ''}><option value="">无项目</option>{data.projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></Field>}{editing && <Field label="状态"><select name="status" defaultValue={item.status}><option value="Active">有效</option><option value="Superseded">已替代</option><option value="Archived">已归档</option></select></Field>}</>}
    {kind === 'pulse' && <Field label="项目脉搏"><textarea name="pulse" rows={6} defaultValue={item.pulse || ''} required autoFocus /></Field>}
    {kind === 'log-edit' && <><Field label="今日工作记录"><textarea name="summary" rows={12} defaultValue={item.summary} required autoFocus /></Field>{item.stale && <label><input type="checkbox" name="acknowledge_events" required />我已对照当日时间线核对新增事件</label>}</>}
    {(kind === 'channel' || kind === 'channel-edit') && <><Field label="频道名称"><input name="name" defaultValue={item.name || ''} required autoFocus /></Field><Field label="关注边界（关键词）"><textarea name="boundary" rows={3} defaultValue={item.boundary || ''} placeholder="例如：Coding Agent、模型发布、重要论文" /></Field><Field label="RSS/Atom 来源（每行一个网址）"><textarea name="sources" rows={3} defaultValue={item.sources || ''} placeholder="https://example.com/feed.xml" /></Field><Field label="排除关键词"><textarea name="filter_rule" rows={2} defaultValue={item.filter_rule || ''} placeholder="例如：营销文章、广告" /></Field><Field label="每日最多条数"><input name="daily_limit" type="number" min="1" max="50" defaultValue={item.daily_limit || 8} /></Field></>}
    {kind === 'intelligence' && <><Field label="标题"><input name="title" required autoFocus /></Field><div className="form-columns"><Field label="频道"><select name="channel_id" required><option value="">选择频道</option>{data.intelligence_channels.map(channel => <option key={channel.id} value={channel.id}>{channel.name}</option>)}</select></Field><Field label="来源"><input name="source" required /></Field></div><Field label="来源链接"><input name="url" type="url" placeholder="https://" /></Field><Field label="摘要"><textarea name="summary" rows={3} /></Field><Field label="为什么与你有关"><textarea name="why_recommended" rows={3} required /></Field><Field label="关联项目"><select name="project_id"><option value="">无项目</option>{data.projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></Field></>}
    {(kind === 'rule' || kind === 'rule-edit') && <><Field label="规则内容"><textarea name="text" rows={3} defaultValue={item.text || ''} required autoFocus /></Field>{!editing && <Field label="类别"><select name="category"><option value="Daily Log">Daily Log</option><option value="Agent">Agent</option><option value="Intelligence">Intelligence</option><option value="General">General</option></select></Field>}{editing && <Button type="button" variant="danger" onClick={async () => { if (window.confirm('删除这条规则？')) { const result = await run('delete_rule', { id: item.id }); if (result) close() } }}>删除规则</Button>}</>}
    {kind === 'knowledge' && <><Field label="知识标题"><input name="title" defaultValue={item.title || ''} required autoFocus /></Field><Field label="拟保存内容"><textarea name="content" rows={8} defaultValue={item.result || item.description || ''} required /></Field></>}
    {kind === 'knowledge-edit' && <><Field label="知识标题"><input name="title" defaultValue={item.title} required autoFocus /></Field><Field label="写入内容"><textarea name="content" rows={10} defaultValue={item.content} required /></Field></>}
    {kind === 'task' ? <div className="modal-actions"><Button type="button" onClick={close}>取消</Button><Button type="submit" value="create" disabled={!agentProjects.length}>创建</Button><Button type="submit" value="dispatch" variant="primary" disabled={!agentProjects.length}>创建并派出</Button></div>
      : <div className="modal-actions"><Button type="button" onClick={close}>取消</Button><Button type="submit" variant="primary">{kind === 'knowledge-edit' ? '确认写入' : editing ? '保存修改' : '确认'}</Button></div>}
  </form></Modal>
}

export default function App() {
  const [page, setPage] = useState(initialPage)
  const [focus, setFocus] = useState(() => window.location.hash.split('/')[1] || null)
  const [modal, setModal] = useState(null)
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState(null)
  const { data, pending, loading, refresh, mutate } = useWorkspaceData(setNotice)
  const [previewTransparency, setPreviewTransparency] = useState(null)
  const content = useRef(null)
  useEffect(() => { content.current?.scrollTo(0, 0) }, [page, focus])
  useClock()
  useEffect(() => {
    if (!notice?.message) return
    const timer = setTimeout(() => setNotice(null), 3000)
    return () => clearTimeout(timer)
  }, [notice])
  useEffect(() => { const handler = () => { setPage(initialPage()); setFocus(window.location.hash.split('/')[1] || null) }; window.addEventListener('hashchange', handler); return () => window.removeEventListener('hashchange', handler) }, [])
  useEffect(() => { const handler = event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); document.getElementById('global-command')?.focus() } if (event.key === 'Escape') { setModal(null); setSearch('') } }; window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler) }, [])
  const settings = data?.settings || { theme_mode: 'auto', manual_theme: 'morning', nickname: '博士' }
  const theme = settings.theme_mode === 'manual' ? settings.manual_theme : themeByTime()
  const nickname = settings.nickname?.trim()

  function navigate(next, id = null) { setPage(next); setFocus(id?.split('/')[0] || null); window.location.hash = id ? `${next}/${id}` : next; setSearch('') }
  function open(kind, value) { setModal({ kind, value }); setSearch('') }
  async function run(name, payload, { quiet = false } = {}) {
    try {
      const response = await mutate(name, payload)
      const errors = response.result?.errors
      const warnings = []
      if (errors?.length) warnings.push(`新增 ${response.result.added || 0} 条；${errors.length} 个来源失败：${errors.map(item => item.error).join('；')}`)
      if (response.refreshError) warnings.push('操作已完成，但界面刷新失败；请稍后刷新，无需重复提交。')
      if (warnings.length) {
        setNotice({ error: warnings.join('；') })
      } else if (!quiet) {
        setNotice({ message: response.result?.message || (name === 'refresh_channel' ? (response.result.reason || `已新增 ${response.result.added} 条`) : '已保存') })
      }
      return response.result
    } catch (error) {
      if (quiet) throw error
      setNotice({ error: error.message })
      return null
    }
  }

  async function addTodo() {
    if (search.trim() && await run('create_todo', { title: search.slice(0, 200) })) { setSearch(''); navigate('todos') }
  }

  const matches = useMemo(() => !search.trim() || !data ? [] : [
    ...(data.records || []).filter(item => `${item.title} ${item.content}`.toLowerCase().includes(search.toLowerCase())).slice(0, 4).map(item => ({ ...item, page: 'records', label: '记录' })),
    ...(data.learning_topics || []).filter(item => `${item.title} ${item.goal}`.toLowerCase().includes(search.toLowerCase())).slice(0, 3).map(item => ({ ...item, page: 'learning', label: '学习' })),
    ...data.todos.filter(item => !item.archived_at && item.title.toLowerCase().includes(search.toLowerCase())).slice(0, 4).map(item => ({ ...item, page: 'todos', label: '待办' })),
    ...data.tasks.filter(item => item.title.toLowerCase().includes(search.toLowerCase())).slice(0, 4).map(item => ({ ...item, page: 'tasks', label: 'Agent 任务' })),
    ...data.projects.filter(item => item.name.toLowerCase().includes(search.toLowerCase())).slice(0, 3).map(item => ({ ...item, page: 'projects', title: item.name, label: '项目' })),
  ], [search, data])

  const transparency = previewTransparency ?? settings.theme_transparency ?? 8
  return <div className={`app-shell theme-${theme} ${page === 'today' ? 'workspace-home' : ''} ${page === 'learning' && focus ? 'workspace-topic' : ''}`} style={{ '--surface-alpha': (100 - transparency) / 100 }}>
    <aside className="sidebar"><div className="brand"><div className="brand-mark">♆</div><div><strong>Personal OS</strong><small>ABYSS CALLS · BUT ALSO HEALS</small></div></div><nav aria-label="主导航">{NAV.map(([key, label, english]) => <button key={key} aria-label={label} className={`nav-item ${page === key ? 'active' : ''} ${key === 'settings' ? 'settings-nav' : ''}`} onClick={() => navigate(key)}><span className="nav-icon"><Icon name={key} /></span><span>{label}<small>{english}</small></span></button>)}</nav><div className="sidebar-quote"><span>✧</span><p>在混沌中，仍然前行。</p><small>PERSONAL OS · A MORE FOCUSED YOU</small></div></aside>
    <div className="main-area"><header className="topbar"><div className="command-wrap"><label className="command-bar"><span>⌕</span><input id="global-command" value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); if (matches[0]) navigate(matches[0].page, matches[0].id); else addTodo() } }} placeholder="搜索记录、待办、任务…" /><kbd>⌘ K</kbd></label>{search && <div className="search-popover">{matches.map(item => <button key={item.id} onClick={() => navigate(item.page, item.id)}><small>{item.label}</small>{item.title}</button>)}<button onClick={addTodo}><small>新建</small>加入待办：{search}</button></div>}</div><div className="topbar-right"><span className="topbar-theme">{theme === 'morning' ? '☼' : theme === 'afternoon' ? '✦' : '☾'}</span><button className="avatar" onClick={() => navigate('settings')} aria-label="打开设置">✧</button><span className="topbar-name">{nickname || 'Personal OS'}</span></div></header>
      <div className="hero"><div className="hero-copy"><span className="hero-kicker">{page === 'today' ? '' : page.toUpperCase()}</span><div className="hero-line"><h1>{page === 'today' ? <>{greeting()}{nickname ? `，${nickname}` : ''}。</> : pageTitles[page]}</h1>{page === 'today' && data && <StateChip data={data} run={run} />}</div><p>{page === 'today' ? '先记下来，再继续一件重要的事。' : '让每一步工作都有来处，也有归处。'}</p></div></div>
      <main className="content" ref={content}>{loading ? <div className="loading">正在读取工作空间…</div> : !data ? <div className="loading">无法连接本地服务。请启动 Python API。</div> : <>
        {page === 'today' && <Home data={data} run={run} open={open} navigate={navigate} refresh={refresh} />}
        {page === 'records' && <Records data={data} run={run} focus={focus} navigate={navigate} open={open} />}
        {page === 'learning' && <Learning data={data} run={run} focus={focus} navigate={navigate} />}
        {page === 'todos' && <Todos data={data} run={run} open={open} />}
        {page === 'tasks' && <Tasks data={data} run={run} open={open} focus={focus} navigate={navigate} />}
        {page === 'projects' && <Projects data={data} run={run} open={open} focus={focus} navigate={navigate} />}
        {page === 'intelligence' && <Intelligence data={data} run={run} open={open} focus={focus} refresh={refresh} navigate={navigate} />}
        {page === 'review' && <Review data={data} run={run} open={open} focus={focus} navigate={navigate} />}
        {page === 'history' && <History data={data} run={run} open={open} />}
        {page === 'settings' && <Settings data={data} run={run} open={open} theme={theme} previewTransparency={setPreviewTransparency} />}
      </>}</main>
    </div>
    {notice && <div className={`toast ${notice.error ? 'error' : ''}`} role="status">{notice.error || notice.message}<button onClick={() => setNotice(null)} aria-label="关闭通知">×</button></div>}
    {pending && <div className="pending-indicator" role="status">{['generate_brief','generate_project_pulse','summarize_log','generate_cards'].includes(pending) ? '正在整理上下文并生成内容…' : ['refresh_channel','sync_workbuddy'].includes(pending) ? '正在读取信息来源…' : '正在保存…'}</div>}
    {modal && data && <FormModal modal={modal} data={data} run={run} close={() => setModal(null)} />}
    {data && !modal && <TodoReminder data={data} run={run} navigate={navigate} />}
  </div>
}
