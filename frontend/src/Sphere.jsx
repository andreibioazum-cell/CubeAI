export default function Sphere({ position, color }) {
  return (
    <mesh position={position}>
      <sphereGeometry args={[0.5, 16, 16]} />
      <meshStandardMaterial color={color} />
    </mesh>
  )
}