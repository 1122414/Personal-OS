import React, { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { action } from './api.js'
import { Button, Empty, Modal, Panel, dateLabel, timeLabel } from './ui.jsx'

const HOME_STATUS = { active: '进行中', paused: '已暂停', done: '已完成' }

function fileName(path) {
  return (path || '').split('/').pop()
}

function SessionRow({ item, onReveal }) {
  return <li className="trace-row" title={item.ref}>
    <span className="trace-kind">{item.label}</span>
    <div><strong>{item.title}</strong>{item.last_text && <p>停在：{item.last_text}</p>}<small>{timeLabel(item.at)}{item.source !== 'workbuddy' && <> · <button className="trace-source" title="在访达中显示" onClick={() => onReveal(item)}>{fileName(item.ref)}</button></>}</small></div>
  </li>
}

function CommitDetail({ commit, onClose }) {
  return createPortal(<Modal title={commit.subject} onClose={onClose}>
    <p className="muted">{commit.project} · {commit.author} · {dateLabel(commit.at)} {timeLabel(commit.at)} · {commit.hash.slice(0, 7)}</p>
    {commit.body && <p className="commit-body">{commit.body}</p>}
    <pre className="commit-stat">{commit.stat || '没有文件改动'}</pre>
  </Modal>, document.querySelector('.app-shell') || document.body)
}

export function LastWork({ data, run }) {
  const work = data.last_work
  const sync = data.trace_sync || {}
  const [commit, setCommit] = useState(null)
  const [sourceError, setSourceError] = useState('')
  const open = async (name, item) => {
    setSourceError('')
    try {
      const { result } = await action(name, { id: item.id })
      if (name === 'show_commit') setCommit(result)
    } catch (error) {
      setSourceError(error.message)
    }
  }
  const reveal = item => open('reveal_trace_source', item)
  const tools = <span className="panel-tools">{work && <span className="overline">{dateLabel(work.date)}</span>}<button className="text-link" onClick={() => run('sync_traces', {})}>刷新</button></span>
  if (!work) return <Panel title="上次工作" action={tools} className="last-work">
    <Empty title={data.projects.length ? '还没有读到工作痕迹' : '登记项目后，这里会出现上次做了什么'} detail="来自已登记项目的 git 提交，以及 Cursor、Codex、WorkBuddy 的会话。" />
  </Panel>
  return <Panel title="上次工作" action={tools} className="last-work"><div className="trace-list">
    {work.groups.map((group, index) => <details key={group.project_id || 'none'} open={index < 2} className="trace-group">
      <summary><strong>{group.name}</strong><small>{[group.commits.length && `${group.commits.length} 次提交`, group.sessions.length && `${group.sessions.length} 段会话`, group.tasks.length && `完成 ${group.tasks.length} 项任务`].filter(Boolean).join(' · ')}</small></summary>
      <ul>
        {group.tasks.map(item => <li className="trace-row" key={item.id}><span className="trace-kind">任务</span><div><strong>{item.title}</strong><small>{timeLabel(item.at)}</small></div></li>)}
        {group.sessions.map(item => <SessionRow key={item.id} item={item} onReveal={reveal} />)}
        {group.commits.map(item => <li className="trace-row" key={item.id} title={item.ref}><span className="trace-kind">提交</span><div><strong>{item.title}</strong><small>{timeLabel(item.at)} · <button className="trace-source" title="查看提交内容" onClick={() => open('show_commit', item)}>{item.ref?.slice(0, 7)}</button></small></div></li>)}
      </ul>
    </details>)}
    {work.unassigned_sessions.length > 0 && <details className="trace-group"><summary><strong>其他会话</strong><small>{work.unassigned_sessions.length} 段 · 未归到已登记项目</small></summary><ul>{work.unassigned_sessions.map(item => <SessionRow key={item.id} item={item} onReveal={reveal} />)}</ul></details>}
    {sync.error_count > 0 && <p className="muted">最近一次同步有 {sync.error_count} 个来源未读完：{sync.errors?.[0]?.error}</p>}
    {sourceError && <p className="muted" role="alert">{sourceError}</p>}
    {commit && <CommitDetail commit={commit} onClose={() => setCommit(null)} />}
  </div></Panel>
}

export function RepoOnboarding({ run }) {
  const [state, setState] = useState({ loading: true, candidates: [], root: '' })
  const [picked, setPicked] = useState([])
  useEffect(() => {
    action('list_repo_candidates', {}).then(({ result }) => {
      setState({ loading: false, candidates: result.candidates, root: result.root, message: result.message })
      setPicked(result.candidates.map(item => item.path))
    }).catch(error => setState({ loading: false, candidates: [], root: '', message: error.message }))
  }, [])
  const toggle = path => setPicked(current => current.includes(path) ? current.filter(item => item !== path) : [...current, path])
  return <Panel title="先登记正在做的项目" className="repo-onboarding" action={<small>{state.root}</small>}>
    <p className="muted">下面是最近 30 天有提交的仓库。登记后，首页会从这些项目读取提交和会话；未登记的仓库不会被读取。</p>
    {state.loading ? <p className="muted">正在查找仓库…</p> : state.candidates.length ? <div className="repo-list panel-body">{state.candidates.map(item => <label key={item.path} className="repo-option"><input type="checkbox" checked={picked.includes(item.path)} onChange={() => toggle(item.path)} /><span><strong>{item.name}</strong><small>{item.commits} 次提交 · 最近 {dateLabel(item.last_commit_at)}</small></span></label>)}</div> : <p className="muted">{state.message || '没有找到最近有提交的仓库，可以在设置中修改扫描目录，或在项目页手动创建。'}</p>}
    <div className="brief-actions"><Button variant="primary" disabled={!picked.length} onClick={() => run('register_projects', { paths: picked })}>登记所选项目</Button></div>
  </Panel>
}

function HomeField({ item, field, label, run, refresh }) {
  const [value, setValue] = useState(item[field] || '')
  async function save() {
    if (value.trim() === (item[field] || '')) return
    const result = await run('update_home_item', { note: item.note, field, value, expected_version: item.version, title: item.title })
    if (!result) { await refresh(); setValue(item[field] || '') }
  }
  return <label className="home-field"><span>{label}</span><input value={value} maxLength={500} placeholder="点击填写" onChange={event => setValue(event.target.value)} onBlur={save} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur(); if (event.key === 'Escape') { setValue(item[field] || ''); event.currentTarget.blur() } }} disabled={!item.version} /></label>
}

