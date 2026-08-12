import { useMemo } from 'react'
import { useLoader } from '@react-three/fiber'
import * as THREE from 'three'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader'
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader'

// Реквизит Кейн расставляет сам, последним проходом по карте.

const TARGET_HEIGHT = { chest: 1.0, tree: 3.0 }

function useProp(name) {
  const materials = useLoader(MTLLoader, `/${name}.mtl`)
  const obj = useLoader(OBJLoader, `/${name}.obj`, loader => {
    materials.preload()
    loader.setMaterials(materials)
  })
  // Модели из MagicaVoxel приходят в произвольном масштабе — приводим
  // к нужной высоте по габаритам, а не подбираем множитель на глаз.
  return useMemo(() => {
    const box = new THREE.Box3().setFromObject(obj)
    const size = new THREE.Vector3()
    box.getSize(size)
    const scale = size.y > 0 ? TARGET_HEIGHT[name] / size.y : 1
    return { obj, scale }
  }, [obj, name])
}

function Tent({ accent }) {
  return (
    <group>
      <mesh position={[0, 1.1, 0]}>
        <coneGeometry args={[1.2, 2.2, 12]} />
        <meshStandardMaterial color="#d93b3b" />
      </mesh>
      <mesh position={[0, 2.4, 0]}>
        <sphereGeometry args={[0.2, 10, 10]} />
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={0.6} />
      </mesh>
    </group>
  )
}

function Crystal({ accent }) {
  return (
    <group>
      <mesh position={[0, 1.0, 0]} rotation={[0, 0.4, 0]}>
        <octahedronGeometry args={[0.75]} />
        <meshStandardMaterial color={accent} emissive={accent}
          emissiveIntensity={0.5} flatShading />
      </mesh>
      <mesh position={[0.5, 0.5, 0.3]} rotation={[0, 1.1, 0.2]}>
        <octahedronGeometry args={[0.35]} />
        <meshStandardMaterial color={accent} emissive={accent}
          emissiveIntensity={0.4} flatShading />
      </mesh>
    </group>
  )
}

function Lantern({ accent }) {
  return (
    <group>
      <mesh position={[0, 0.8, 0]}>
        <cylinderGeometry args={[0.09, 0.12, 1.6, 8]} />
        <meshStandardMaterial color="#3a3a3a" />
      </mesh>
      <mesh position={[0, 1.8, 0]}>
        <sphereGeometry args={[0.3, 10, 10]} />
        <meshStandardMaterial color="#ffe9a8" emissive={accent}
          emissiveIntensity={1.1} />
      </mesh>
    </group>
  )
}

