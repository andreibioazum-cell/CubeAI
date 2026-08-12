import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'

// Промах Кейна: он попытался построить и ошибся цветом либо полез
// в занятую клетку. Раньше ошибки были не видны вообще — картинка
// рисовалась по эталону. Теперь видно, как сеть учится.

const LIFETIME = 0.45 // секунды

function MissFlash({ miss, onDone }) {
  const ref = useRef()
  const age = useRef(0)
  const finished = useRef(false)

  useFrame((_, delta) => {
    if (!ref.current || finished.current) return
    age.current += delta
    const t = age.current / LIFETIME
    if (t >= 1) {
      // Кадры идут дальше, пока React не размонтирует вспышку —
      // без флага onDone дёргался бы каждый кадр.
      finished.current = true
      onDone(miss.id)
      return
    }
    const s = 1 + t * 0.8
    ref.current.scale.set(s, s, s)
    ref.current.material.opacity = 1 - t
  })

  return (
    <mesh ref={ref} position={[miss.x, miss.y, miss.z]}>
      <boxGeometry args={[1.05, 1.05, 1.05]} />
      <meshBasicMaterial color="#ff2b2b" wireframe transparent opacity={1} />
    </mesh>
  )
}

export default function Misses({ misses, onDone }) {
  return (
    <>
      {misses.map(m => (
        <MissFlash key={m.id} miss={m} onDone={onDone} />
      ))}
    </>
  )
}
