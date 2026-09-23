export async function loadState() {
  const response = await fetch('/api/state')
  if (!response.ok) throw new Error('无法读取本地数据')
  return response.json()
}

export async function action(name, payload = {}) {
  const response = await fetch(`/api/action/${name}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || '操作失败')
  return data
}

export async function recentObsidian() {
  const response = await fetch('/api/obsidian/recent')
  if (!response.ok) throw new Error('无法读取 Obsidian')
  return response.json()
}