function Flag({ accent }) {
  return (
    <group>
      <mesh position={[0, 1.4, 0]}>
        <cylinderGeometry args={[0.07, 0.07, 2.8, 6]} />
        <meshStandardMaterial color="#5a4632" />
      </mesh>
      <mesh position={[0.55, 2.3, 0]}>
        <boxGeometry args={[1.1, 0.7, 0.05]} />
        <meshStandardMaterial color={accent} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

function Bush() {
  return (
    <group>
      <mesh position={[0, 0.4, 0]}>
        <sphereGeometry args={[0.5, 10, 10]} />
        <meshStandardMaterial color="#3f7a3f" flatShading />
      </mesh>
      <mesh position={[0.35, 0.3, 0.25]}>
        <sphereGeometry args={[0.33, 10, 10]} />
        <meshStandardMaterial color="#356b35" flatShading />
      </mesh>
    </group>
  )
}

function Statue({ accent }) {
  return (
    <group>
      <mesh position={[0, 0.2, 0]}>
        <boxGeometry args={[0.9, 0.4, 0.9]} />
        <meshStandardMaterial color="#7a7a82" />
      </mesh>
      <mesh position={[0, 1.0, 0]}>
        <boxGeometry args={[0.45, 1.2, 0.45]} />
        <meshStandardMaterial color="#9a9aa2" />
      </mesh>
      <mesh position={[0, 1.85, 0]}>
        <sphereGeometry args={[0.28, 10, 10]} />
        <meshStandardMaterial color={accent} />
      </mesh>
    </group>
  )
}

function Lollipop({ accent }) {
  return (
    <group>
      <mesh position={[0, 0.9, 0]}>
        <cylinderGeometry args={[0.08, 0.08, 1.8, 8]} />
        <meshStandardMaterial color="#fff0f6" />
      </mesh>
      <mesh position={[0, 2.0, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.5, 0.22, 8, 20]} />
        <meshStandardMaterial color={accent} />
      </mesh>
    </group>
  )
}

function Barrel() {
  return (
    <mesh position={[0, 0.45, 0]}>
      <cylinderGeometry args={[0.42, 0.38, 0.9, 12]} />
      <meshStandardMaterial color="#7a5230" />
    </mesh>
  )
}

const PROCEDURAL = {
  tent: Tent, crystal: Crystal, lantern: Lantern, flag: Flag,
  bush: Bush, statue: Statue, lollipop: Lollipop, barrel: Barrel,
}


// ── Изобретённый реквизит ───────────────────────────────────────
// Предмет приходит с сервера как список примитивов, а не как отдельный
// компонент. Смысл в том, что Кейн может придумать девятый предмет и
// сотый, не дожидаясь, пока я напишу для них код.

function toneColor(tone, palette) {
  const wall = palette?.wall || '#8a8f9c'
  const floor = palette?.floor || '#4a4e58'
  const accent = palette?.accent || '#ffd23f'
  if (tone === 'accent') return accent
  if (tone === 'wall') return wall
  if (tone === 'floor') return floor
  const c = new THREE.Color(tone === 'dark' ? wall : accent)
  const hsl = {}
  c.getHSL(hsl)
  c.setHSL(hsl.h, hsl.s, tone === 'dark'
    ? Math.max(0.06, hsl.l * 0.45)
    : Math.min(0.94, hsl.l * 1.5 + 0.2))
  return `#${c.getHexString()}`
}

function Part({ part, palette }) {
  const { shape, x, y, z, w, h, d, rot } = part
  const color = toneColor(part.tone, palette)
  // Примитивы стоят основанием на своей отметке, поэтому центр поднят
  // на половину высоты — иначе половина предмета уходила бы в пол.
  const pos = [x, y + h / 2, z]

  // Формы обязаны совпадать с теми, по которым бэкенд проверяет связность.
  if (shape === 'torus') {
    return (
      <mesh position={pos} rotation={[Math.PI / 2, 0, rot || 0]} castShadow>
        <torusGeometry args={[0.35 * w, 0.15 * w, 8, 16]} />
        <meshStandardMaterial color={color} roughness={0.75} />
      </mesh>
    )
  }
  if (shape === 'cyl') {
    return (
      <mesh position={pos} rotation={[0, rot || 0, 0]}
            scale={[1, 1, Math.max(d / Math.max(w, 1e-6), 0.05)]} castShadow>
        <cylinderGeometry args={[w / 2, w / 2, h, 12]} />
        <meshStandardMaterial color={color} roughness={0.75} />
      </mesh>
    )
  }
  return (
    <mesh position={pos} rotation={[0, rot || 0, 0]}
          scale={shape === 'sphere' || shape === 'cone'
            ? [1, 1, Math.max(d / Math.max(w, 1e-6), 0.05)] : [1, 1, 1]}
          castShadow>
      {shape === 'box' && <boxGeometry args={[w, h, d]} />}
      {shape === 'cone' && <coneGeometry args={[w / 2, h, 12]} />}
      {shape === 'sphere' && <sphereGeometry args={[w / 2, 14, 10]} />}
      <meshStandardMaterial color={color} roughness={0.75} />
    </mesh>
  )
}

function Invented({ spec, palette }) {
  return (
    <>
      {spec.map((part, i) => <Part key={i} part={part} palette={palette} />)}
    </>
  )
}

export default function Decorations({ decorations, palette }) {
  const chest = useProp('chest')
  const tree = useProp('tree')
  const accent = palette?.accent || '#ffd23f'

  const items = useMemo(() => decorations.map((d, i) => {
    const pos = [d.x, 0, d.z]
    if (d.spec) {
      return (
        <group key={i} position={pos}>
          <Invented spec={d.spec} palette={palette} />
        </group>
      )
    }
    const Proc = PROCEDURAL[d.type]
    if (Proc) {
      return (
        <group key={i} position={pos}>
          <Proc accent={accent} />
        </group>
      )
    }
    const src = d.type === 'tree' ? tree : chest
    return (
      <primitive key={i} object={src.obj.clone()} position={pos} scale={src.scale} />
    )
  }), [decorations, chest, tree, accent, palette])

  return <>{items}</>
}
