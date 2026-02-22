import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import ProtectedRoute from './components/auth/ProtectedRoute'
import Sidebar from './components/layout/Sidebar'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/UploadPage'
import ReconciliationPage from './pages/ReconciliationPage'
import SessionsPage from './pages/SessionsPage'
import AnalyticsPage from './pages/AnalyticsPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import UnauthorizedPage from './pages/UnauthorizedPage'

function AppLayout() {
    const { isAuthenticated } = useAuth()

    if (!isAuthenticated) return null

    return (
        <div className="app-layout">
            <Sidebar />
            <main className="main-content">
                <Routes>
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />

                    {/* Any authenticated user */}
                    <Route path="/dashboard" element={
                        <ProtectedRoute>
                            <Dashboard />
                        </ProtectedRoute>
                    } />

                    {/* AP Analyst or above — upload and sessions */}
                    <Route path="/upload" element={
                        <ProtectedRoute minimumRole="ap_analyst">
                            <UploadPage />
                        </ProtectedRoute>
                    } />
                    <Route path="/sessions" element={
                        <ProtectedRoute minimumRole="ap_analyst">
                            <SessionsPage />
                        </ProtectedRoute>
                    } />
                    <Route path="/reconciliation/:sessionId" element={
                        <ProtectedRoute minimumRole="ap_analyst">
                            <ReconciliationPage />
                        </ProtectedRoute>
                    } />

                    {/* Finance Director or above — analytics */}
                    <Route path="/analytics" element={
                        <ProtectedRoute minimumRole="finance_director">
                            <AnalyticsPage />
                        </ProtectedRoute>
                    } />

                    {/* Unauthorized landing */}
                    <Route path="/unauthorized" element={<UnauthorizedPage />} />

                    {/* Catch-all */}
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
            </main>
        </div>
    )
}

export default function App() {
    const { isAuthenticated, isLoading } = useAuth()

    if (isLoading) {
        return (
            <div className="auth-loading-overlay">
                <div className="auth-loading-spinner" />
            </div>
        )
    }

    return (
        <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route
                path="/*"
                element={
                    isAuthenticated
                        ? <AppLayout />
                        : <Navigate to="/login" replace />
                }
            />
        </Routes>
    )
}
