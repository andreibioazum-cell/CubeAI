// Мост к Python, который работает прямо во вкладке.
//
// Раньше здесь был fetch к FastAPI. Теперь тот же самый бэкенд крутится
// у зрителя в браузере через Pyodide: сервер не нужен вообще, а у каждого
// открывшего страницу — своя стройка, свой архив и свой счёт.
//
// Наружу торчит `api(route, params)` с той же подписью, что была у HTTP,
// поэтому компонентам всё равно, откуда приходит ответ.

const PYODIDE_VERSION = '0.28.0'
const CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`
const BASE = import.meta.env.BASE_URL || '/'

// Серверный режим — тот же фронтенд, но считает FastAPI, а не вкладка.
//   VITE_SERVER=1                      ходить туда же, откуда пришла страница
//   VITE_API=http://127.0.0.1:8000     ходить по указанному адресу
// Второе нужно в разработке: правку в Python видно после перезапуска
// uvicorn, без пересборки и без повторной загрузки Pyodide.
// Пустая строка — валидный адрес «тот же сервер», поэтому режим проверяется
// на null, а не на истинность: `if (REMOTE)` при VITE_SERVER=1 был бы ложным
// и серверная ветка вырезалась бы как недостижимая.
const REMOTE = import.meta.env.VITE_SERVER
  ? ''
  : (import.meta.env.VITE_API || null)
const ON_SERVER = REMOTE !== null

let pyCall = null
let booting = null

// Питон однопоточный: два одновременных вызова из разных компонентов
// раскладывались бы в один и тот же интерпретатор внахлёст. Очередь
// гарантирует, что вызовы идут строго по одному.
let chain = Promise.resolve()

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script')
    el.src = src
    el.onload = resolve
    el.onerror = () => reject(new Error(`не загрузился ${src}`))
    document.head.appendChild(el)
  })
}

export function boot(onStage = () => {}) {
  if (booting) return booting
  booting = (async () => {
    if (ON_SERVER) {
      onStage('Подключаюсь к серверу…')
      const res = await fetch(`${REMOTE}/builders`)
      if (!res.ok) throw new Error(`сервер не отвечает: HTTP ${res.status}`)
      return { ok: true }
    }
    onStage('Загружаю Python…')
    await loadScript(CDN + 'pyodide.js')
    const py = await globalThis.loadPyodide({ indexURL: CDN })

    onStage('Загружаю numpy…')
    await py.loadPackage('numpy')

    onStage('Распаковываю движок…')
    const manifest = await (await fetch(`${BASE}py/manifest.json`)).json()
    try { py.FS.mkdir('/work') } catch { /* уже есть */ }
    await Promise.all(manifest.files.map(async (name) => {
      const res = await fetch(`${BASE}py/${name}`)
      if (!res.ok) throw new Error(`нет ${name}`)
      py.FS.writeFile('/work/' + name, new Uint8Array(await res.arrayBuffer()))
    }))

    onStage('Бужу Кейна и Авеля…')
    pyCall = py.runPython(
      "import sys, os\n" +
      "sys.path.insert(0, '/work')\n" +
      "os.chdir('/work')\n" +
      "import web_engine\n" +
      "web_engine.call")

    // Первый вызов поднимает обоих строителей и проектирует им по карте —
    // это самая долгая операция за всю загрузку.
    const res = JSON.parse(pyCall('/boot', JSON.stringify({ dir: '/work' })))
    if (!res.ok) throw new Error(res.error || 'движок не поднялся')
    return res
  })()
  return booting
}

export function ready() {
  return ON_SERVER || pyCall !== null
}

async function remote(route, params) {
  const qs = new URLSearchParams(params).toString()
  const res = await fetch(`${REMOTE}${route}${qs ? '?' + qs : ''}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function api(route, params = {}) {
  const run = async () => {
    if (ON_SERVER) return remote(route, params)
    if (!pyCall) await boot()
    const raw = pyCall(route, JSON.stringify(params))
    const data = JSON.parse(raw)
    if (data && data.error) throw new Error(data.error)
    return data
  }
  // Звено цепи не должно рваться: иначе одна ошибка застопорила бы все
  // последующие вызовы.
  const next = chain.then(run, run)
  chain = next.catch(() => {})
  return next
}
