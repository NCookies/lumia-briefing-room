import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AppInfoProvider } from './components/AppInfoProvider.tsx'
import { ConfirmProvider } from './components/ConfirmProvider.tsx'
import { installClientLog } from './clientLog.ts'

installClientLog()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppInfoProvider>
      <ConfirmProvider>
        <App />
      </ConfirmProvider>
    </AppInfoProvider>
  </StrictMode>,
)
