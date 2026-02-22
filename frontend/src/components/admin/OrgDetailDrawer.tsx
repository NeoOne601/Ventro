/**
 * OrgDetailDrawer — Slide-in org detail panel (MASTER only)
 * Shows full org stats + user list + tier management.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-toastify'
import apiClient from '../../services/api'

const TIER_OPTIONS = ['starter', 'growth', 'enterprise', 'enterprise_plus']
const TIER_PRICES: Record<string, string> = {
    starter: 'Free', growth: '$499/mo', enterprise: '$1,999/mo', enterprise_plus: '$4,999/mo',
}

interface Props {
    orgId: string
    onClose: () => void
}

export default function OrgDetailDrawer({ orgId, onClose }: Props) {
    const qc = useQueryClient()
    const [tierEdit, setTierEdit] = useState<string | null>(null)

    const { data: org, isLoading } = useQuery({
        queryKey: ['admin-org', orgId],
        queryFn: async () => (await apiClient.get(`/admin/orgs/${orgId}`)).data,
    })

    const updateMutation = useMutation({
        mutationFn: (payload: { tier?: string; is_active?: boolean }) =>
            apiClient.patch(`/admin/orgs/${orgId}`, payload),
        onSuccess: () => {
            toast.success('Organisation updated')
            qc.invalidateQueries({ queryKey: ['admin-org', orgId] })
            qc.invalidateQueries({ queryKey: ['admin-orgs'] })
        },
        onError: () => toast.error('Update failed'),
    })

    return (
        <>
            <div className="drawer-backdrop" onClick={onClose} />
            <div className="drawer" style={{ width: 480 }}>
                <div className="drawer-header">
                    <div>
                        <div className="drawer-title">{org?.name ?? '…'}</div>
                        <div className="drawer-subtitle">{org?.slug ? `ventro.io/${org.slug}` : ''}</div>
                    </div>
                    <button className="drawer-close" onClick={onClose}>✕</button>
                </div>

                {isLoading ? <div className="admin-loading">Loading…</div> : org && (
                    <div className="drawer-body">
                        {/* Health metrics */}
                        <div className="org-detail-metrics">
                            {[
                                { label: 'Users', value: org.user_count },
                                { label: 'Sessions (30d)', value: org.session_count_30d },
                                { label: 'Total sessions', value: org.total_sessions },
                                { label: 'Webhooks', value: org.webhook_count },
                                { label: 'SAMR alert rate (30d)', value: `${(org.samr_alert_rate_30d * 100).toFixed(0)}%` },
                                { label: 'Avg session time', value: `${Math.round(org.avg_session_duration_seconds)}s` },
                            ].map(({ label, value }) => (
                                <div key={label} className="org-detail-metric">
                                    <div className="org-detail-metric-value">{value}</div>
                                    <div className="org-detail-metric-label">{label}</div>
                                </div>
                            ))}
                        </div>

                        {/* Tier management */}
                        <div className="drawer-section">
                            <div className="drawer-section-title">Subscription Tier</div>
                            <div className="org-tier-grid">
                                {TIER_OPTIONS.map(t => (
                                    <button
                                        key={t}
                                        className={`org-tier-option ${(tierEdit ?? org.tier) === t ? 'org-tier-option--selected' : ''}`}
                                        onClick={() => setTierEdit(t)}
                                    >
                                        <span className="org-tier-name">{t.replace('_', ' ')}</span>
                                        <span className="org-tier-price">{TIER_PRICES[t]}</span>
                                    </button>
                                ))}
                            </div>
                            {tierEdit && tierEdit !== org.tier && (
                                <button
                                    className="btn btn--primary"
                                    style={{ marginTop: 12 }}
                                    disabled={updateMutation.isPending}
                                    onClick={() => updateMutation.mutate({ tier: tierEdit })}
                                >
                                    {updateMutation.isPending ? 'Saving…' : `Upgrade to ${tierEdit}`}
                                </button>
                            )}
                        </div>

                        {/* Suspension */}
                        <div className="drawer-section drawer-danger-zone">
                            <div className="drawer-section-title">Danger Zone</div>
                            <div className="drawer-danger-desc">
                                {org.is_active
                                    ? 'Suspending will prevent all users in this org from logging in.'
                                    : 'This organisation is currently suspended.'}
                            </div>
                            <button
                                className={`btn ${org.is_active ? 'btn--danger' : 'btn--secondary'}`}
                                disabled={updateMutation.isPending}
                                onClick={() => updateMutation.mutate({ is_active: !org.is_active })}
                            >
                                {org.is_active ? '⛔ Suspend Organisation' : '✅ Reactivate Organisation'}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </>
    )
}
