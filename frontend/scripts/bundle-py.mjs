// Собрать питоновскую часть в public/py для запуска в браузере.
//
// Vite копирует public как есть, поэтому после сборки эти файлы лежат рядом
// с index.html и подтягиваются Pyodide прямо из вкладки.
//
// Скрипт на Node, а не на Python, хотя копирует именно Python: на билд-
// сервере (Netlify и подобные) интерпретатор может называться python3,
// python или отсутствовать вовсе, а node там есть по определению —
// без него нечем собирать фронтенд.

import { statSync, mkdirSync, rmSync, copyFileSync, writeFileSync }
  from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = join(HERE, '..', '..', 'backend')
const DST = join(HERE, '..', 'public', 'py')

// Только то, что нужно для показа. Обучение, калибровки и торч сюда не
// едут: designer.pt требует PyTorch, которого в Pyodide нет, а без него
// карты берутся из архива — ровно как при CAINE_SOURCE=auto на сервере.
const CODE = [
  'modules.py', 'levelgen.py', 'genome.py', 'hands.py', 'critic.py',
  'walkers.py', 'archive.py', 'modgen.py', 'props.py', 'styles_found.py',
  'evolve.py', 'duel.py', 'world.py', 'web_engine.py',
]

const DATA = [
  'archive.json', 'archive_abel.json', 'invented_modules.json',
  'invented_props.json', 'styles_found.json', 'walker_brain.npz',
]

rmSync(DST, { recursive: true, force: true })
mkdirSync(DST, { recursive: true })

const files = []
let total = 0
for (const name of [...CODE, ...DATA]) {
  const src = join(SRC, name)
  let size
  try {
    size = statSync(src).size
  } catch {
    console.error(`нет файла ${name} — сборка остановлена`)
    process.exit(1)
  }
  copyFileSync(src, join(DST, name))
  files.push(name)
  total += size
}

writeFileSync(join(DST, 'manifest.json'),
              JSON.stringify({ files }, null, 1), 'utf8')

console.log(`public/py: ${files.length} файлов, ${Math.round(total / 1024)} КБ`)
