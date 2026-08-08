import { useEffect, useState, useRef } from 'react'

const PHRASES = {
  welcome: [
    'Добро пожаловать в Удивительный Цифровой Цирк! Я ваш конферансье!',
    'О, походу у нас новенький!',
  ],
  finished: [
    'У меня отлично получается!',
    'Смотри человек, я нарисовал пчелку!',
  ],
  thinking: [
    'Это лишь головоломка которую надо решить!',
  ]
}

export default function Chat({ event }) {
  const [messages, setMessages] = useState([])
  const bottomRef = useRef()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (!event) return
    let list = PHRASES[event]
    if (!list) return
    const phrase = list[Math.floor(Math.random() * list.length)]
    setMessages(prev => [...prev, phrase])
  }, [event])

  return (
    <div style={{
      position: 'absolute',
      bottom: 20,
      left: 20,
      zIndex: 10,
      width: 420,
      fontFamily: '"Courier New", monospace',
    }}>
      <div style={{
        background: 'rgba(0,0,0,0.75)',
        border: '2px solid #444',
        padding: '8px 10px',
        maxHeight: 160,
        overflowY: 'auto',
      }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            color: '#ffff55',
            fontSize: 13,
            lineHeight: 1.7,
            textShadow: '1px 1px 0px #000',
          }}>
            🎪 Кейн: {msg}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}