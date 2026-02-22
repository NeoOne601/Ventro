/**
 * UserTable — Searchable, sortable, paginated user management table
 * Shows role badges, status indicators, and per-row action menu
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-toastify'
import apiClient from '../../services/api'
import EditRoleDrawer from './EditRoleDrawer'
import { ROLE_COLORS, ROLE_LABELS } from '../../contexts/AuthContext'
import type { Role } from '../../contexts/AuthContext'

interface User {
    id: string
    email: string
    full_name: string
    role: string
    organisation_id: string
    is_active: boolean
    is_verified: boolean
    created_at: string
    last_login_at: string | null
}

export default function UserTable({ isMaster }: { isMaster: boolean }) {
    const qc = useQueryClient()
    const [page, setPage] = useState(1)
    const [search, setSearch] = useState('')
    const [roleFilter, setRoleFilter] = useState('')
    const [selectedUser, setSelectedUser] = useState<User | null>(null)
    const [showDrawer, setShowDrawer] = useState(false)
    const PAGE_SIZE = 20

    const { data, isLoading } = useQuery({
        queryKey: ['admin-users', page, search, roleFilter],
        queryFn: async () => {
            const { data } = await apiClient.get('/admin/users', {
                params: { page, page_size: PAGE_SIZE, search, role: roleFilter },
            })
            return data
        },
        staleTime: 30_000,
    })

    const disableMutation = useMutation({
        mutationFn: (userId: string) => apiClient.delete(`/admin/users/${userId}`),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['admin-users'] })
            toast.success('User disabled')
        },
        onError: () => toast.error('Failed to disable user'),
    })

    const revokeSessionsMutation = useMutation({
        mutationFn: (userId: string) => apiClient.post(`/admin/users/${userId}/revoke-sessions`),
        onSuccess: () => toast.success('All sessions revoked'),
        onError: () => toast.error('Failed to revoke sessions'),
    })

    const ROLES = ['ap_analyst', 'ap_manager', 'finance_director', 'external_auditor', 'admin', 'developer', 'master']

    return (
        <div className="admin-user-table-wrap">
            {/* Filters */}
            <div className="admin-filters">
                <div className="admin-search-wrap">
                    <span className="admin-search-icon">🔍</span>
                    <input
                        className="admin-search"
                        placeholder="Search by name or email…"
                        value={search}
                        onChange={e => { setSearch(e.target.value); setPage(1) }}
                    />
                </div>
                <select
                    className="admin-role-filter"
                    value={roleFilter}
                    onChange={e => { setRoleFilter(e.target.value); setPage(1) }}
                >
                    <option value="">All roles</option>
                    {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r as Role] ?? r}</option>)}
                </select>
                {data && (
                    <span className="admin-count">{data.total} user{data.total !== 1 ? 's' : ''}</span>
                )}
            </div>

            {/* Table */}
            <div className="admin-table-container">
                <table className="admin-table">
                    <thead>
                        <tr>
                            <th>User</th>
                            <th>Role</th>
                            <th>Status</th>
                            <th>Last Login</th>
                            {isMaster && <th>Org</th>}
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {isLoading && (
                            <tr><td colSpan={6} className="admin-loading">Loading…</td></tr>
                        )}
                        {data?.items?.map((u: User) => (
                            <tr key={u.id} className={!u.is_active ? 'admin-row--disabled' : ''}>
                                <td>
                                    <div className="admin-user-cell">
                                        <div className="admin-avatar">
                                            {u.full_name?.[0]?.toUpperCase() ?? '?'}
                                        </div>
                                        <div>
                                            <div className="admin-user-name">{u.full_name}</div>
                                            <div className="admin-user-email">{u.email}</div>
                                        </div>
                                    </div>
                                </td>
                                <td>
                                    <span
                                        className="admin-role-badge"
                                        style={{ background: `${ROLE_COLORS[u.role as Role]}22`, color: ROLE_COLORS[u.role as Role] ?? '#64748b' }}
                                    >
                                        {ROLE_LABELS[u.role as Role] ?? u.role}
                                    </span>
                                </td>
                                <td>
                                    <span className={`admin-status ${u.is_active ? 'admin-status--active' : 'admin-status--inactive'}`}>
                                        <span className="admin-status-dot" />
                                        {u.is_active ? 'Active' : 'Disabled'}
                                    </span>
                                </td>
                                <td className="admin-muted">
                                    {u.last_login_at
                                        ? new Date(u.last_login_at).toLocaleDateString()
                                        : 'Never'}
                                </td>
                                {isMaster && (
                                    <td className="admin-muted">{u.organisation_id.slice(0, 8)}…</td>
                                )}
                                <td>
                                    <div className="admin-actions">
                                        <button
                                            className="admin-action"
                                            title="Edit role"
                                            onClick={() => { setSelectedUser(u); setShowDrawer(true) }}
                                        >
                                            ✏️
                                        </button>
                                        <button
                                            className="admin-action"
                                            title="Revoke all sessions"
                                            onClick={() => revokeSessionsMutation.mutate(u.id)}
                                        >
                                            🔒
                                        </button>
                                        {u.is_active && (
                                            <button
                                                className="admin-action admin-action--danger"
                                                title="Disable user"
                                                onClick={() => {
                                                    if (confirm(`Disable ${u.email}?`)) {
                                                        disableMutation.mutate(u.id)
                                                    }
                                                }}
                                            >
                                                🚫
                                            </button>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            {data && data.total > PAGE_SIZE && (
                <div className="admin-pagination">
                    <button
                        className="btn btn--ghost"
                        disabled={page === 1}
                        onClick={() => setPage(p => p - 1)}
                    >← Prev</button>
                    <span className="admin-page-info">Page {page} of {Math.ceil(data.total / PAGE_SIZE)}</span>
                    <button
                        className="btn btn--ghost"
                        disabled={page >= Math.ceil(data.total / PAGE_SIZE)}
                        onClick={() => setPage(p => p + 1)}
                    >Next →</button>
                </div>
            )}

            {showDrawer && selectedUser && (
                <EditRoleDrawer
                    user={selectedUser}
                    onClose={() => { setShowDrawer(false); setSelectedUser(null) }}
                    onSuccess={() => {
                        setShowDrawer(false)
                        setSelectedUser(null)
                        qc.invalidateQueries({ queryKey: ['admin-users'] })
                    }}
                />
            )}
        </div>
    )
}
