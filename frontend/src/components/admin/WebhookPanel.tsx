/**
 * WebhookPanel — Register, test, and monitor outbound webhook endpoints
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-toastify'
import apiClient from '../../services/api'

const ALL_EVENTS = [
    { id: 'reconciliation.completed', label: '✅ Reconciliation Completed' },
    { id: 'finding.discrepancy', label: '⚠️ Discrepancy Found' },
    { id: 'session.failed', label: '❌ Session Failed' },
    { id: 'user.created', label: '👤 User Created' },
    { id: 'user.role_changed', label: '🔄 Role Changed' },
]

interface Endpoint {
    id: string; url: string; description: string; events: string[]; is_active: boolean; created_at: string
}

export default function WebhookPanel() {
    const qc = useQueryClient()
    const [showAdd, setShowAdd] = useState(false)
    const [url, setUrl] = useState('')
    const [description, setDescription] = useState('')
    const [selectedEvents, setSelectedEvents] = useState<string[]>(['reconciliation.completed'])
    const [expandedDeliveries, setExpandedDeliveries] = useState<string | null>(null)

    const { data: endpoints = [], isLoading } = useQuery<Endpoint[]>({
        queryKey: ['admin-webhooks'],
        queryFn: async () => (await apiClient.get('/admin/webhooks')).data,
    })

    const createMutation = useMutation({
        mutationFn: () => apiClient.post('/admin/webhooks', { url, description, events: selectedEvents }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['admin-webhooks'] })
            setShowAdd(false); setUrl(''); setDescription('')
            toast.success('Webhook endpoint registered')
        },
        onError: () => toast.error('Failed to register webhook'),
    })

    const deleteMutation = useMutation({
        mutationFn: (id: string) => apiClient.delete(`/admin/webhooks/${id}`),
        onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-webhooks'] }); toast.success('Webhook removed') },
    })

    const testMutation = useMutation({
        mutationFn: (id: string) => apiClient.post(`/admin/webhooks/${id}/test`),
        onSuccess: (res) => {
            const result = res.data
            result.success
                ? toast.success(`Test ping delivered (HTTP ${result.status_code})`)
                : toast.error(`Test failed: ${result.error ?? `HTTP ${result.status_code}`}`)
        },
    })

    const toggleEvent = (evId: string) => setSelectedEvents(ev =>
        ev.includes(evId) ? ev.filter(e => e !== evId) : [...ev, evId]
    )

    return (
        <div className="webhook-panel">
            <div className="webhook-header">
                <div>
                    <h3 className="webhook-title">Outbound Webhooks</h3>
                    <p className="webhook-subtitle">
                        Ventro will POST signed JSON to your endpoints on selected events.
                        Requests include <code>X-Ventro-Signature: sha256=…</code> for verification.
                    </p>
                </div>
                <button className="btn btn--primary" onClick={() => setShowAdd(s => !s)}>
                    {showAdd ? 'Cancel' : '+ Add Endpoint'}
                </button>
            </div>

            {/* Add endpoint form */}
            {showAdd && (
                <div className="webhook-add-form">
                    <div className="auth-field">
                        <label>Endpoint URL</label>
                        <input type="url" placeholder="https://hooks.example.com/ventro"
                            value={url} onChange={e => setUrl(e.target.value)} required />
                    </div>
                    <div className="auth-field">
                        <label>Description (optional)</label>
                        <input type="text" placeholder="Slack alerting channel"
                            value={description} onChange={e => setDescription(e.target.value)} />
                    </div>
                    <div className="auth-field">
                        <label>Events to subscribe</label>
                        <div className="webhook-event-grid">
                            {ALL_EVENTS.map(ev => (
                                <label key={ev.id} className={`webhook-event-chip ${selectedEvents.includes(ev.id) ? 'webhook-event-chip--on' : ''}`}>
                                    <input type="checkbox" checked={selectedEvents.includes(ev.id)}
                                        onChange={() => toggleEvent(ev.id)} style={{ display: 'none' }} />
                                    {ev.label}
                                </label>
                            ))}
                        </div>
                    </div>
                    <button className="btn btn--primary"
                        onClick={() => createMutation.mutate()}
                        disabled={!url || selectedEvents.length === 0 || createMutation.isPending}>
                        {createMutation.isPending ? 'Registering…' : 'Register Endpoint'}
                    </button>
                </div>
            )}

            {/* Endpoint list */}
            {isLoading ? <div className="admin-loading">Loading…</div> : endpoints.length === 0 ? (
                <div className="webhook-empty">
                    <div className="webhook-empty-icon">🔔</div>
                    <p>No webhook endpoints yet. Add one to receive real-time notifications.</p>
                </div>
            ) : (
                <div className="webhook-list">
                    {endpoints.map(ep => (
                        <div key={ep.id} className="webhook-endpoint">
                            <div className="webhook-ep-top">
                                <div>
                                    <div className="webhook-ep-url">{ep.url}</div>
                                    {ep.description && <div className="webhook-ep-desc">{ep.description}</div>}
                                    <div className="webhook-ep-events">
                                        {ep.events.map(ev => <span key={ev} className="webhook-ep-tag">{ev}</span>)}
                                    </div>
                                </div>
                                <div className="webhook-ep-actions">
                                    <button className="admin-action" title="Send test ping"
                                        onClick={() => testMutation.mutate(ep.id)}
                                        disabled={testMutation.isPending}>
                                        🔔
                                    </button>
                                    <button className="admin-action"
                                        title="View delivery log"
                                        onClick={() => setExpandedDeliveries(d => d === ep.id ? null : ep.id)}>
                                        📋
                                    </button>
                                    <button className="admin-action admin-action--danger" title="Remove"
                                        onClick={() => { if (confirm('Remove this webhook?')) deleteMutation.mutate(ep.id) }}>
                                        🗑
                                    </button>
                                </div>
                            </div>

                            {/* Delivery log */}
                            {expandedDeliveries === ep.id && (
                                <DeliveryLog endpointId={ep.id} />
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

function DeliveryLog({ endpointId }: { endpointId: string }) {
    const { data: deliveries = [] } = useQuery({
        queryKey: ['webhook-deliveries', endpointId],
        queryFn: async () => (await apiClient.get(`/admin/webhooks/${endpointId}/deliveries`)).data,
    })
    return (
        <div className="webhook-deliveries">
            <div className="webhook-deliveries-title">Last 20 deliveries</div>
            {deliveries.length === 0 ? <div className="webhook-ep-desc">No deliveries yet</div> : (
                <table className="admin-table webhook-delivery-table">
                    <thead><tr><th>Event</th><th>Status</th><th>Attempt</th><th>Time</th></tr></thead>
                    <tbody>
                        {deliveries.map((d: any, i: number) => (
                            <tr key={i}>
                                <td><span className="webhook-ep-tag">{d.event}</span></td>
                                <td>
                                    <span className={d.status_code >= 200 && d.status_code < 300 ? 'admin-status--active' : 'admin-status--inactive'}>
                                        {d.status_code ?? 'ERR'} {d.error ? `— ${d.error}` : ''}
                                    </span>
                                </td>
                                <td>#{d.attempt}</td>
                                <td className="admin-muted">{new Date(d.delivered_at).toLocaleString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    )
}
