import { useFrame, useLoader } from '@react-three/fiber'
import { useRef, useEffect } from 'react'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader'
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader'

export default function Caine({ onStep }) {
  const ref = useRef()
  const target = useRef({ x: 0, y: 1, z: 0 })
  const materials = useLoader(MTLLoader, '/caine.mtl')
  const obj = useLoader(OBJLoader, '/caine.obj', loader => {
    materials.preload()
    loader.setMaterials(materials)
  })

  useEffect(() => {
    const interval = setInterval(async () => {
      const res = await fetch('http://127.0.0.1:8000/step')
      const data = await res.json()
      target.current.x = data.x
      target.current.y = data.y + 1
      target.current.z = data.z
      onStep(
        data.x,
        data.y,
        data.z,
        data.color,
        data.shape,
        data.done,
        data.new_walker || null,
      )
    }, 150)
    return () => clearInterval(interval)
  }, [])

  useFrame(() => {
    if (!ref.current) return
    ref.current.position.x += (target.current.x - ref.current.position.x) * 0.15
    ref.current.position.y += (target.current.y - ref.current.position.y) * 0.15
    ref.current.position.z += (target.current.z - ref.current.position.z) * 0.15
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