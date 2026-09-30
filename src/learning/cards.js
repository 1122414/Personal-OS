export const RATINGS = [['forgot', '忘了'], ['fuzzy', '模糊'], ['remembered', '记得']]

export function isNewCard(card) {
  return !card.reviews?.length
}

/** Unmastered cards due today or earlier: overdue reviews first, then new cards, oldest first. */
export function todayCards(cards, today) {
  return (cards || [])
    .filter(card => !card.mastered_at && card.due_date && card.due_date <= today)
    .sort((a, b) => Number(isNewCard(a)) - Number(isNewCard(b)) || a.due_date.localeCompare(b.due_date) || a.created_at.localeCompare(b.created_at))
}

/** A topic's deck: today's cards in review order, then the rest by next review date. */
export function deckOrder(cards, today) {
  const due = todayCards(cards, today)
  const dueIds = new Set(due.map(card => card.id))
  const later = (cards || []).filter(card => !card.mastered_at && !dueIds.has(card.id))
    .sort((a, b) => (a.due_date || '').localeCompare(b.due_date || '') || a.created_at.localeCompare(b.created_at))
  return [...due, ...later]
}

export function dueLabel(card, today) {
  if (card.mastered_at) return '已掌握'
  if (!card.due_date || card.due_date <= today) return isNewCard(card) ? '今天学' : '今天复习'
  const days = Math.round((new Date(`${card.due_date}T00:00:00`) - new Date(`${today}T00:00:00`)) / 86400000)
  return days === 1 ? '明天复习' : `${days} 天后复习`
}

export function sourceLabel(card) {
  return card.source === 'ai' ? `AI · ${card.engine || '生成'}` : '我写的'
}
