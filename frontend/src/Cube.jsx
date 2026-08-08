export default function Cube({ position, color }) {
    return (
        <mesh position={position}>
            <boxGeometry args={[1, 1, 1]} />
            <meshStandardMaterial color={color} />
        </mesh>

    )
}