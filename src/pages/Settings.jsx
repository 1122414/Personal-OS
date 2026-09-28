import React, { useEffect, useState } from 'react'
import { Button, Empty, Field, Panel } from '../ui.jsx'

const themes = [['morning', '潮汐圣域', '10:00–14:00'], ['afternoon', '赤色剧场', '14:00–20:00'], ['night', '深海回响', '其余时间']]

export default function Settings({ data, run, open, theme }) {
  const [form, setForm] = useState({ ...data.settings })
  const [obsidian, setObsidian] = useState(null)
  const [backupId, setBackupId] = useState('')
  const [savedPath, setSavedPath] = useState('')
  const [restoreAccepted, setRestoreAccepted] = useState(false)
  useEffect(() => { setForm({ ...data.settings }) }, [data.settings.updated_at])
  useEffect(() => { fetch('/api/obsidian/recent').then(response => response.json()).then(setObsidian).catch(() => setObsidian(null)) }, [data.settings.obsidian_vault])
  const update = (key, value) => setForm(previous => ({ ...previous, [key]: value }))
  return <div className="page settings-page"><div className="settings-grid">
    <Panel title="外观主题" className="appearance-panel"><div className="skin-banner"><div className="skin-avatar">✧</div><div><strong>当前个性化主题：浊心斯卡蒂</strong><p>角色主题和称呼可以根据个人偏好配置，Personal OS 的工作流程保持一致。</p></div></div>
      <Field label="我的称呼（可选）"><input value={form.nickname || ''} onChange={event => update('nickname', event.target.value)} placeholder="例如：博士" /></Field>
      <label className="switch-row"><span><strong>自动随时间切换主题</strong><small>按照晨间、午后、夜间时段选择视觉主题。</small></span><input type="checkbox" checked={form.theme_mode === 'auto'} onChange={event => update('theme_mode', event.target.checked ? 'auto' : 'manual')} /></label>
      <div className="theme-options">{themes.map(([key, name, hours]) => <button key={key} className={`theme-option ${theme === key ? 'selected' : ''}`} onClick={() => { update('theme_mode', 'manual'); update('manual_theme', key) }}><span className={`theme-preview ${key}`} /><strong>{name}</strong><small>{hours}</small></button>)}</div>
      <div className="settings-actions"><Button variant="primary" onClick={() => run('save_settings', form)}>保存设置</Button></div>
    </Panel>
    <div className="settings-side"><Panel title="个人规则（AI 参考）" action={<button className="text-link" onClick={() => open('rule')}>＋ 新建</button>}>{data.personal_rules.length ? data.personal_rules.map(rule => <div className="rule-row" key={rule.id}><span><strong>{rule.text}</strong><small>{rule.category}</small></span><Button onClick={() => open('rule-edit', rule)}>编辑</Button><input aria-label={`启用 ${rule.text}`} type="checkbox" checked={rule.enabled} onChange={event => run('update_rule', { id: rule.id, enabled: event.target.checked })} /></div>) : <Empty title="还没有个人规则" detail="通过可见、可修改的规则约束日报与建议。" />}</Panel>
      <p className="muted">规则用于 AI 建议与执行上下文，人工完成和情报关键词筛选不会自动强制校验自然语言规则。</p><Panel title="连接器与运行环境"><div className="integration-row"><span className="integration-icon">◈</span><div><strong>Obsidian</strong><small>{obsidian?.configured ? `已连接 · 最近 ${obsidian.files.length} 个文件` : '等待配置 vault 路径'}</small></div></div><Field label="Vault 路径"><input value={form.obsidian_vault || ''} onChange={event => update('obsidian_vault', event.target.value)} placeholder="/path/to/Obsidian" /></Field><div className="integration-row"><span className="integration-icon">◎</span><div><strong>Agent Runtime — Codex</strong><small>任务中选择运行时后，可执行并回传审核。</small></div></div></Panel>
      <Panel title="数据备份与恢复"><p className="muted">备份本地数据库；不包含项目文件或 Obsidian 笔记。恢复前自动另存当前数据。</p><Button onClick={async () => { const result = await run('create_backup', {}); if (result) setSavedPath(result.path) }}>创建备份</Button><Button onClick={async () => { const result = await run('export_data', {}); if (result) setSavedPath(result.path) }}>导出 JSON</Button>{savedPath && <Field label="已保存路径"><input readOnly value={savedPath} /></Field>}<Field label="选择备份"><select value={backupId} onChange={event => { setBackupId(event.target.value); setRestoreAccepted(false) }}><option value="">选择本机备份…</option>{data.backups?.map(item => <option key={item.id} value={item.id}>{item.id}</option>)}</select></Field><label><input type="checkbox" checked={restoreAccepted} onChange={event => setRestoreAccepted(event.target.checked)} />我确认用所选备份替换当前工作台数据</label><Button disabled={!backupId || !restoreAccepted} onClick={async () => { const result = await run('restore_backup', { id: backupId }); if (result) { setRestoreAccepted(false); setBackupId('') } }}>恢复所选备份</Button><p className="muted">自动化仅在应用运行时工作。关闭窗口会停止服务；错过的日报可以在历史页选择日期补记。</p></Panel>
    </div></div>
  </div>
}
