import React, { useEffect, useState } from 'react'

const NONE = { models: [], default: '' }
const found = new Map()

function discover(runtime) {
  if (!found.has(runtime)) {
    found.set(runtime, fetch(`/api/agent_models?runtime=${encodeURIComponent(runtime)}`)
      .then(response => response.ok ? response.json() : NONE)
      .catch(() => { found.delete(runtime); return NONE }))
  }
  return found.get(runtime)
}

export default function ModelField({ runtime, value, onChange, name, disabled }) {
  const [options, setOptions] = useState(NONE)
  useEffect(() => {
    let live = true
    setOptions(NONE)
    if (runtime && runtime !== 'multica') discover(runtime).then(result => { if (live) setOptions(result) })
    return () => { live = false }
  }, [runtime])
  if (runtime === 'multica') return <span className="muted">由 Multica 智能体决定</span>
  const list = `models-${runtime}`
  return <>
    <input className="model-input" name={name} list={list} value={value} onChange={event => onChange(event.target.value)} disabled={disabled}
      aria-label="模型" maxLength={100} placeholder={`默认${options.default ? `（${options.default}）` : '（CLI 配置）'}`} />
    <datalist id={list}>{options.models.map(model => <option key={model.id} value={model.id}>{model.label === model.id ? '' : model.label}</option>)}</datalist>
  </>
}
