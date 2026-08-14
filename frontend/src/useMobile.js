import { useState, useEffect } from 'react'

// Телефон определяется не по строке браузера, а по тому, что важно для
// показа: узкий экран и палец вместо мыши. Строку подделывают, а поворот
// экрана она вообще не отслеживает.
//
// 860 px — с запасом: Samsung S24 в альбомной 852, iPhone 15 тоже 852,
// Xiaomi обычно уже. Планшет сюда не попадает, ему широкой вёрстки хватает.
const QUERY = '(max-width: 860px), (pointer: coarse) and (max-height: 560px)'

export default function useMobile() {
  const [mobile, setMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(QUERY).matches)

  useEffect(() => {
    const mq = window.matchMedia(QUERY)
    const on = e => setMobile(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  return mobile
}
