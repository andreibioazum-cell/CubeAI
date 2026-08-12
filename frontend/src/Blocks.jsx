import { useRef, useLayoutEffect, useState, useEffect } from 'react'
import { mixedTexture } from './textures'
import * as THREE from 'three'

// Один InstancedMesh на пару (форма + цвет) вместо отдельного меша на блок.

const dummy = new THREE.Object3D()

function geometryFor(shape) {
  if (shape === 'sphere') return <sphereGeometry args={[0.5, 12, 12]} />
  if (shape === 'cone') return <coneGeometry args={[0.5, 1, 12]} />
  return <boxGeometry args={[1, 1, 1]} />
}

// Ёмкость округляем до степени двойки, чтобы не пересоздавать буфер
// на каждый новый блок — перемонтаж случается ~log(n) раз.
function capacityFor(n) {
  let cap = 256
  while (cap < n) cap *= 2
  return cap
}

// Код роли из чертежа: 1 — стена, 2 — пол/настил, 3 — акцент.
const ROLE_NAME = { 1: 'wall', 2: 'floor', 3: 'accent' }

function BlockGroup({ shape, color, items, capacity, role, mix }) {
  const [tex, setTex] = useState(null)

  // Текстура подбирается под состав стиля и умножается на цвет палитры.
  useEffect(() => {
    let dropped = false
    mixedTexture(mix, ROLE_NAME[role] || 'wall', color)
      .then(t => { if (!dropped) setTex(t) })
      .catch(() => {})
    return () => { dropped = true }
  }, [mix, role, color])

  const ref = useRef()

  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const n = Math.min(items.length, capacity)
    for (let i = 0; i < n; i++) {
      const b = items[i]
      dummy.position.set(b.x, b.y, b.z)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)
    }
    mesh.count = n
    mesh.instanceMatrix.needsUpdate = true
    mesh.computeBoundingSphere()
  }, [items, capacity])

  return (
    <instancedMesh ref={ref} args={[null, null, capacity]}
                   frustumCulled={false} castShadow receiveShadow>
      {geometryFor(shape)}
      {/* key заставляет пересоздать материал, когда текстура доехала.
          Без этого шейдер остаётся собранным без поддержки карты: она
          приходит асинхронно, материал к тому моменту уже скомпилирован,
          и блоки оставались белыми — цвет-то ушёл в текстуру.

          Когда текстура есть, цвет уже вмешан в неё: иначе палитра
          умножилась бы дважды и всё потемнело. */}
      <meshStandardMaterial key={tex ? 'textured' : 'plain'}
                            color={tex ? '#ffffff' : color}
                            map={tex || null} />
    </instancedMesh>
  )
}

export default function Blocks({ groups, mix }) {
  return (
    <>
      {groups.map(({ key, shape, color, items, role }) => {
        const capacity = capacityFor(items.length)
        return (
          <BlockGroup
            // capacity в ключе: смена ёмкости = пересоздание буфера
            key={`${key}:${capacity}`}
            shape={shape}
            color={color}
            items={items}
            capacity={capacity}
            role={role}
            mix={mix}
          />
        )
      })}
    </>
  )
}
