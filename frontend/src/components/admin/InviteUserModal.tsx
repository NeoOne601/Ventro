/**
 * InviteUserModal — Glassmorphism slide-up for creating a new user
 * Shows the temporary password after successful creation
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../../services/api'
import { ROLE_COLORS, ROLE_LABELS } from '../../contexts/AuthContext'
import type { Role } from '../../contexts/AuthContext'

const INVITE_ROLES: Role[] = ['external_auditor', 'ap_analyst', 'ap_manager', 'finance_director', 'admin']

interface Props {
    isMaster: boolean
    onClose: () => void
    onSuccess: () => void
}

export default function InviteUserModal({ isMaster, onClose, onSuccess }: Props) {
    const [email, setEmail] = useState('')
    const [fullName, setFullName] = useState('')
    const [role, setRole] = useState<Role>('ap_analyst')
    const [orgId, setOrgId] = useState('')
    const [tempPassword, setTempPassword] = useState('')

    const createMutation = useMutation({
        mutationFn: () => apiClient.post('/admin/users', {
            email, full_name: fullName, role,
            organisation_id: isMaster && orgId ? orgId : undefined,
        }),
        onSuccess: (res) => {
            setTempPassword(res.data.temp_password)
        },
        onError: (err: any) => {
            // Error shown inline
        },
    })

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        createMutation.mutate()
    }

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2 className="modal-title">Invite User</h2>
                    <button className="drawer-close" onClick={onClose}>✕</button>
                </div>

                {tempPassword ? (
                    /* Success state — show temp password */
                    <div className="modal-success">
                        <div className="modal-success-icon">✅</div>
                        <h3>User invited!</h3>
                        <p>Share this temporary password with <strong>{email}</strong>:</p>
                        <div className="modal-temp-pw">
                            <code>{tempPassword}</code>
                            <button
                                className="btn btn--ghost modal-copy-btn"
                                onClick={() => { navigator.clipboard.writeText(tempPassword) }}
                            >
                                📋 Copy
                            </button>
                        </div>
                        <p className="modal-pw-note">
                            ⚠ This password is shown only once. The user should change it on first login.
                        </p>
                        <button className="btn btn--primary" onClick={onSuccess}>Done</button>
                    </div>
                ) : (
                    <form className="modal-form" onSubmit={handleSubmit}>
                        <div className="auth-field">
                            <label>Full name</label>
                            <input
                                type="text"
                                placeholder="Jane Smith"
                                value={fullName}
                                onChange={e => setFullName(e.target.value)}
                                required
                            />
                        </div>

                        <div className="auth-field">
                            <label>Work email</label>
                            <input
                                type="email"
                                placeholder="jane@acme.com"
                                value={email}
                                onChange={e => setEmail(e.target.value)}
                                required
                            />
                        </div>

                        {isMaster && (
                            <div className="auth-field">
                                <label>Organisation ID (optional)</label>
                                <input
                                    type="text"
                                    placeholder="Leave blank for your org"
                                    value={orgId}
                                    onChange={e => setOrgId(e.target.value)}
                                />
                            </div>
                        )}

                        {/* Role selector */}
                        <div className="auth-field">
                            <label>Role</label>
                            <div className="modal-role-grid">
                                {INVITE_ROLES.map(r => (
                                    <button
                                        key={r}
                                        type="button"
                                        className={`modal-role-card ${role === r ? 'modal-role-card--selected' : ''}`}
                                        style={role === r ? {
                                            borderColor: ROLE_COLORS[r],
                                            background: `${ROLE_COLORS[r]}18`,
                                        } : {}}
                                        onClick={() => setRole(r)}
                                    >
                                        <span style={{ color: ROLE_COLORS[r], fontWeight: 700 }}>
                                            {ROLE_LABELS[r]}
                                        </span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {createMutation.isError && (
                            <div className="auth-error">
                                ⚠ {(createMutation.error as any)?.response?.data?.detail ?? 'Creation failed'}
                            </div>
                        )}

                        <div className="modal-footer">
                            <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
                            <button
                                type="submit"
                                className="btn btn--primary"
                                disabled={createMutation.isPending}
                            >
                                {createMutation.isPending ? 'Creating…' : 'Send Invite'}
                            </button>
                        </div>
                    </form>
                )}
            </div>
        </div>
    )
}
