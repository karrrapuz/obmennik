import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/global.css'
import './styles/press-feedback.css'
import './styles/input-behavior.css'
import App from './App.tsx'
import { AuthProvider } from './auth/AuthProvider'
import { initializeTelegram } from './services/telegram'

initializeTelegram()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider><App /></AuthProvider>
  </StrictMode>,
)
