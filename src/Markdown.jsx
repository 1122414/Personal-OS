import React from 'react'

// Build React nodes; raw HTML and images never become executable markup or requests.
function inline(text, depth = 0) {
  if (depth > 3) return text
  const pattern = /(!?\[[^\]\n]*\]\([^\s)]+\)|\*\*[^*\n]+\*\*|`[^`\n]+`|https?:\/\/[^\s<>\u3000]+)/g
  const output = []
  let from = 0
  for (const match of text.matchAll(pattern)) {
    output.push(text.slice(from, match.index))
    const token = match[0]
    const key = match.index
    if (token.startsWith('![')) {
      output.push(<span key={key}>[图片：{token.slice(2, token.indexOf(']'))}]</span>)
    } else if (token.startsWith('[')) {
      const end = token.indexOf('](')
      const label = token.slice(1, end)
      const href = token.slice(end + 2, -1)
      output.push(/^https?:\/\//i.test(href) ? <a key={key} href={href} target="_blank" rel="noopener noreferrer">{inline(label, depth + 1)}</a> : <span key={key}>{label}</span>)
    } else if (token.startsWith('**')) {
      output.push(<strong key={key}>{inline(token.slice(2, -2), depth + 1)}</strong>)
    } else if (token.startsWith('`')) {
      output.push(<code key={key}>{token.slice(1, -1)}</code>)
    } else {
      const href = token.replace(/[。；，、）)\],;.!?]+$/, '')
      output.push(<React.Fragment key={key}><a href={href} target="_blank" rel="noopener noreferrer">{href}</a>{token.slice(href.length)}</React.Fragment>)
    }
    from = match.index + token.length
  }
  output.push(text.slice(from))
  return output
}

const cells = line => line.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/).map(cell => cell.trim().replace(/\\\|/g, '|'))
const tableRule = line => line?.includes('|') && cells(line).every(cell => /^:?-{3,}:?$/.test(cell))
const listLine = line => /^\s*(?:[-+*]|\d+[.)])\s+/.test(line)
const special = line => /^(#{1,6}\s|```|~~~|>\s?|\s*$|---+$)/.test(line) || listLine(line)

export default function Markdown({ text }) {
  const lines = text.replace(/\r\n/g, '\n').replace(/^---\n[\s\S]*?\n---\n/, '').split('\n')
  const nodes = []
  for (let i = 0; i < lines.length;) {
    const line = lines[i]
    const key = i
    if (!line.trim()) { i++; continue }
    if (/^(```|~~~)/.test(line)) {
      const fence = line.slice(0, 3)
      const code = []
      i++
      while (i < lines.length && !lines[i].startsWith(fence)) code.push(lines[i++])
      if (i < lines.length) i++
      nodes.push(<pre key={key}><code>{code.join('\n')}</code></pre>)
    } else if (/^#{1,6}\s/.test(line)) {
      const level = line.indexOf(' ')
      nodes.push(React.createElement(`h${Math.min(level + 1, 6)}`, { key }, inline(line.slice(level + 1))))
      i++
    } else if (tableRule(lines[i + 1]) && line.includes('|')) {
      const header = cells(line)
      i += 2
      const rows = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(cells(lines[i++]))
      nodes.push(<div className="report-table" key={key}><table><thead><tr>{header.map((cell, n) => <th key={n}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row, n) => <tr key={n}>{row.map((cell, k) => <td key={k}>{inline(cell)}</td>)}</tr>)}</tbody></table></div>)
    } else if (listLine(line)) {
      const ordered = /^\s*\d+[.)]/.test(line)
      const items = []
      while (i < lines.length && listLine(lines[i]) && /^\s*\d+[.)]/.test(lines[i]) === ordered) {
        let value = lines[i++].replace(/^\s*(?:[-+*]|\d+[.)])\s+/, '')
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !listLine(lines[i])) value += '\n' + lines[i++].trim()
        const checkbox = value.match(/^\[([ xX])\]\s*/)
        items.push(<li key={items.length}>{checkbox && <input type="checkbox" checked={checkbox[1] !== ' '} disabled aria-label="原笔记中的勾选状态" />}{inline(checkbox ? value.slice(checkbox[0].length) : value)}</li>)
      }
      nodes.push(React.createElement(ordered ? 'ol' : 'ul', { key }, items))
    } else if (/^>/.test(line)) {
      const quote = []
      while (i < lines.length && /^>/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ''))
      nodes.push(<blockquote key={key}>{inline(quote.join('\n'))}</blockquote>)
    } else if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
      nodes.push(<hr key={key} />); i++
    } else {
      const paragraph = [lines[i++]]
      while (i < lines.length && !special(lines[i]) && !tableRule(lines[i + 1])) paragraph.push(lines[i++])
      nodes.push(<p key={key}>{inline(paragraph.join('\n'))}</p>)
    }
  }
  return <div className="markdown-report">{nodes}</div>
}
