import { useState, useRef, useCallback, useEffect } from 'react'

// Состояние одного строителя: его карта, его блоки, его гуляки.

// В разработке фронтенд и бэкенд на разных портах, в сборке — на одном
// адресе, поэтому база пустая.
const API = import.meta.env.VITE_API
  ?? (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')

// Блоки группируются по паре (форма + цвет) для инстансинга, попутно
// собирается множество занятых клеток.
function buildScene(blocks) {
  const byKey = new Map()
  const occupied = new Set()
  for (const b of blocks.values()) {
    const key = `${b.shape}|${b.color}|${b.role ?? 1}`
    let g = byKey.get(key)
    if (!g) {
      g = { key, shape: b.shape, color: b.color, role: b.role ?? 1, items: [] }
      byKey.set(key, g)
    }
    g.items.push(b)
    occupied.add(`${b.x},${b.z}`)
  }
  return { groups: [...byKey.values()], occupied }
}

const EMPTY_SCENE = { groups: [], occupied: new Set() }

export default function useBuilder(who, { onSay } = {}) {
  const blocksRef = useRef(new Map())
  const liveSeen = useRef(0)
  const idleCount = useRef(0)

  const [scene, setScene] = useState(EMPTY_SCENE)
  const [decorations, setDecorations] = useState([])
  const [walk, setWalk] = useState(null)
  const [level, setLevel] = useState(null)
  const [progress, setProgress] = useState(0)
  const [awaiting, setAwaiting] = useState(false)
  const [live, setLive] = useState(null)

  const say = useCallback((event) => {
    if (onSay) onSay(event, who)
  }, [onSay, who])

  const applyNewLevel = useCallback((lv) => {
    blocksRef.current.clear()
    setScene(EMPTY_SCENE)
    setDecorations([])
    setWalk(null)
    setProgress(0)
    setAwaiting(false)
    if (lv) setLevel(lv)
  }, [])

  // Перечитать карту, назначенную сервером. Нужно, когда карту сменил не
  // фронтенд, а сервер — например, при начале нового матча.
  const reload = useCallback(() => {
    fetch(`${API}/level?who=${who}`)
      .then(r => r.json())
      .then(lv => { if (lv) applyNewLevel(lv) })
      .catch(() => {})
  }, [who, applyNewLevel])

  // Что уже построено к моменту загрузки страницы: без этого перезагрузка
  // теряла бы получасовую стройку.
  useEffect(() => {
    let cancelled = false
    fetch(`${API}/level?who=${who}`)
      .then(r => r.json())
      .then(lv => {
        if (cancelled || !lv) return
        setLevel(lv)
        setProgress(lv.progress || 0)
        setAwaiting(!!lv.awaiting)
        if (lv.decorations?.length) setDecorations(lv.decorations)
        if (lv.built?.length) {
          for (const b of lv.built) {
            blocksRef.current.set(`${b.x},${b.y},${b.z}`, { ...b, shape: 'cube' })
          }
          setScene(buildScene(blocksRef.current))
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [who])

  // Достроил — запускаем гуляк. Показываем ровно ту прогулку, которой
  // критик мерил эту карту.
  useEffect(() => {
    if (!awaiting) return
    let dropped = false
    fetch(`${API}/walk?who=${who}`)
      .then(r => r.json())
      .then(d => { if (!dropped && d.ok) setWalk(d) })
      .catch(() => {})
    return () => { dropped = true }
  }, [awaiting, who])

  const handleStep = useCallback((data) => {
    if (data.world_reset) {
      applyNewLevel(data.level)
      return
    }

    if (data.live !== undefined) {
      setLive(data.live)
      for (const e of data.live?.events || []) {
        if (e.t > liveSeen.current) {
          liveSeen.current = e.t
          if (e.kind === 'invent') say('invent')
        }
      }
    }

    if (data.awaiting) {
      setAwaiting(prev => {
        if (!prev) say('finished')
        return true
      })
      return
    }

    if (typeof data.progress === 'number') setProgress(data.progress)

    if (data.blocks?.length) {
      for (const b of data.blocks) {
        blocksRef.current.set(`${b.x},${b.y},${b.z}`, {
          x: b.x, y: b.y, z: b.z, color: b.color, shape: 'cube',
          role: b.role ?? 1,
        })
      }
      setScene(buildScene(blocksRef.current))
    }

    if (data.decor?.length) setDecorations(prev => [...prev, ...data.decor])

    if (data.kind === 'move') {
      idleCount.current += 1
      if (idleCount.current % 60 === 0) say('thinking')
    }
  }, [say, applyNewLevel])

  const startNew = useCallback(() => {
    fetch(`${API}/next?who=${who}`)
      .then(r => r.json())
      .then(res => { if (res.ok) applyNewLevel(res.level) })
      .catch(() => {})
  }, [applyNewLevel, who])

  return {
    who, scene, decorations, walk, level, progress, awaiting, live,
    handleStep, startNew, reload,
  }
}
