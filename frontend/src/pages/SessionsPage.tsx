import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import { motion } from 'framer-motion'
import { ExternalLink, Clock, CheckCircle, AlertTriangle, Cpu } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

const STATUS_COLORS: Record<string, string> = {
    matched: '#22c55e',
    discrepancy_found: '#eab308',
    exception: '#ef4444',
    samr_alert: '#a855f7',
    processing: '#06b6d4',
    pending: '#3b82f6',
    failed: '#ef4444',
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
    matched: <CheckCircle size={14} />,
    discrepancy_found: <AlertTriangle size={14} />,
    exception: <AlertTriangle size={14} />,
    samr_alert: <AlertTriangle size={14} />,
    processing: <Cpu size={14} />,
    pending: <Clock size={14} />,
}

export default function SessionsPage() {
    const { data: sessions = [], isLoading, refetch } = useQuery({
        queryKey: ['sessions-list'],
        queryFn: () => api.listSessions(50, 0),
        refetchInterval: 10_000,
    })

    return (
        <div className="animate-fade-in">
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1>Reconciliation Sessions</h1>
                    <p>Track all three-way match sessions across your organization.</p>
                </div>
                <Link to="/upload" className="btn btn-primary">+ New Session</Link>
            </div>

            {isLoading ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                    {[...Array(5)].map((_, i) => (
                        <div key={i} className="skeleton" style={{ height: 72, borderRadius: 'var(--radius-lg)' }} />
                    ))}
                </div>
            ) : sessions.length === 0 ? (
                <div className="glass-card" style={{ textAlign: 'center', padding: '3rem' }}>
                    <Clock size={40} color="var(--text-muted)" style={{ margin: '0 auto 1rem' }} />
                    <h3 style={{ color: 'var(--text-secondary)' }}>No sessions yet</h3>
                    <p style={{ marginBottom: '1.25rem', fontSize: '0.875rem' }}>
                        Upload PO, GRN, and Invoice documents to create your first reconciliation.
                    </p>
                    <Link to="/upload" className="btn btn-primary">Upload Documents</Link>
                </div>
            ) : (
                <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Session ID</th>
                                <th>Status</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sessions.map((session: any, i: number) => {
                                const color = STATUS_COLORS[session.status] || '#94a3b8'
                                const icon = STATUS_ICONS[session.status] || <Clock size={14} />
                                return (
                                    <motion.tr
                                        key={session.id}
                                        initial={{ opacity: 0, y: 5 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: i * 0.03 }}
                                    >
                                        <td>
                                            <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                                {session.id.slice(0, 18)}...
                                            </code>
                                        </td>
                                        <td>
                                            <span className="badge" style={{
                                                background: `${color}18`,
                                                color,
                                                border: `1px solid ${color}40`,
                                                display: 'inline-flex', alignItems: 'center', gap: 5,
                                            }}>
                                                {icon}
                                                {session.status.replace(/_/g, ' ')}
                                            </span>
                                        </td>
                                        <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                                            {formatDistanceToNow(new Date(session.created_at), { addSuffix: true })}
                                        </td>
                                        <td>
                                            <Link to={`/reconciliation/${session.id}`}
                                                className="btn btn-secondary"
                                                style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                                                <ExternalLink size={13} /> View
                                            </Link>
                                        </td>
                                    </motion.tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
