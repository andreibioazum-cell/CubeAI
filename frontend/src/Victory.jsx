// Экран итога матча: красная пелена наплывает, показывает счёт и чемпиона.

export default function Victory({ duel, onRestart }) {
  if (!duel?.over) return null

  const wins = duel.wins || {}
  const champ = duel.champion
  const draw = champ === 'ничья' || !champ
  const name = champ === 'abel' ? 'Abel' : 'Caine'

  return (
    <div className="victory spray">
      <div className="victory-inner">
        <div className="victory-title outline">
          {draw ? 'Ничья' : 'Победа'}
        </div>

        <div className="victory-score outline">
          {wins.caine ?? 0} : {wins.abel ?? 0}
        </div>

        {!draw && (
          <div className={`builder-btn outline ${champ} left victory-badge`}>
            {name}
          </div>
        )}

        <div className="victory-sub outline-thin">
          матч из {duel.match_rounds} раундов сыгран
        </div>

        <button className="victory-again outline" onClick={onRestart}>
          Играть снова
        </button>
      </div>
    </div>
  )
}
