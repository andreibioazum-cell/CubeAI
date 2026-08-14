import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { useState, useRef, useCallback, useEffect, Suspense } from 'react'
import Caine from './Caine'
import Blocks from './Blocks'
import Chat from './Chat'
import Walkers from './Walkers'
import Decorations from './Decorations'
import FrameCamera from './FrameCamera'
import { frameDistance } from './framing'
import useBuilder from './useBuilder'
import useMobile from './useMobile'
import Sky from './Sky'
import Victory from './Victory'
import Boot from './Boot'
import Music from './Music'
import { EffectComposer, Bloom, Vignette, SMAA } from '@react-three/postprocessing'
import * as THREE from 'three'
import { PHRASES, nextPhrase } from './phrases'
import { api, boot } from './engine'
import './ui.css'

const FIELD = 100
const MAX_MESSAGES = 40

// Платформы стоят на расстоянии, которого хватает, чтобы постройки не
// налезали друг на друга: карта бывает до 78 клеток в поперечнике.
const PLATFORM_GAP = 130

// Чем кончился раунд. Ничья и незачёт существуют по-настоящему: при них
// счёт остаётся прежним, и без подписи это неотличимо от поломки.
const ROUND_RESULT = {
  caine: 'Раунд взял Кейн',
  abel: 'Раунд взял Авель',
  'ничья': 'Ничья — счёт не изменился',
  'нет карты': 'Раунд не засчитан',
}

// Тени и постобработка стоят дорого. На слабой машине их можно выключить
// адресом ?plain=1 — картинка станет проще, но всё остальное работает.
const PLAIN = new URLSearchParams(window.location.search).has('plain')

// Обратный ключ: на телефоне красоту выключает уже сам код, а ?fancy=1
// возвращает её тем, у кого аппарат тянет.
const FORCE_FANCY = new URLSearchParams(window.location.search).has('fancy')

// Превью экрана итога: ?victory=1. Ждать пять раундов, чтобы посмотреть
// на вёрстку, — плохой способ её настраивать.
const PREVIEW = new URLSearchParams(window.location.search).get('victory')

