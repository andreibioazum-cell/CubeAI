import { useEffect, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import Decorations from './Decorations'
import { api } from './engine'

// Каталог придуманного реквизита: ?props=1
// Нужен для проверки глазами: на общем плане предмет ростом в полтора
// блока не отличить от акцента здания.

const PALETTE = { wall: '#8a8f9c', floor: '#4a4e58', accent: '#d8b45a' }
const STEP = 3

export default function PropCatalog() {
  const [items, setItems] = useState([])

  useEffect(() => {
    api('/props')
      .then(d => setItems(d.props || []))
      .catch(() => setItems([]))
  }, [])

  const cols = Math.ceil(Math.sqrt(Math.max(items.length, 1)))
  const decorations = items.map((p, i) => ({
    type: p.name,
    spec: p.parts,
    x: (i % cols) * STEP - (cols - 1) * STEP / 2,
    y: 0,
    z: Math.floor(i / cols) * STEP - (cols - 1) * STEP / 2,
  }))

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#12151c' }}>
      <div style={{
        position: 'absolute', top: 16, left: 16, zIndex: 10,
        color: '#e8e8e8', fontFamily: '"Courier New", monospace', fontSize: 13,
      }}>
        реквизит, придуманный Кейном: {items.length}
      </div>
      <Canvas camera={{ position: [0, 14, 20], fov: 42 }}>
        <ambientLight intensity={0.75} />
        <directionalLight position={[8, 14, 6]} intensity={1.1} />
        <gridHelper args={[cols * STEP + 4, cols + 2, '#2a2f3a', '#20242c']} />
        <Decorations decorations={decorations} palette={PALETTE} />
        <OrbitControls />
      </Canvas>
    </div>
  )
}
