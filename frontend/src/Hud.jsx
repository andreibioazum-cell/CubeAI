const panel = {
  position: 'absolute',
  top: 16,
  right: 16,
  zIndex: 10,
  width: 250,
  padding: '10px 12px',
  background: 'rgba(0,0,0,0.72)',
  border: '2px solid #444',
  color: '#e8e8e8',
  fontFamily: '"Courier New", monospace',
  fontSize: 12,
  lineHeight: 1.6,
}

const HYBRID_LABEL = {
  pure: 'чистый стиль',
  blend: 'смешанный гибрид',
  zoned: 'сшитый гибрид',
  evolved: 'найдено эволюцией',
  designed: 'спроектировано сетью',
}

function Row({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: '#8f8f8f' }}>{label}</span>
      <span style={{ textAlign: 'right' }}>{value}</span>
    </div>
  )
}

function Live({ live }) {
  if (!live || !live.running) return null
  const plus = (n) => (n > 0 ? ` +${n}` : '')
  return (
    <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid #444' }}>
      <div style={{ color: '#7fd77f', marginBottom: 4 }}>
        придумывает прямо сейчас
      </div>
      <Row label="ниш открыто" value={
        <>{live.cells}<span style={{ color: '#7fd77f' }}>{plus(live.cells_gained)}</span></>
      } />
      <Row label="средний счёт" value={
        <>{live.mean_score}
          {live.mean_gained > 0 && (
            <span style={{ color: '#7fd77f' }}> +{live.mean_gained.toFixed(3)}</span>
          )}
        </>
      } />
      <Row label="новых элементов" value={live.invented} />
      <Row label="словарь" value={`11 + ${live.pool}`} />
    </div>
  )
}

export default function Hud({ level, progress, live, walk, duel }) {
  if (!level) return null
  const d = level.descriptor || {}
  const pct = Math.round((progress || 0) * 100)

  return (
    <div style={panel}>
      {/* Название по характеру, а не по родословной: «Особняк × Цирк»
          ничего не говорит о том, чем постройка стала. */}
      <div style={{ color: '#ffff55', fontSize: 14, marginBottom: 2 }}>
        {level.found_style || level.style_name}
      </div>
      {level.found_style && (
        <div style={{ color: '#6f6f6f', fontSize: 11, marginBottom: 6 }}>
          из {level.style_name}
        </div>
      )}

      {!level.legacy && (
        <div style={{ color: '#8f8f8f', marginBottom: 8 }}>
          карта #{level.index} · {HYBRID_LABEL[level.hybrid] || level.hybrid}
          {level.mood && (
            <div style={{ color: level.palette?.accent || '#8f8f8f' }}>
              настроение: {level.mood}
            </div>
          )}
        </div>
      )}

      <div style={{
        height: 8, background: '#222', border: '1px solid #555', marginBottom: 8,
      }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: level.palette?.accent || '#ffff55',
          transition: 'width 0.2s linear',
        }} />
      </div>
      <Row label="построено" value={`${pct}%`} />

      {!level.legacy && (
        <>
          <Row label="блоков" value={level.blocks} />
          <Row label="декора" value={level.decorations_total} />
          <Row label="модулей" value={d.size} />
          <Row label="глубина" value={d.depth} />
          <Row label="ветвистость" value={d.branching} />
          <Row label="тупиков" value={d.dead_ends} />
          <Row label="проходимость" value={`${Math.round((d.reachability ?? 0) * 100)}%`} />
          {level.score != null
            ? <Row label="оценка критика" value={level.score} />
            : <Row label="новизна" value={level.novelty} />}
        </>
      )}

      {duel?.last && (
        <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid #444' }}>
          <div style={{ color: '#ff9f6f', marginBottom: 4 }}>
            раунд {duel.round}
          </div>
          <Row label="Кейн" value={duel.last.a?.score ?? '—'} />
          <Row label="Авель" value={duel.last.b?.score ?? '—'} />
          <Row label="взял раунд" value={
            duel.last.winner === 'caine' ? 'Кейн'
              : duel.last.winner === 'abel' ? 'Авель' : duel.last.winner
          } />
          <Row label="счёт" value={`${duel.wins?.caine ?? 0} : ${duel.wins?.abel ?? 0}`} />
          {duel.last.stolen && (
            <Row label="перенял" value={
              duel.last.stolen.kept?.length
                ? `${duel.last.stolen.kept.length} планировк.`
                : (duel.last.stolen.why || '—')
            } />
          )}
        </div>
      )}

      {walk && (
        <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid #444' }}>
          <div style={{ color: '#8fd0ff', marginBottom: 4 }}>
            гуляки в карте
          </div>
          <Row label="их в карте" value={walk.walkers} />
          <Row label="обошли карту" value={`${Math.round(walk.coverage * 100)}%`} />
          <Row label="нашли сундук" value={`${Math.round(walk.reach * 100)}%`} />
        </div>
      )}

      <Live live={live} />

      {level.legacy && (
        <div style={{ color: '#ff8080', marginTop: 6 }}>
          старый DQN · паттерн {level.pattern}
        </div>
      )}
    </div>
  )
}
