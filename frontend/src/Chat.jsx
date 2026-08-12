import { useMemo } from 'react'

// Чат в углу: реплики Кейна и Авеля пузырями своего цвета.

const VISIBLE = 4

export default function Chat({ messages }) {
  const items = useMemo(() => (messages || []).slice(-VISIBLE).map((raw, i) => {
    const cut = raw.indexOf(': ')
    const who = cut > 0 ? raw.slice(0, cut) : 'Кейн'
    const text = cut > 0 ? raw.slice(cut + 2) : raw
    return { key: `${i}-${raw}`, who, text, side: who === 'Авель' ? 'abel' : 'caine' }
  }), [messages])

  return (
    <div className="chat spray">
      {items.map(m => (
        <div key={m.key} className={`bubble ${m.side}`}>
          <span className="who">{m.who}</span>
          {m.text}
        </div>
      ))}
    </div>
  )
}
