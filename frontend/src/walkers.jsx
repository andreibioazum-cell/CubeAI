import { useRef, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'

const SPEED = 0.12
const BOUNDS = 28
const STEP = 1.0

function isBlocked(x, z, blocks) {
  return blocks.some(b => Math.abs(b.x - x) < 0.9 && Math.abs(b.z - z) < 0.9)
}

function nextPos(x, z, dir) {
  switch (dir) {
    case 0: return { x, z: z + STEP }
    case 1: return { x, z: z - STEP }
    case 2: return { x: x - STEP, z }
    case 3: return { x: x + STEP, z }
    default: return { x, z }
  }
}

function WalkerMesh({ walker, blocks }) {
  const ref = useRef()
  const state = useRef({
    x: walker.x,
    z: walker.z,
    dir: Math.floor(Math.random() * 4),
    timer: 0,
    changeInterval: 40 + Math.floor(Math.random() * 80),
  })

  useEffect(() => {
    if (ref.current) {
      ref.current.position.x = walker.x
      ref.current.position.z = walker.z
    }
  }, [])

  useFrame(() => {
    if (!ref.current) return
    const s = state.current

    s.timer++

    if (s.timer >= s.changeInterval) {
      s.dir = Math.floor(Math.random() * 4)
      s.timer = 0
      s.changeInterval = 40 + Math.floor(Math.random() * 80)
    }

    if (s.timer % 15 === 0) {
      const next = nextPos(s.x, s.z, s.dir)
      if (
        Math.abs(next.x) < BOUNDS &&
        Math.abs(next.z) < BOUNDS &&
        !isBlocked(next.x, next.z, blocks)
      ) {
        s.x = next.x
        s.z = next.z
      } else {
        const dirs = [0, 1, 2, 3].filter(d => d !== s.dir).sort(() => Math.random() - 0.5)
        for (const d of dirs) {
          const alt = nextPos(s.x, s.z, d)
          if (
            Math.abs(alt.x) < BOUNDS &&
            Math.abs(alt.z) < BOUNDS &&
            !isBlocked(alt.x, alt.z, blocks)
          ) {
            s.x = alt.x
            s.z = alt.z
            s.dir = d
            break
          }
        }
      }
    }

    // Плавное движение к целевой позиции
    ref.current.position.x += (s.x - ref.current.position.x) * SPEED
    ref.current.position.z += (s.z - ref.current.position.z) * SPEED
  })

  return (
    <mesh ref={ref} position={[walker.x, 0.5, walker.z]}>
      <sphereGeometry args={[0.35, 12, 12]} />
      <meshStandardMaterial color={walker.color} />
    </mesh>
  )
}

export default function Walkers({ walkers, blocks }) {
  return (
    <>
      {walkers.map(walker => (
        <WalkerMesh key={walker.id} walker={walker} blocks={blocks} />
      ))}
    </>
  )
}