// Полоса достройки под своим строителем: красная у Кейна, синяя у Авеля.
// Заменила панель с двумя десятками цифр — на показе важно ровно одно:
// кто на сколько построил.
function Progress({ who, progress }) {
  const pct = Math.round((progress || 0) * 100)
  return (
    <div className={`pbar-row ${who}`}>
      <div className="pbar"><i style={{ width: `${pct}%` }} /></div>
      <span className="pct outline-thin">{pct}%</span>
    </div>
  )
}

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
  const [stage, setStage] = useState('Просыпаюсь…')
  const [bootError, setBootError] = useState(null)
  const [started, setStarted] = useState(false)
  const mobile = useMobile()

  // Карта теней 1536×1536, bloom и сглаживание на телефоне съедают кадр
  // целиком. Тот же вид без них выглядит проще, но двигается.
  const fancy = FORCE_FANCY || (!PLAIN && !mobile)

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

  // Пока движок не поднялся, показывать нечего: карт ещё нет.
  useEffect(() => {
    boot(setStage)
      .then(() => setStarted(true))
      .catch(err => setBootError(err.message))
  }, [])

  useEffect(() => {
    if (!started) return
    api('/builders').then(setBuilders).catch(() => {})
  }, [started])

  const hasAbel = !!builders?.duel && builders.builders.length > 1
  // Раунд общий, поэтому и кнопка одна: жать по разу за каждого было
  // лишней работой, а начать заново у одного, пока второй ещё строит,
  // означало бы выбросить его недостроенную карту.
  const bothDone = caine.awaiting && (!hasAbel || abel.awaiting)

  // Счёт подтягивается, только когда оба закончили: раунд засчитывается по
  // готовым картам, а не по недостроенным.
  //
  // Опрос, а не один запрос. Судейство — самая тяжёлая операция за весь
  // раунд: одни и те же гуляки обходят обе карты, потом критик считает обе,
  // потом проигравший забирает планировку. Единственная попытка означала,
  // что любой сбой оставит счёт замершим навсегда, и притом молча —
  // прежний `.catch(() => {})` глотал даже причину.
  useEffect(() => {
    if (!bothDone || !hasAbel) return
    let stop = false
    let tries = 0

    const again = () => {
      if (stop || ++tries >= 12) return
      setTimeout(ask, 1500)
    }
    const ask = () => {
      api('/duel')
        .then(d => {
          if (stop) return
          if (d?.ok) setDuel(d)
          else again()
        })
        .catch(err => {
          console.error('счёт раунда не сошёлся:', err.message)
          again()
        })
    }

    ask()
    return () => { stop = true }
  }, [bothDone, hasAbel])

  // Сервер считает раунды по завершении, поэтому во время стройки второго
  // раунда duel.round всё ещё равен единице. Зрителю нужен номер того
  // раунда, который идёт сейчас, — иначе счётчик выглядит зависшим.
  const totalRounds = duel?.match_rounds ?? 5
  const playing = Math.min(
    (duel?.round ?? 0) + (bothDone || duel?.over ? 0 : 1), totalRounds)
  const startRound = useCallback(() => {
    // Исход прошлого раунда стирается сразу: иначе, пока судится новый,
    // под кнопкой висел бы результат предыдущего — а он уже не про то,
    // что зритель видит на платформах.
    setDuel(prev => (prev ? { ...prev, last: null } : prev))
    caine.startNew()
    if (hasAbel) abel.startNew()
  }, [caine, abel, hasAbel])

  const restartMatch = useCallback(() => {
    api('/duel/reset')
      .then(d => {
        if (!d.ok) return
        setDuel(d)
        // Карты уже сменил движок, поэтому здесь только подхватываем их.
        caine.reload()
        if (hasAbel) abel.reload()
      })
      .catch(err => console.error('матч не перезапустился:', err.message))
  }, [caine, abel, hasAbel])
  const shown = focus === 'abel' && hasAbel ? abel : caine
  const sky = shown.level?.sky || '#111111'
  const focusX = focus === 'abel' && hasAbel ? PLATFORM_GAP : 0

  // Пределы приближения зависят от размера постройки: у мелкой карты те же
  // метры — это уже «внутри стены», у крупной — «слишком далеко». Считаются
  // по той же формуле, что и наводка камеры, иначе на узком экране рамка
  // упиралась бы в собственный предел отдаления.
  const b = shown.level?.bounds
  const fit = b
    ? frameDistance(b, window.innerWidth / window.innerHeight)
    : 60
  const near = Math.max(12, fit * 0.28)
  const far = fit * 2.6

  if (!started) return <Boot stage={stage} error={bootError} />

  return (
    <div style={{ width: '100vw', height: '100vh', background: sky }}>
      <Chat messages={messages} />
      {/* Ставится после загрузки движка: во время неё канал занят Python. */}
      <Music src={`${import.meta.env.BASE_URL || '/'}audio/theme.mp3`} />

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
          <Progress who="caine" progress={caine.progress} />
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
            <Progress who="abel" progress={abel.progress} />
          </div>
        )}
      </div>

      {bothDone && !duel?.over && (
        <div className="rebuild spray">
          <div className="hint outline-thin">
            {hasAbel
              ? (ROUND_RESULT[duel?.last?.winner] ?? 'Считаю раунд…')
              : 'Кейн закончил и ждёт'}
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
          Движок споткнулся — перезагрузи страницу
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
        shadows={fancy}
        camera={{ position: [0, 60, 70], fov: 50, far: 1600 }}
        /* Плотность экрана телефона доходит до 3: без потолка сцена
           рисуется в 1179×2556 настоящих пикселей, вчетверо больше
           нужного. Полтора — предел, за которым разница уже не видна. */
        dpr={mobile ? [1, 1.5] : [1, 2]}
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
          castShadow={fancy}
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
        {fancy && (
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
