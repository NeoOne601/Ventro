/**
 * EditRoleDrawer — Slides in from right to edit a user's role + active status
 * Sections: user info, role selector cards, active toggle, danger zone (revoke sessions)
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'react-toastify'
import apiClient from '../../services/api'
import { ROLE_COLORS, ROLE_LABELS } from '../../contexts/AuthContext'
import type { Role } from '../../contexts/AuthContext'

const ASSIGNABLE_ROLES: Role[] = [
    'external_auditor', 'ap_analyst', 'ap_manager',
    'finance_director', 'admin', 'developer',
]

const ROLE_DESC: Record<string, string> = {
    external_auditor: 'Read-only — sessions & workpapers',
    ap_analyst: 'Upload, reconcile, manage sessions',
    ap_manager: 'All analyst + approve & sign workpapers',
    finance_director: 'All manager + analytics & billing',
    admin: 'Full org management + user admin',
    developer: 'Debug access + API key management',
}

interface Props {
    user: { id: string; email: string; full_name: string; role: string; is_active: boolean; last_login_at: string | null }
    onClose: () => void
    onSuccess: () => void
}

export default function EditRoleDrawer({ user, onClose, onSuccess }: Props) {
    const [selectedRole, setSelectedRole] = useState(user.role)
    const [isActive, setIsActive] = useState(user.is_active)

    const updateMutation = useMutation({
        mutationFn: () => apiClient.patch(`/admin/users/${user.id}`, {
            role: selectedRole !== user.role ? selectedRole : undefined,
            is_active: isActive !== user.is_active ? isActive : undefined,
        }),
        onSuccess: () => { toast.success('User updated'); onSuccess() },
        onError: () => toast.error('Update failed'),
    })

    const revokeSessionsMutation = useMutation({
        mutationFn: () => apiClient.post(`/admin/users/${user.id}/revoke-sessions`),
        onSuccess: () => toast.success('All sessions revoked'),
        onError: () => toast.error('Failed to revoke sessions'),
    })

    const hasChanges = selectedRole !== user.role || isActive !== user.is_active

    return (
        <>
            <div className="drawer-backdrop" onClick={onClose} />
            <div className="drawer">
                <div className="drawer-header">
                    <div>
                        <div className="drawer-title">Edit User</div>
                        <div className="drawer-subtitle">{user.email}</div>
                    </div>
                    <button className="drawer-close" onClick={onClose}>✕</button>
                </div>

                {/* User Info */}
                <div className="drawer-user-card">
                    <div className="admin-avatar drawer-avatar">
                        {user.full_name?.[0]?.toUpperCase() ?? '?'}
                    </div>
                    <div>
                        <div className="drawer-user-name">{user.full_name}</div>
                        <div className="drawer-user-meta">
                            Last login: {user.last_login_at
                                ? new Date(user.last_login_at).toLocaleString()
                                : 'Never'}
                        </div>
                    </div>
                </div>

                {/* Role selector */}
                <div className="drawer-section">
                    <div className="drawer-section-label">Role</div>
                    <div className="drawer-role-grid">
                        {ASSIGNABLE_ROLES.map(role => (
                            <button
                                key={role}
                                className={`drawer-role-card ${selectedRole === role ? 'drawer-role-card--selected' : ''}`}
                                style={selectedRole === role ? {
                                    borderColor: ROLE_COLORS[role],
                                    background: `${ROLE_COLORS[role]}18`,
                                } : {}}
                                onClick={() => setSelectedRole(role)}
                            >
                                <div className="drawer-role-name" style={{ color: ROLE_COLORS[role] }}>
                                    {ROLE_LABELS[role]}
                                </div>
                                <div className="drawer-role-desc">{ROLE_DESC[role]}</div>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Active toggle */}
                <div className="drawer-section">
                    <div className="drawer-section-label">Account Status</div>
                    <label className="drawer-toggle">
                        <div
                            className={`drawer-toggle-track ${isActive ? 'drawer-toggle-track--on' : ''}`}
                            onClick={() => setIsActive(a => !a)}
                        >
                            <div className="drawer-toggle-thumb" />
                        </div>
                        <span className="drawer-toggle-label">
                            {isActive ? 'Active' : 'Disabled'}
                        </span>
                    </label>
                </div>

                {/* Danger zone */}
                <div className="drawer-section drawer-danger-zone">
                    <div className="drawer-section-label">Danger Zone</div>
                    <button
                        className="btn btn--danger drawer-revoke-btn"
                        onClick={() => {
                            if (confirm('Revoke all active sessions for this user?')) {
                                revokeSessionsMutation.mutate()
                            }
                        }}
                        disabled={revokeSessionsMutation.isPending}
                    >
                        🔒 Revoke All Sessions
                    </button>
                </div>

                {/* Footer */}
                <div className="drawer-footer">
                    <button className="btn btn--ghost" onClick={onClose}>Cancel</button>
                    <button
                        className="btn btn--primary"
                        onClick={() => updateMutation.mutate()}
                        disabled={!hasChanges || updateMutation.isPending}
                    >
                        {updateMutation.isPending ? 'Saving…' : 'Save Changes'}
                    </button>
                </div>
            </div>
        </>
    )
}
