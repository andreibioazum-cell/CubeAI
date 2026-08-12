import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import PropCatalog from './PropCatalog.jsx'

// Каталог придуманного реквизита: ?props=1. Отдельный вид нужен потому,
// что на общем плане предмет ростом в полтора блока не отличить от акцента
// здания — а проверять надо именно предметы.
const showProps = new URLSearchParams(window.location.search).has('props')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {showProps ? <PropCatalog /> : <App />}
  </StrictMode>,
)
