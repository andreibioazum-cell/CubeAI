import * as THREE from 'three'

// Текстуры блоков: по одной на пару (стиль × роль), 21 штука.

const ROLES = ['wall', 'floor', 'accent']
const STYLE_KEYS = ['cave', 'castle', 'mansion', 'island', 'circus',
                    'candy', 'city']

const SIZE = 64          // размер, под который рисуются текстуры

// Насколько сильно палитра перекрашивает текстуру. 0 — видна только
// текстура, 1 — только цвет карты. Половина оставляет узнаваемой и фактуру
// стиля, и цвет, который Кейн вывел эволюцией.
const TINT = 0.5
const cache = new Map()  // готовые смеси
const files = new Map()  // загруженные картинки (или null, если файла нет)

function path(style, role) {
  return `/tex/${style}_${role}.png`
}

// Загружаем один раз и запоминаем результат, включая отрицательный:
// повторно дёргать сервер за отсутствующим файлом незачем.
function loadImage(style, role) {
  const key = `${style}_${role}`
  if (files.has(key)) return files.get(key)
  const p = new Promise(resolve => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)
    img.src = path(style, role)
  })
  files.set(key, p)
  return p
}

/**
 * Текстура для роли под заданный состав стилей.
 * Возвращает THREE.Texture или null, если ни одного файла ещё нет.
 */
export async function mixedTexture(mix, role, tint = null) {
  const parts = Object.entries(mix || {})
    .filter(([k]) => STYLE_KEYS.includes(k))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
  if (!parts.length) return null

  const key = `${role}|${tint || '-'}|`
    + parts.map(([k, v]) => `${k}:${v.toFixed(2)}`).join(',')
  if (cache.has(key)) return cache.get(key)

  const images = await Promise.all(parts.map(([k]) => loadImage(k, role)))
  const usable = parts
    .map(([k, w], i) => ({ k, w, img: images[i] }))
    .filter(p => p.img)
  if (!usable.length) {
    cache.set(key, null)
    return null
  }

  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = SIZE
  const ctx = canvas.getContext('2d')

  // Сводим слои по долям: первый кладётся целиком, следующие поверх
  // с прозрачностью, равной их доле в оставшемся весе.
  let used = 0
  for (const p of usable) {
    const share = p.w / usable.reduce((s, q) => s + q.w, 0)
    ctx.globalAlpha = used === 0 ? 1 : share / (used + share)
    ctx.drawImage(p.img, 0, 0, SIZE, SIZE)
    used += share
  }
  ctx.globalAlpha = 1

  // Палитра поверх фактуры: режим «color» берёт от заливки тон и
  // насыщенность, а светлоту оставляет от текстуры — то есть рисунок
  // и объём сохраняются, меняется только цвет.
  if (tint) {
    ctx.globalCompositeOperation = 'color'
    ctx.globalAlpha = TINT
    ctx.fillStyle = tint
    ctx.fillRect(0, 0, SIZE, SIZE)
    ctx.globalAlpha = 1
    ctx.globalCompositeOperation = 'source-over'
  }

  const tex = new THREE.CanvasTexture(canvas)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.magFilter = THREE.NearestFilter   // пиксель-арт не размывается
  tex.minFilter = THREE.NearestMipmapLinearFilter
  tex.colorSpace = THREE.SRGBColorSpace
  cache.set(key, tex)
  return tex
}

export { ROLES, STYLE_KEYS, SIZE }
