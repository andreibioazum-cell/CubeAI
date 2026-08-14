// Как поставить камеру, чтобы постройка влезла в кадр и заняла его целиком.
//
// Поле зрения задаётся по вертикали, поэтому узкое место зависит от экрана.
// На мониторе ширина влезает сама собой. На телефоне в портретной
// ориентации горизонталь становится ограничением: чтобы вместить широкую
// постройку, камера отъезжала так далеко, что постройка превращалась
// в полоску посреди пустого неба.
//
// Решение — смотреть вдоль длинной стороны. Тогда длина уходит в глубину
// кадра и ложится на высоту экрана, а поперёк остаётся короткая сторона.

export const MIN_SPAN = 24
export const FOV = 50     // должен совпадать с camera.fov в App

// Камера поднята примерно на 31° над горизонтом, поэтому глубина
// проецируется на экран короче своей настоящей длины.
const SQUASH = 0.55

function need(across, deep, aspect) {
  const halfV = Math.tan((FOV / 2) * Math.PI / 180)
  const halfH = halfV * Math.max(aspect, 0.2)
  return Math.max((across / 2) / halfH, (deep / 2) * SQUASH / halfV) * 1.08
}

export function framing(bounds, aspect) {
  const spanX = Math.max(bounds.maxx - bounds.minx, MIN_SPAN)
  const spanZ = Math.max(bounds.maxz - bounds.minz, MIN_SPAN)

  // Прежняя формула на широком экране давала хорошую рамку — она остаётся
  // нижней границей, чтобы привычный вид на мониторе не изменился.
  const floor = Math.max(spanX, spanZ) * 1.15
  const front = Math.max(floor, need(spanX, spanZ, aspect))
  const side = Math.max(floor, need(spanZ, spanX, aspect))

  return side < front
    ? { dist: side, sideways: true }
    : { dist: front, sideways: false }
}

export function frameDistance(bounds, aspect) {
  return framing(bounds, aspect).dist
}
