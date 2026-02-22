/**
 * OrgGrid — MASTER-only organisation health cards
 * Shows in the Admin Console "Organisations" tab.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../../services/api'
import OrgDetailDrawer from './OrgDetailDrawer'
import './OrgGrid.css'

const TIER_COLORS: Record<string, string> = {
    starter: '#64748b',
    growth: '#6366f1',
    enterprise: '#8b5cf6',
    enterprise_plus: '#ec4899',
}

interface OrgSummary {
    id: string; name: string; slug: string; tier: string; is_active: boolean
    created_at: string; user_count: number; session_count_30d: number
    samr_alert_rate_30d: number; webhook_count: number
}

export default function OrgGrid() {
    const [search, setSearch] = useState('')
    const [tierFilter, setTierFilter] = useState('')
    const [selectedOrg, setSelectedOrg] = useState<string | null>(null)

    const { data: orgs = [], isLoading } = useQuery<OrgSummary[]>({
        queryKey: ['admin-orgs', search, tierFilter],
        queryFn: async () => (await apiClient.get('/admin/orgs', {
            params: { search, tier: tierFilter },
        })).data,
        staleTime: 30_000,
    })

    const { data: globalStats } = useQuery({
        queryKey: ['admin-global-stats'],
        queryFn: async () => (await apiClient.get('/admin/orgs/global-stats')).data,
        staleTime: 60_000,
    })

    return (
        <div className="org-grid-page">
            {/* Global stats bar */}
            {globalStats && (
                <div className="org-global-stats">
                    {[
                        { label: 'Organisations', value: globalStats.total_orgs },
                        { label: 'Active', value: globalStats.active_orgs },
                        { label: 'Users', value: globalStats.total_users },
                        { label: 'Sessions (30d)', value: globalStats.sessions_30d },
                        { label: 'SAMR Precision', value: `${(globalStats.samr_precision_30d * 100).toFixed(0)}%` },
                        { label: 'Est. MRR', value: `$${globalStats.estimated_mrr_usd?.toLocaleString()}` },
                    ].map(({ label, value }) => (
                        <div key={label} className="org-stat-card">
                            <div className="org-stat-value">{value}</div>
                            <div className="org-stat-label">{label}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* Filters */}
            <div className="admin-filters">
                <div className="admin-search-wrap" style={{ flex: 1 }}>
                    <span className="admin-search-icon">🔍</span>
                    <input
                        className="admin-search"
                        placeholder="Search org name or slug…"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                    />
                </div>
                <select className="admin-role-filter" value={tierFilter} onChange={e => setTierFilter(e.target.value)}>
                    <option value="">All tiers</option>
                    {['starter', 'growth', 'enterprise', 'enterprise_plus'].map(t => (
                        <option key={t} value={t}>{t}</option>
                    ))}
                </select>
                <span className="admin-count">{orgs.length} orgs</span>
            </div>

            {/* Cards */}
            {isLoading ? <div className="admin-loading">Loading…</div> : (
                <div className="org-cards">
                    {orgs.map(org => (
                        <div
                            key={org.id}
                            className={`org-card ${!org.is_active ? 'org-card--inactive' : ''}`}
                            onClick={() => setSelectedOrg(org.id)}
                        >
                            <div className="org-card-top">
                                <div>
                                    <div className="org-card-name">{org.name}</div>
                                    <div className="org-card-slug">ventro.io/{org.slug}</div>
                                </div>
                                <span
                                    className="org-tier-badge"
                                    style={{ background: `${TIER_COLORS[org.tier]}22`, color: TIER_COLORS[org.tier] }}
                                >
                                    {org.tier.replace('_', ' ')}
                                </span>
                            </div>

                            <div className="org-card-metrics">
                                <div className="org-metric">
                                    <span className="org-metric-value">{org.user_count}</span>
                                    <span className="org-metric-label">users</span>
                                </div>
                                <div className="org-metric">
                                    <span className="org-metric-value">{org.session_count_30d}</span>
                                    <span className="org-metric-label">sessions/30d</span>
                                </div>
                                <div className="org-metric">
                                    <span
                                        className="org-metric-value"
                                        style={{ color: org.samr_alert_rate_30d > 0.3 ? '#ef4444' : '#10b981' }}
                                    >
                                        {(org.samr_alert_rate_30d * 100).toFixed(0)}%
                                    </span>
                                    <span className="org-metric-label">SAMR rate</span>
                                </div>
                                <div className="org-metric">
                                    <span className="org-metric-value">{org.webhook_count}</span>
                                    <span className="org-metric-label">webhooks</span>
                                </div>
                            </div>

                            {!org.is_active && (
                                <div className="org-inactive-banner">⚠ Organisation suspended</div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {selectedOrg && (
                <OrgDetailDrawer
                    orgId={selectedOrg}
                    onClose={() => setSelectedOrg(null)}
                />
            )}
        </div>
    )
}
