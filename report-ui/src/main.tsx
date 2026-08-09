import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { loadReport } from './data'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App data={loadReport()} />
  </StrictMode>,
)
