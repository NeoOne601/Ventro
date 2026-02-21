import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import {
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts'
import {
    ShieldCheck, AlertTriangle, CheckCircle, TrendingUp,
    Files, Zap, ArrowRight, Activity
} from 'lucide-react'

const STATUS_COLORS = {
    matched: '#22c55e',
    discrepancy_found: '#eab308',
    exception: '#ef4444',
    samr_alert: '#a855f7',
    pending: '#3b82f6',
    processing: '#06b6d4',
}

export default function Dashboard() {
    const { data: metrics, isLoading } = useQuery({
        queryKey: ['analytics-metrics'],
        queryFn: api.getMetrics,
        refetchInterval: 30_000,
    })

    const { data: health } = useQuery({
        queryKey: ['health'],
        queryFn: api.getHealth,
        refetchInterval: 60_000,
    })

    const StatusDot = ({ status }: { status: string }) => (
        <span
            className="status-dot"
            style={{
                width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                background: status === 'healthy' ? '#22c55e' : status === 'degraded' ? '#eab308' : '#ef4444',
                boxShadow: `0 0 8px ${status === 'healthy' ? '#22c55e' : '#eab308'}`,
            }}
        />
    )

    const pieData = metrics ? [
        { name: 'Matched', value: metrics.matched_sessions, color: '#22c55e' },
        { name: 'Discrepancy', value: metrics.discrepancy_sessions, color: '#ef4444' },
        { name: 'SAMR Alert', value: metrics.samr_alerts, color: '#a855f7' },
    ].filter(d => d.value > 0) : []

    const sessionHistory = (metrics?.sessions || []).slice(0, 20).map((s: any, i: number) => ({
        name: `S${i + 1}`,
        time: s.processing_time ? Math.round(s.processing_time) : 0,
        status: s.status,
    }))

    return (
        <div className="animate-fade-in">
            {/* Page Header */}
            <div className="page-header">
                <h1>Command Center</h1>
                <p>Real-time oversight of your AI-powered audit reconciliation system.</p>
            </div>

            {/* Metric Cards */}
            <div className="metrics-grid">
                {[
                    {
                        label: 'Total Sessions',
                        value: isLoading ? '—' : metrics?.total_sessions ?? 0,
                        icon: <Files size={20} />,
                        color: 'var(--color-accent)',
                        glow: 'var(--color-accent-glow)',
                    },
                    {
                        label: 'Matched',
                        value: isLoading ? '—' : metrics?.matched_sessions ?? 0,
                        icon: <CheckCircle size={20} />,
                        color: '#22c55e',
                        glow: 'rgba(34,197,94,0.25)',
                    },
                    {
                        label: 'SAMR Alerts',
                        value: isLoading ? '—' : metrics?.samr_alerts ?? 0,
                        icon: <AlertTriangle size={20} />,
                        color: '#a855f7',
                        glow: 'rgba(168,85,247,0.25)',
                    },
                    {
                        label: 'Avg. Process Time',
                        value: isLoading ? '—' : `${metrics?.avg_processing_time_seconds ?? 0}s`,
                        icon: <Activity size={20} />,
                        color: 'var(--color-cyan)',
                        glow: 'var(--color-cyan-glow)',
                    },
                    {
                        label: 'Hallucination Rate',
                        value: isLoading ? '—' : `${((metrics?.hallucination_rate ?? 0) * 100).toFixed(1)}%`,
                        icon: <ShieldCheck size={20} />,
                        color: metrics?.hallucination_rate > 0.1 ? '#ef4444' : '#22c55e',
                        glow: 'rgba(34,197,94,0.25)',
                    },
                    {
                        label: 'Discrepancies',
                        value: isLoading ? '—' : metrics?.discrepancy_sessions ?? 0,
                        icon: <TrendingUp size={20} />,
                        color: '#eab308',
                        glow: 'rgba(234,179,8,0.25)',
                    },
                ].map((card) => (
                    <div className="metric-card glass-card" key={card.label}
                        style={{ borderTop: `2px solid ${card.color}` }}>
                        <div className="metric-icon" style={{
                            color: card.color,
                            background: card.glow,
                            width: 40, height: 40, borderRadius: 10,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            marginBottom: '0.75rem',
                        }}>
                            {card.icon}
                        </div>
                        <div className="metric-value" style={{ fontSize: '2rem', fontWeight: 700, color: card.color }}>
                            {isLoading ? <div className="skeleton" style={{ height: 36, width: 80 }} /> : card.value}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>{card.label}</div>
                    </div>
                ))}
            </div>

            {/* Charts Row */}
            <div className="two-col" style={{ marginBottom: 'var(--space-xl)' }}>
                {/* Processing Time Chart */}
                <div className="glass-card">
                    <h3 style={{ marginBottom: '1.25rem', color: 'var(--text-accent)' }}>
                        Processing Time per Session
                    </h3>
                    {sessionHistory.length > 0 ? (
                        <ResponsiveContainer width="100%" height={200}>
                            <AreaChart data={sessionHistory}>
                                <defs>
                                    <linearGradient id="timeGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                <XAxis dataKey="name" stroke="#475569" tick={{ fontSize: 11 }} />
                                <YAxis stroke="#475569" tick={{ fontSize: 11 }} unit="s" />
                                <Tooltip
                                    contentStyle={{
                                        background: 'rgba(15,23,42,0.95)',
                                        border: '1px solid rgba(255,255,255,0.08)',
                                        borderRadius: 8,
                                        fontSize: 12,
                                    }}
                                />
                                <Area type="monotone" dataKey="time" stroke="#6366f1" fill="url(#timeGrad)" strokeWidth={2} />
                            </AreaChart>
                        </ResponsiveContainer>
                    ) : (
                        <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                            No sessions yet. <Link to="/upload" style={{ marginLeft: 8 }}>Upload documents →</Link>
                        </div>
                    )}
                </div>

                {/* Status Distribution Pie */}
                <div className="glass-card">
                    <h3 style={{ marginBottom: '1.25rem', color: 'var(--text-accent)' }}>
                        Reconciliation Status Distribution
                    </h3>
                    {pieData.length > 0 ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
                            <ResponsiveContainer width={160} height={160}>
                                <PieChart>
                                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={45} outerRadius={75}
                                        paddingAngle={3} dataKey="value">
                                        {pieData.map((entry, index) => (
                                            <Cell key={index} fill={entry.color} />
                                        ))}
                                    </Pie>
                                </PieChart>
                            </ResponsiveContainer>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                                {pieData.map((entry) => (
                                    <div key={entry.name} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.85rem' }}>
                                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: entry.color, flexShrink: 0 }} />
                                        <span style={{ color: 'var(--text-secondary)' }}>{entry.name}</span>
                                        <span style={{ color: 'var(--text-primary)', fontWeight: 600, marginLeft: 'auto' }}>{entry.value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                            No data yet
                        </div>
                    )}
                </div>
            </div>

            {/* System Health + CTA */}
            <div className="two-col">
                <div className="glass-card">
                    <h3 style={{ marginBottom: '1rem', color: 'var(--text-accent)' }}>System Health</h3>
                    {health?.services ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {Object.entries(health.services).map(([svc, status]) => (
                                <div key={svc} style={{
                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                    padding: '0.6rem 0.75rem', background: 'var(--glass-bg)',
                                    borderRadius: 'var(--radius-md)', border: '1px solid var(--glass-border)',
                                }}>
                                    <span style={{ fontSize: '0.85rem', textTransform: 'capitalize' }}>{svc}</span>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <StatusDot status={status as string} />
                                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                                            {status as string}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading health data...</div>
                    )}
                </div>

                <div className="glass-card" style={{
                    background: 'linear-gradient(135deg, rgba(99,102,241,0.12), rgba(168,85,247,0.08))',
                    border: '1px solid rgba(99,102,241,0.25)',
                    display: 'flex', flexDirection: 'column', justifyContent: 'center',
                }}>
                    <div style={{ color: 'var(--color-accent)', marginBottom: '0.75rem' }}>
                        <Zap size={32} />
                    </div>
                    <h3 style={{ marginBottom: '0.5rem' }}>Ready to Reconcile?</h3>
                    <p style={{ fontSize: '0.875rem', marginBottom: '1.25rem' }}>
                        Upload your Purchase Order, Goods Receipt Note, and Invoice to begin the
                        AI-powered three-way match audit.
                    </p>
                    <Link to="/upload" className="btn btn-primary" style={{ width: 'fit-content' }}>
                        Start Reconciliation <ArrowRight size={16} />
                    </Link>
                </div>
            </div>
        </div>
    )
}
