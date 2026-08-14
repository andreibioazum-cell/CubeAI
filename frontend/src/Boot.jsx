// Экран ожидания, пока Python приезжает в браузер.

export default function Boot({ stage, error }) {
  return (
    <div className="boot">
      <div className="boot-title outline">
        Caine<span className="b">AI</span>
      </div>
      {error ? (
        <>
          <div className="boot-sub outline">Не завелось</div>
          <div className="boot-error">{error}</div>
        </>
      ) : (
        <>
          <div className="boot-sub outline">{stage}</div>
          <div className="boot-bar"><i /></div>
          <div className="boot-note">
            Кейн и Авель считают прямо у тебя во вкладке — сервера нет.
            Первый запуск качает Python, дальше страница открывается из кеша.
          </div>
        </>
      )}
    </div>
  )
}
