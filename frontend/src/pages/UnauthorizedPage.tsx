/**
 * Unauthorised Page — shown when user is authenticated but lacks required role/permission
 */
import { useNavigate } from 'react-router-dom'
import { useAuth, ROLE_LABELS, ROLE_COLORS } from '../contexts/AuthContext'

export default function UnauthorizedPage() {
    const { user, logout } = useAuth()
    const navigate = useNavigate()

    return (
        <div className="unauth-page">
            <div className="unauth-icon">🔒</div>
            <h1 className="unauth-title">Access Restricted</h1>
            <p className="unauth-subtitle">
                You don't have permission to access this page.
            </p>

            {user && (
                <div className="unauth-role-box">
                    <span>Signed in as</span>
                    <span
                        className="unauth-role-badge"
                        style={{ background: ROLE_COLORS[user.role] + '22', color: ROLE_COLORS[user.role], border: `1px solid ${ROLE_COLORS[user.role]}44` }}
                    >
                        {ROLE_LABELS[user.role]}
                    </span>
                </div>
            )}

            <div className="unauth-actions">
                <button className="btn btn--ghost" onClick={() => navigate(-1)}>
                    ← Go back
                </button>
                <button className="btn btn--primary" onClick={() => navigate('/dashboard')}>
                    Dashboard
                </button>
                <button className="btn btn--danger" onClick={() => logout()}>
                    Sign out
                </button>
            </div>
        </div>
    )
}
