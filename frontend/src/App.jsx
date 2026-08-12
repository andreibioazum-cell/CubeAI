import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { useState, useRef, useCallback, useEffect, Suspense } from 'react'
import Caine from './Caine'
import Blocks from './Blocks'
import Chat from './Chat'
import Hud from './Hud'
import Walkers from './Walkers'
import Decorations from './Decorations'
import FrameCamera from './FrameCamera'
import useBuilder from './useBuilder'
import Sky from './Sky'
import Victory from './Victory'
import { EffectComposer, Bloom, Vignette, SMAA } from '@react-three/postprocessing'
import * as THREE from 'three'
import { PHRASES, nextPhrase } from './phrases'
import './ui.css'

// В разработке фронтенд и бэкенд на разных портах, в сборке — на одном
// адресе, поэтому база пустая.
const API = import.meta.env.VITE_API
  ?? (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')
const FIELD = 100
const MAX_MESSAGES = 40

// Платформы стоят на расстоянии, которого хватает, чтобы постройки не
// налезали друг на друга: карта бывает до 78 клеток в поперечнике.
const PLATFORM_GAP = 130

// Тени и постобработка стоят дорого. На слабой машине их можно выключить
// адресом ?plain=1 — картинка станет проще, но всё остальное работает.
const FANCY = !new URLSearchParams(window.location.search).has('plain')

// Превью экрана итога: ?victory=1. Ждать пять раундов, чтобы посмотреть
// на вёрстку, — плохой способ её настраивать.
const PREVIEW = new URLSearchParams(window.location.search).get('victory')

function Platform({ x, dim }) {
  return (
    <group position={[x, 0, 0]}>
      <gridHelper args={[FIELD, FIELD / 2, dim ? '#3a3a4a' : '#5a5a72',
                         dim ? '#2c2c3a' : '#454558']} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}
            receiveShadow>
        <planeGeometry args={[FIELD, FIELD]} />
        <meshStandardMaterial color={dim ? '#2a2a38' : '#3d3d50'}
                              roughness={0.95} />
      </mesh>
    </group>
  )
}

