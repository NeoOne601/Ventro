import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, RadarChart, Radar, PolarGrid,
    PolarAngleAxis, PolarRadiusAxis
} from 'recharts'
import { ShieldCheck, TrendingUp, Activity, AlertTriangle } from 'lucide-react'

export default function AnalyticsPage() {
    const { data: metrics, isLoading } = useQuery({
        queryKey: ['analytics-full'],
        queryFn: api.getMetrics,
        refetchInterval: 60_000,
    })

    const { data: health } = useQuery({
        queryKey: ['health-full'],
        queryFn: api.getHealth,
    })

    const sessionData = (metrics?.sessions || []).slice(0, 15).map((s: any, i: number) => ({
        name: `S${i + 1}`,
        time: s.processing_time ? Math.round(s.processing_time) : 0,
        status: s.status,
    }))

    const radarData = [
        { subject: 'Match Rate', value: metrics ? (metrics.matched_sessions / Math.max(metrics.total_sessions, 1)) * 100 : 0 },
        { subject: 'SAMR Safety', value: metrics ? (1 - metrics.hallucination_rate) * 100 : 100 },
        { subject: 'Speed', value: metrics?.avg_processing_time_seconds < 60 ? 90 : 50 },
        { subject: 'Compliance', value: 85 },
        { subject: 'Accuracy', value: 92 },
        { subject: 'Coverage', value: 95 },
    ]

    const getStatusColor = (st: string) => ({
        matched: '#22c55e', discrepancy_found: '#eab308', exception: '#ef4444',
        samr_alert: '#a855f7', processing: '#06b6d4', pending: '#3b82f6',
    })[st] || '#94a3b8'

    return (
        <div className="animate-fade-in">
            <div className="page-header">
                <h1>Analytics &amp; Performance</h1>
                <p>System-wide metrics for the MAS-VGFR reconciliation engine.</p>
            </div>

            {/* KPI Row */}
            <div className="metrics-grid" style={{ marginBottom: 'var(--space-xl)' }}>
                {[
                    { label: 'Total Sessions', value: metrics?.total_sessions ?? 0, icon: <Activity />, color: 'var(--color-accent)' },
                    { label: 'Match Rate', value: `${metrics ? ((metrics.matched_sessions / Math.max(metrics.total_sessions, 1)) * 100).toFixed(1) : 0}%`, icon: <TrendingUp />, color: '#22c55e' },
                    { label: 'Hallucination Rate', value: `${((metrics?.hallucination_rate ?? 0) * 100).toFixed(2)}%`, icon: <ShieldCheck />, color: metrics?.hallucination_rate > 0.05 ? '#ef4444' : '#22c55e' },
                    { label: 'SAMR Alerts', value: metrics?.samr_alerts ?? 0, icon: <AlertTriangle />, color: '#a855f7' },
                ].map((kpi) => (
                    <div key={kpi.label} className="glass-card" style={{ borderTop: `2px solid ${kpi.color}` }}>
                        <div style={{ color: kpi.color, marginBottom: '0.6rem' }}>{kpi.icon}</div>
                        <div style={{ fontSize: '1.75rem', fontWeight: 700, color: kpi.color }}>
                            {isLoading ? '—' : kpi.value}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 4 }}>{kpi.label}</div>
                    </div>
                ))}
            </div>

            <div className="two-col" style={{ marginBottom: 'var(--space-xl)' }}>
                {/* Processing Times Bar Chart */}
                <div className="glass-card">
                    <h3 style={{ marginBottom: '1rem', color: 'var(--text-accent)' }}>Session Processing Times (s)</h3>
                    <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={sessionData} barSize={14}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                            <XAxis dataKey="name" stroke="#475569" tick={{ fontSize: 11 }} />
                            <YAxis stroke="#475569" tick={{ fontSize: 11 }} unit="s" />
                            <Tooltip
                                contentStyle={{ background: 'rgba(15,23,42,0.95)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, fontSize: 12 }}
                                cursor={{ fill: 'rgba(99,102,241,0.08)' }}
                            />
                            <Bar dataKey="time" radius={[4, 4, 0, 0]}
                                fill="url(#barGrad)"
                            />
                            <defs>
                                <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.9} />
                                    <stop offset="100%" stopColor="#a855f7" stopOpacity={0.6} />
                                </linearGradient>
                            </defs>
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* Radar Chart - System Quality */}
                <div className="glass-card">
                    <h3 style={{ marginBottom: '1rem', color: 'var(--text-accent)' }}>System Quality Metrics</h3>
                    <ResponsiveContainer width="100%" height={220}>
                        <RadarChart data={radarData}>
                            <PolarGrid stroke="rgba(255,255,255,0.08)" />
                            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10, fill: '#475569' }} />
                            <Radar name="Quality" dataKey="value" stroke="#6366f1" fill="#6366f1" fillOpacity={0.15} strokeWidth={2} />
                        </RadarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* System Health Details */}
            <div className="glass-card">
                <h3 style={{ marginBottom: '1.25rem', color: 'var(--text-accent)' }}>Infrastructure Status</h3>
                <div className="three-col">
                    {health?.services ? Object.entries(health.services).map(([svc, status]) => (
                        <div key={svc} style={{
                            padding: '1rem', background: 'var(--glass-bg)',
                            borderRadius: 'var(--radius-md)', border: '1px solid var(--glass-border)',
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                                <div style={{
                                    width: 8, height: 8, borderRadius: '50%',
                                    background: status === 'healthy' ? '#22c55e' : '#eab308',
                                    boxShadow: `0 0 6px ${status === 'healthy' ? '#22c55e' : '#eab308'}`,
                                }} />
                                <span style={{ fontWeight: 600, textTransform: 'capitalize', fontSize: '0.875rem' }}>
                                    {svc}
                                </span>
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                                {status as string}
                            </div>
                        </div>
                    )) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading...</div>
                    )}
                </div>
            </div>
        </div>
    )
}
