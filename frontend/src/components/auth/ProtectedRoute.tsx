/**
 * ProtectedRoute — Role-gated routing component
 * 
 * Wraps any route that requires authentication or a specific minimum role.
 * Handles loading state (spinning overlay), unauthenticated redirect → /login,
 * and unauthorised redirect → /unauthorized.
 * 
 * Usage:
 *   <ProtectedRoute>                          // any authenticated user
 *   <ProtectedRoute minimumRole="ap_analyst"> // analyst or higher
 *   <ProtectedRoute minimumRole="admin">      // admin / developer / master only
 *   <ProtectedRoute permission="finding:override"> // specific permission
 */
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth, type Permission, type Role } from '../../contexts/AuthContext'

interface ProtectedRouteProps {
    children: React.ReactNode
    minimumRole?: Role
    permission?: Permission
}

export default function ProtectedRoute({
    children,
    minimumRole,
    permission,
}: ProtectedRouteProps) {
    const { isAuthenticated, isLoading, hasRole, hasPermission } = useAuth()
    const location = useLocation()

    if (isLoading) {
        return (
            <div className="auth-loading-overlay">
                <div className="auth-loading-spinner" />
                <p>Authenticating…</p>
            </div>
        )
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" state={{ from: location }} replace />
    }

    if (minimumRole && !hasRole(minimumRole)) {
        return <Navigate to="/unauthorized" replace />
    }

    if (permission && !hasPermission(permission)) {
        return <Navigate to="/unauthorized" replace />
    }

    return <>{children}</>
}