export default function App() {
  const controlsRef = useRef()
  const [messages, setMessages] = useState([`Кейн: ${PHRASES.welcome[0]}`])
  const [online, setOnline] = useState(true)
  const [focus, setFocus] = useState('caine')
  const [duel, setDuel] = useState(null)
  const [builders, setBuilders] = useState(null)

  // Говорящих теперь двое, поэтому имя едет в самой строке, а не рисуется
  // компонентом чата.
  const say = useCallback((event, who) => {
    const phrase = nextPhrase(event)
    if (!phrase) return
    const name = who === 'abel' ? 'Авель' : 'Кейн'
    setMessages(prev => [...prev, `${name}: ${phrase}`].slice(-MAX_MESSAGES))
  }, [])

  const caine = useBuilder('caine', { onSay: say })
  const abel = useBuilder('abel', { onSay: say })

  const handleConnection = useCallback(ok => {
    setOnline(prev => (prev === ok ? prev : ok))
  }, [])

  useEffect(() => {
    fetch(`${API}/builders`).then(r => r.json()).then(setBuilders).catch(() => {})
  }, [])

  // Счёт противостояния подтягивается, только когда оба закончили: раунд
  // засчитывается по готовым картам, а не по недостроенным.
  useEffect(() => {
    if (!caine.awaiting || !abel.awaiting) return
    let dropped = false
    fetch(`${API}/duel`)
      .then(r => r.json())
      .then(d => { if (!dropped && d.ok) setDuel(d) })
      .catch(() => {})
    return () => { dropped = true }
  }, [caine.awaiting, abel.awaiting])

  const hasAbel = !!builders?.duel && builders.builders.length > 1
  // Раунд общий, поэтому и кнопка одна: жать по разу за каждого было
  // лишней работой, а начать заново у одного, пока второй ещё строит,
  // означало бы выбросить его недостроенную карту.
  const bothDone = caine.awaiting && (!hasAbel || abel.awaiting)

  // Сервер считает раунды по завершении, поэтому во время стройки второго
  // раунда duel.round всё ещё равен единице. Зрителю нужен номер того
  // раунда, который идёт сейчас, — иначе счётчик выглядит зависшим.
  const totalRounds = duel?.match_rounds ?? 5
  const playing = Math.min(
    (duel?.round ?? 0) + (bothDone || duel?.over ? 0 : 1), totalRounds)
  const startRound = useCallback(() => {
    caine.startNew()
    if (hasAbel) abel.startNew()
  }, [caine, abel, hasAbel])

  const restartMatch = useCallback(() => {
    fetch(`${API}/duel/reset`)
      .then(r => r.json())
      .then(d => {
        if (!d.ok) return
        setDuel(d)
        // Карты уже сменил сервер, поэтому здесь только подхватываем их.
        caine.reload()
        if (hasAbel) abel.reload()
      })
      .catch(() => {})
  }, [caine, abel, hasAbel])
  const shown = focus === 'abel' && hasAbel ? abel : caine
  const sky = shown.level?.sky || '#111111'
  const focusX = focus === 'abel' && hasAbel ? PLATFORM_GAP : 0

  // Пределы приближения зависят от размера постройки: у мелкой карты те же
  // метры — это уже «внутри стены», у крупной — «слишком далеко».
  const b = shown.level?.bounds
  const span = b ? Math.max(b.maxx - b.minx, b.maxz - b.minz, 24) : 60
  const near = Math.max(12, span * 1.15 * 0.28)
  const far = span * 1.15 * 2.6

  return (
    <div style={{ width: '100vw', height: '100vh', background: sky }}>
      <Chat messages={messages} />
      <Hud level={shown.level} progress={shown.progress} live={shown.live}
           walk={shown.walk} duel={duel} />

      <div className="topbar spray">
        <div className="side">
          <button
            className={`builder-btn outline caine left${focus === 'caine' ? '' : ' off'}`}
            onClick={() => setFocus('caine')}
          >
            Caine
          </button>
          <div className="theme">
            {caine.level?.found_style || caine.level?.style_name || '—'}
            {caine.level?.found_style && (
              <span className="sub">из {caine.level.style_name}</span>
            )}
          </div>
        </div>

        {hasAbel && (
          <div className="score">
            <div className="digits outline">
              {duel?.wins?.caine ?? 0} : {duel?.wins?.abel ?? 0}
            </div>
            <div className="label">
              раунд {playing} из {totalRounds}
            </div>
          </div>
        )}

        {hasAbel && (
          <div className="side">
            <button
              className={`builder-btn outline abel right${focus === 'abel' ? '' : ' off'}`}
              onClick={() => setFocus('abel')}
            >
              Abel
            </button>
            <div className="theme">
              {abel.level?.found_style || abel.level?.style_name || '—'}
              {abel.level?.found_style && (
                <span className="sub">из {abel.level.style_name}</span>
              )}
            </div>
          </div>
        )}
      </div>

      {bothDone && !duel?.over && (
        <div className="rebuild spray">
          <div className="hint outline-thin">
            {hasAbel ? 'Оба закончили — раунд сыгран' : 'Кейн закончил и ждёт'}
          </div>
          <button
            className="outline"
            onClick={startRound}
            style={{
              background: focus === 'abel'
                ? 'linear-gradient(#6fa8ff, #3d8bff)'
                : 'linear-gradient(#ff6a5e, #ff4438)',
              boxShadow: `0 6px 0 ${focus === 'abel' ? '#1a4fb8' : '#b81f18'},`
                + ' 0 0 0 4px #16121c, 0 12px 26px rgba(0,0,0,0.45)',
            }}
          >
            {hasAbel ? 'Следующий раунд' : 'Построить снова'}
          </button>
        </div>
      )}

      {!online && (
        <div className="offline spray">
          Бэкенд недоступен — запусти uvicorn main:app
        </div>
      )}

      <Victory
        duel={PREVIEW
          ? { over: true, match_rounds: 5, champion: PREVIEW === 'abel' ? 'abel'
              : PREVIEW === 'draw' ? 'ничья' : 'caine',
              wins: PREVIEW === 'abel' ? { caine: 1, abel: 4 }
                : PREVIEW === 'draw' ? { caine: 2, abel: 2 } : { caine: 4, abel: 1 } }
          : duel}
        onRestart={PREVIEW ? () => {} : restartMatch}
      />

      <Canvas
        shadows={FANCY}
        camera={{ position: [0, 60, 70], fov: 50, far: 1600 }}
        gl={{ antialias: false, toneMapping: THREE.ACESFilmicToneMapping,
              toneMappingExposure: 1.45 }}
      >
        <color attach="background" args={[sky]} />
        {/* Туман по цвету горизонта и далеко: близкий съедал половину
            постройки, ради которой всё и затевалось. */}
        <fog attach="fog" args={[sky, 260, 900]} />
        <Sky color={sky} />
        {/* Свет: одно «солнце» с тенями плюс мягкая подсветка снизу.
            Солнце светит сбоку и сверху — при отвесном свете грани куба
            освещены одинаково, и постройка выглядит плоской. Тень делает
            вертикаль читаемой лучше любого освещения. */}
        <hemisphereLight args={[sky, '#2c2c3a', 0.8]} />
        <ambientLight intensity={0.45} />
        <directionalLight
          position={[70, 110, 55]}
          intensity={2.1}
          color="#fff2df"
          castShadow={FANCY}
          shadow-mapSize={[1536, 1536]}
          shadow-bias={-0.0006}
          shadow-normalBias={0.03}
        >
          {/* Область тени охватывает обе платформы: карта бывает до 78
              клеток, а между платформами ещё 130. */}
          <orthographicCamera attach="shadow-camera"
                              args={[-190, 190, 190, -190, 1, 420]} />
        </directionalLight>
        <directionalLight position={[-60, 45, -50]} intensity={0.45}
                          color="#9fb8ff" />

        <FrameCamera bounds={shown.level?.bounds} controls={controlsRef}
                     platformX={focusX} />

        <group position={[0, 0, 0]}>
          <Suspense fallback={null}>
            <Caine onStep={caine.handleStep} onConnection={handleConnection}
                   who="caine" />
            <Decorations decorations={caine.decorations}
                         palette={caine.level?.palette} />
          </Suspense>
          <Blocks groups={caine.scene.groups}
                  mix={caine.level?.style_mix} />
          <Walkers walk={caine.walk} palette={caine.level?.palette} />
        </group>

        {hasAbel && (
          <group position={[PLATFORM_GAP, 0, 0]}>
            <Suspense fallback={null}>
              {/* Пока это та же модель Кейна, только перекрашенная:
                  своя модель Авеля появится позже. */}
              <Caine onStep={abel.handleStep} onConnection={handleConnection}
                     who="abel" tint="#5aa9ff" />
              <Decorations decorations={abel.decorations}
                           palette={abel.level?.palette} />
            </Suspense>
            <Blocks groups={abel.scene.groups}
                    mix={abel.level?.style_mix} />
            <Walkers walk={abel.walk} palette={abel.level?.palette} />
          </group>
        )}

        {/* Только поворот и приближение. Сдвиг выключен: с ним зритель за
            пару секунд уезжает в пустоту и не понимает, как вернуться.
            Угол подъёма ограничен — сверху постройка выглядит плоской,
            снизу камера уходит под землю. */}
        <OrbitControls
          ref={controlsRef}
          enablePan={false}
          minPolarAngle={Math.PI * 0.12}
          maxPolarAngle={Math.PI * 0.46}
          enableDamping
          dampingFactor={0.08}
          rotateSpeed={0.55}
          zoomSpeed={0.8}
          minDistance={near}
          maxDistance={far}
        />

        <Platform x={0} dim={focus !== 'caine'} />
        {hasAbel && <Platform x={PLATFORM_GAP} dim={focus !== 'abel'} />}

        {/* Bloom по яркому: светятся акценты, гуляки и небо у горизонта.
            Порог высокий намеренно — при низком расплывается вся постройка
            и пиксельные текстуры превращаются в кисель. */}
        {FANCY && (
          <EffectComposer disableNormalPass multisampling={0}>
            <Bloom intensity={0.55} luminanceThreshold={0.62}
                   luminanceSmoothing={0.22} mipmapBlur radius={0.7} />
            <Vignette offset={0.42} darkness={0.32} />
            <SMAA />
          </EffectComposer>
        )}
      </Canvas>
    </div>
  )
}
