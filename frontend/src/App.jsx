import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { useState, useEffect, useRef } from 'react'
import Caine from './Caine'
import Cube from './Cube'
import Sphere from './Sphere'
import Cone from './Cone'
import Chat from './Chat'
import Walkers from './Walkers'

export default function App() {
  const [blocks, setBlocks] = useState([])
  const [walkers, setWalkers] = useState([])
  const [chatEvent, setChatEvent] = useState(null)
  const stepCount = useRef(0)
  const walkerIdRef = useRef(0)

  useEffect(() => {
    setChatEvent('welcome')
  }, [])

  const handleStep = (x, y, z, color, shape, done, newWalker) => {
    if (done) {
      setChatEvent('finished')

      // Кейн создал нового гуляку
      if (newWalker) {
        setWalkers(prev => [...prev, {
          id: walkerIdRef.current++,
          color: newWalker.color,
          x: newWalker.x,
          z: newWalker.z,
        }])
      }
      return
    }

    if (!color) {
      stepCount.current += 1
      if (stepCount.current % 15 === 0) {
        setChatEvent('thinking')
      }
      return
    }

    if (Math.abs(x) > 38 || Math.abs(z) > 38) return

    setBlocks(prev => {
      const filtered = prev.filter(b => !(b.x === x && b.y === y && b.z === z))
      return [...filtered, { x, y, z, color, shape }]
    })
  }

  const renderBlock = (block, i) => {
    const pos = [block.x, block.y, block.z]
    if (block.shape === 'sphere') return <Sphere key={i} position={pos} color={block.color} />
    if (block.shape === 'cone') return <Cone key={i} position={pos} color={block.color} />
    return <Cube key={i} position={pos} color={block.color} />
  }

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#111' }}>
      <Chat event={chatEvent} />
      <Canvas camera={{ position: [0, 25, 40] }}>
        <ambientLight intensity={1.5} />
        <directionalLight position={[10, 20, 10]} intensity={2} castShadow />
        <directionalLight position={[-10, 20, -10]} intensity={1} />
        <pointLight position={[0, 10, 0]} intensity={1} color="white" />
        <Caine onStep={handleStep} />
        {blocks.map((block, i) => renderBlock(block, i))}
        <Walkers walkers={walkers} blocks={blocks} />
        <OrbitControls />
        <gridHelper args={[80, 80]} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
          <planeGeometry args={[80, 80]} />
          <meshStandardMaterial color="#333" />
        </mesh>
      </Canvas>
    </div>
  )
}