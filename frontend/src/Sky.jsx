import { useMemo } from 'react'
import * as THREE from 'three'

// Небо градиентом вместо плоской заливки.

const VERT = `
  varying vec3 vPos;
  void main() {
    vPos = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const FRAG = `
  uniform vec3 top;
  uniform vec3 horizon;
  uniform vec3 ground;
  varying vec3 vPos;
  void main() {
    float h = normalize(vPos).y;
    // Горизонт намеренно узкий: широкая растяжка превращает небо в кисель
    vec3 col = h > 0.0
      ? mix(horizon, top, pow(clamp(h, 0.0, 1.0), 0.55))
      : mix(horizon, ground, pow(clamp(-h, 0.0, 1.0), 0.45));
    gl_FragColor = vec4(col, 1.0);
  }
`

export default function Sky({ color = '#4a6fa5' }) {
  const uniforms = useMemo(() => {
    const base = new THREE.Color(color)
    const hsl = {}
    base.getHSL(hsl)

    // Зенит — тот же тон, но глубже и насыщеннее; горизонт — светлее и
    // чуть теплее; земля под платформой уходит в темноту.
    const top = new THREE.Color().setHSL(
      hsl.h, Math.min(1, hsl.s * 1.25), Math.max(0.14, hsl.l * 0.8))
    const horizon = new THREE.Color().setHSL(
      (hsl.h + 0.03) % 1, Math.min(1, hsl.s * 1.05),
      Math.min(0.95, hsl.l * 1.5 + 0.34))
    const ground = new THREE.Color().setHSL(
      hsl.h, hsl.s * 0.6, Math.max(0.03, hsl.l * 0.3))
    return { top: { value: top }, horizon: { value: horizon },
             ground: { value: ground } }
  }, [color])

  return (
    <mesh scale={[-1, 1, 1]} frustumCulled={false} renderOrder={-1}>
      <sphereGeometry args={[600, 32, 24]} />
      <shaderMaterial
        key={color}
        uniforms={uniforms}
        vertexShader={VERT}
        fragmentShader={FRAG}
        depthWrite={false}
        side={THREE.BackSide}
        toneMapped={false}
      />
    </mesh>
  )
}
