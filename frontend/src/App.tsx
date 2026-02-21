import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/UploadPage'
import ReconciliationPage from './pages/ReconciliationPage'
import SessionsPage from './pages/SessionsPage'
import AnalyticsPage from './pages/AnalyticsPage'

export default function App() {
    return (
        <div className="app-layout">
            <Sidebar />
            <main className="main-content">
                <Routes>
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/upload" element={<UploadPage />} />
                    <Route path="/sessions" element={<SessionsPage />} />
                    <Route path="/reconciliation/:sessionId" element={<ReconciliationPage />} />
                    <Route path="/analytics" element={<AnalyticsPage />} />
                </Routes>
            </main>
        </div>
    )
}
