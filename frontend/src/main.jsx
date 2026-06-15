import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'

// Import Bootstrap Icons
import 'bootstrap-icons/font/bootstrap-icons.css'

// Import Global Styles
import './styles/style.min.css'
import './styles/premium-overrides.css'

import { AuthProvider } from './contexts/AuthContext'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
