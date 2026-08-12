import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

// Гуляки идут по записи настоящей прогулки, а не бродят случайно.

const SPEED = 3.2          // кадров записи в секунду
// Ходок должен читаться на фоне постройки, поэтому он крупнее клетки
// и светится собственным цветом: при габаритах в половину блока его
// не было видно даже вблизи.
const BODY = new THREE.BoxGeometry(0.8, 1.7, 0.8)
const HEAD = new THREE.SphereGeometry(0.48, 12, 10)

export default function Walkers({ walk, palette }) {
  const group = useRef()
  const clock = useRef(0)

  const frames = walk?.frames
  const count = walk?.walkers || 0

  const colors = useMemo(() => {
    const accent = new THREE.Color(palette?.accent || '#ffd23f')
    return Array.from({ length: count }, (_, i) => {
      const c = accent.clone()
      const hsl = {}
      c.getHSL(hsl)
      c.setHSL((hsl.h + i * 0.11) % 1, 0.55, 0.55)
      return c
    })
  }, [count, palette])

  useFrame((_, delta) => {
    if (!frames || !frames.length || !group.current) return
    clock.current += delta * SPEED
    const t = clock.current % (frames.length - 1 || 1)
    const i = Math.floor(t)
    const f = t - i
    const a = frames[i]
    const b = frames[Math.min(i + 1, frames.length - 1)]
    group.current.children.forEach((child, k) => {
      if (!a[k] || !b[k]) return
      // Плавно между записанными точками: запись прорежена, иначе
      // движение выглядело бы рывками.
      child.position.x = a[k][0] + (b[k][0] - a[k][0]) * f
      child.position.z = a[k][1] + (b[k][1] - a[k][1]) * f
    })
  })

  if (!frames || !frames.length) return null

  return (
    <group ref={group}>
      {Array.from({ length: count }, (_, i) => (
        <group key={i} position={[0, 0, 0]}>
          <mesh geometry={BODY} position={[0, 0.85, 0]} castShadow>
            <meshStandardMaterial color={colors[i]} roughness={0.5}
                                  emissive={colors[i]} emissiveIntensity={0.45} />
          </mesh>
          <mesh geometry={HEAD} position={[0, 2.05, 0]} castShadow>
            <meshStandardMaterial color={colors[i]} roughness={0.4}
                                  emissive={colors[i]} emissiveIntensity={0.6} />
          </mesh>
        </group>
      ))}
    </group>
  )
}
