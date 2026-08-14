import { useEffect, useRef } from 'react'
import { useThree, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { framing } from './framing'

// Камера смотрит на платформу того строителя, которого сейчас показывают,
// и переезжает между платформами плавно, а не прыжком.

const EASE = 2.4          // скорость переезда между платформами

export default function FrameCamera({ bounds, controls, platformX = 0 }) {
  const { camera, size } = useThree()
  const want = useRef(null)
  const jump = useRef(true)

  useEffect(() => {
    if (!bounds) return
    const cx = (bounds.minx + bounds.maxx) / 2 + platformX
    const cz = (bounds.minz + bounds.maxz) / 2
    const { dist, sideways } = framing(bounds, size.width / size.height)

    // Угол намеренно низкий (~30° над горизонтом): при взгляде почти
    // сверху высота стен и башен не читается, постройка выглядит плоской.
    // Сторона захода выбирается так, чтобы длинная сторона постройки ушла
    // в глубину кадра — иначе на вертикальном экране она не помещается.
    const pos = sideways
      ? new THREE.Vector3(cx + dist * 1.05, dist * 0.6, cz)
      : new THREE.Vector3(cx, dist * 0.6, cz + dist * 1.05)

    want.current = { target: new THREE.Vector3(cx, 0, cz), pos, dist }
    // Первый кадр ставим сразу: плавный переезд из нуля выглядел бы как
    // падение камеры с высоты.
    if (jump.current) {
      camera.position.copy(want.current.pos)
      if (controls?.current) {
        controls.current.target.copy(want.current.target)
        controls.current.update()
      }
      jump.current = false
    }
  }, [bounds, camera, controls, platformX, size.width, size.height])

  useFrame((_, delta) => {
    const w = want.current
    if (!w || !controls?.current) return
    const k = 1 - Math.exp(-EASE * delta)

    // Переезжает цель, а не сама камера: зритель сохраняет свой угол и
    // приближение, меняется только то, вокруг чего он крутится.
    const c = controls.current
    if (c.target.distanceTo(w.target) > 0.05) {
      const shift = w.target.clone().sub(c.target).multiplyScalar(k)
      c.target.add(shift)
      camera.position.add(shift)
      c.update()
    }
  })

  return null
}
