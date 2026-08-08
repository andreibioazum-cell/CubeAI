export default function Cone({ position, color }) {
  return (
    <mesh position={position}>
      <coneGeometry args={[0.5, 1, 16]} />
      <meshStandardMaterial color={color} />
    </mesh>
  )
}