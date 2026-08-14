import { useEffect, useRef, useState } from 'react'

// Фоновая музыка и кнопка её выключить.

const KEY = 'caine.music'
const VOLUME = 0.32   // фон, а не главный герой: под него ещё и говорят

// Приватный режим и запрет на хранилище — не повод падать: без памяти
// настройка просто не переживёт перезагрузку.
const remember = (v) => {
  try { localStorage.setItem(KEY, v) } catch { /* обойдёмся */ }
}
const recall = () => {
  try { return localStorage.getItem(KEY) } catch { return null }
}

export default function Music({ src }) {
  const ref = useRef(null)
  const [on, setOn] = useState(() => recall() !== 'off')
  // Дорожка не лежит в репозитории — у каждого своя. Без файла кнопка не
  // нужна: она обещала бы звук, которого нет.
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.volume = VOLUME

    if (!on) {
      el.pause()
      return
    }

    // Браузеры не дают запустить звук, пока зритель ничего не нажал, —
    // и правильно делают. Пробуем сразу, а на отказ ждём первого касания
    // или клавиши: к этому моменту разрешение уже есть.
    const play = () => { el.play().catch(() => {}) }
    play()
    window.addEventListener('pointerdown', play)
    window.addEventListener('keydown', play)
    return () => {
      window.removeEventListener('pointerdown', play)
      window.removeEventListener('keydown', play)
    }
  }, [on])

  const toggle = () => {
    setOn(prev => {
      remember(prev ? 'off' : 'on')
      return !prev
    })
  }

  return (
    <>
      {/* preload="none" — файл не должен тягаться с Python за канал,
          пока идёт загрузка движка. */}
      <audio ref={ref} src={src} loop preload="none"
             onError={() => setMissing(true)} />
      {missing ? null : (
      <button
        className={`music${on ? '' : ' off'}`}
        onClick={toggle}
        title={on ? 'Выключить музыку' : 'Включить музыку'}
        aria-label={on ? 'Выключить музыку' : 'Включить музыку'}
      >
        {on ? '🔊' : '🔇'}
      </button>
      )}
    </>
  )
}