export function HomeItems({ data, run, refresh, navigate }) {
  const home = data.home_items || { configured: false, items: [], errors: [] }
  if (!home.configured) return <Panel title="长线事项" className="home-items"><Empty title="读取 Obsidian 首页的事项" detail={home.errors[0] || '在设置中配置 Obsidian vault 后显示。'} action={<Button onClick={() => navigate('settings')}>打开设置</Button>} /></Panel>
  const current = home.items.filter(item => item.home_status !== 'done')
  const finished = home.items.length - current.length
  return <Panel title="长线事项" action={<small>{finished ? `已完成 ${finished} 项 · ` : ''}以 Obsidian 为准</small>} className="home-items">
    <div className="panel-body">{current.length ? current.map(item => <article className="home-item" key={`${item.id}-${item.version}`}>
      <div className="home-item-heading"><strong>{item.title}</strong><select aria-label={`${item.title}状态`} value={item.home_status} disabled={!item.version} onChange={async event => { if (!await run('update_home_item', { note: item.note, field: 'home_status', value: event.target.value, expected_version: item.version, title: item.title })) refresh() }}>{Object.entries(HOME_STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
      {item.error ? <p className="notice">{item.error}</p> : <><HomeField item={item} field="home_progress" label="当前进度" run={run} refresh={refresh} /><HomeField item={item} field="home_next" label="下一步" run={run} refresh={refresh} /></>}
    </article>) : <p className="muted">所有事项都已完成。</p>}</div>
  </Panel>
}
