export const PRIORITIES = { high: '高', medium: '中', low: '低' }
const CYCLE = ['medium', 'high', 'low']

export function nextPriority(priority) {
  return CYCLE[(CYCLE.indexOf(priority || 'medium') + 1) % CYCLE.length]
}

/** Same order as the server: to-dos from before ordering existed first by creation time, then by rank. */
export function todoOrder(a, b) {
  const ra = a.rank ?? null, rb = b.rank ?? null
  if ((ra === null) !== (rb === null)) return ra === null ? -1 : 1
  return (ra ?? 0) - (rb ?? 0) || a.created_at.localeCompare(b.created_at)
}

/** Where a drop lands: before the hovered row, or before the next row when over its lower half. */
export function dropBefore(list, hoveredId, lowerHalf) {
  const index = list.findIndex(item => item.id === hoveredId)
  if (index < 0) return null
  return lowerHalf ? list[index + 1]?.id ?? null : hoveredId
}
