import { useFrame, useLoader } from '@react-three/fiber'
import { useRef, useEffect, useState, useMemo } from 'react'
import * as THREE from 'three'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader'
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader'
import { api } from './engine'

const DEFAULT_TEMPO = 150

export default function Caine({ onStep, onConnection, who = 'caine',
                               tint = null }) {
  const ref = useRef()
  const target = useRef({ x: 0, y: 1, z: 0 })
  const yaw = useRef(0)

  // Колбэки держим в ref: интервал ставится один раз, но всегда
  // вызывает актуальную версию обработчика.
  const onStepRef = useRef(onStep)
  const onConnRef = useRef(onConnection)
  onStepRef.current = onStep
  onConnRef.current = onConnection

  const [tempo, setTempo] = useState(null)

  const materials = useLoader(MTLLoader, '/caine.mtl')
  const loaded = useLoader(OBJLoader, '/caine.obj', loader => {
    materials.preload()
    loader.setMaterials(materials)
  })

  // Каждому строителю — своя копия модели.
  const obj = useMemo(() => {
    const copy = loaded.clone(true)
    if (tint) {
      copy.traverse(node => {
        if (!node.isMesh) return
        node.material = Array.isArray(node.material)
          ? node.material.map(m => m.clone())
          : node.material.clone()
        const paint = m => { m.color = new THREE.Color(tint) }
        Array.isArray(node.material) ? node.material.forEach(paint)
                                     : paint(node.material)
      })
    }
    return copy
  }, [loaded, tint])

  useEffect(() => {
    let cancelled = false
    api('/config')
      .then(c => { if (!cancelled) setTempo(c.tempo_ms || DEFAULT_TEMPO) })
      .catch(() => { if (!cancelled) setTempo(DEFAULT_TEMPO) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!tempo) return
    let cancelled = false
    let inFlight = false

    const tick = async () => {
      // Смена карты занимает секунду с лишним — не наслаиваем шаги
      // друг на друга, пока движок занят.
      if (inFlight) return
      inFlight = true
      try {
        const data = await api('/step', { who })
        if (cancelled) return

        const dx = data.x - target.current.x
        const dz = data.z - target.current.z
        if (dx || dz) yaw.current = Math.atan2(dx, dz)

        target.current.x = data.x
        target.current.y = data.y + 1
        target.current.z = data.z

        onConnRef.current?.(true)
        onStepRef.current?.(data)
      } catch (err) {
        // Движок ещё грузится или споткнулся — не роняем сцену, ждём.
        if (!cancelled) onConnRef.current?.(false, err.message)
      } finally {
        inFlight = false
      }
    }

    const interval = setInterval(tick, tempo)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [tempo, who])

  useFrame(() => {
    const m = ref.current
    if (!m) return
    m.position.x += (target.current.x - m.position.x) * 0.15
    m.position.y += (target.current.y - m.position.y) * 0.15
    m.position.z += (target.current.z - m.position.z) * 0.15

    // Разворот по кратчайшей дуге, иначе на переходе через ±π Кейн
    // прокручивается вокруг себя.
    let diff = yaw.current - m.rotation.y
    while (diff > Math.PI) diff -= 2 * Math.PI
    while (diff < -Math.PI) diff += 2 * Math.PI
    m.rotation.y += diff * 0.2
  })

  return (
    <primitive
      ref={ref}
      object={obj}
      scale={0.7}
      position={[0, 1, 0]}
    />
  )
}
