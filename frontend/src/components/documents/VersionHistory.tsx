/**
 * VersionHistory — Document version timeline with diff viewer
 * Shows in a slide-over from the document detail view.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../../services/api'
import './VersionHistory.css'

interface VersionSummary {
    document_id: string
    version: number
    created_at: string
    replaced_reason: string
    line_item_count: number
    metadata: { filename: string; vendor_name?: string; document_number?: string }
}

interface Props {
    documentId: string
    onClose: () => void
}

const REASON_LABELS: Record<string, string> = {
    upload: '⬆ First upload',
    user_correction: '✏ Corrected re-upload',
    auto_reprocess: '🔄 Auto-reprocess',
}

export default function VersionHistory({ documentId, onClose }: Props) {
    const [comparing, setComparing] = useState<[number, number] | null>(null)

    const { data: history = [], isLoading } = useQuery<VersionSummary[]>({
        queryKey: ['doc-history', documentId],
        queryFn: async () => (await apiClient.get(`/documents/${documentId}/history`)).data,
    })

    const { data: diff, isLoading: diffLoading } = useQuery({
        queryKey: ['doc-diff', documentId, comparing?.[0], comparing?.[1]],
        queryFn: async () => (await apiClient.get(
            `/documents/${documentId}/diff/${comparing![0]}/${comparing![1]}`
        )).data,
        enabled: !!comparing,
    })

    return (
        <>
            <div className="drawer-backdrop" onClick={onClose} />
            <div className="drawer vh-drawer">
                <div className="drawer-header">
                    <div>
                        <div className="drawer-title">Version History</div>
                        <div className="drawer-subtitle">{history[0]?.metadata?.filename}</div>
                    </div>
                    <button className="drawer-close" onClick={onClose}>✕</button>
                </div>

                <div className="vh-body">
                    {isLoading ? <div className="admin-loading">Loading…</div> : (
                        <>
                            {/* Timeline */}
                            <div className="vh-timeline">
                                {history.map((v, i) => (
                                    <div key={v.version} className={`vh-entry ${i === 0 ? 'vh-entry--latest' : ''}`}>
                                        <div className="vh-dot" />
                                        <div className="vh-entry-content">
                                            <div className="vh-entry-header">
                                                <span className="vh-version">v{v.version}</span>
                                                <span className="vh-reason">{REASON_LABELS[v.replaced_reason] ?? v.replaced_reason}</span>
                                                {i === 0 && <span className="vh-current-badge">Current</span>}
                                            </div>
                                            <div className="vh-entry-meta">
                                                {new Date(v.created_at).toLocaleString()} · {v.line_item_count} line items
                                                {v.metadata?.vendor_name && ` · ${v.metadata.vendor_name}`}
                                            </div>
                                            {/* Compare button — only if previous version exists */}
                                            {i < history.length - 1 && (
                                                <button
                                                    className="vh-compare-btn"
                                                    onClick={() => setComparing([history[i + 1].version, v.version])}
                                                >
                                                    Compare with v{history[i + 1].version}
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* Diff panel */}
                            {comparing && (
                                <div className="vh-diff">
                                    <div className="vh-diff-title">
                                        Diff: v{comparing[0]} → v{comparing[1]}
                                        <button className="drawer-close" onClick={() => setComparing(null)}>✕</button>
                                    </div>
                                    {diffLoading ? <div className="admin-loading">Computing diff…</div> : diff && (
                                        <>
                                            {diff.metadata_changes?.length > 0 && (
                                                <div className="vh-diff-section">
                                                    <div className="vh-diff-label">Metadata changes</div>
                                                    {diff.metadata_changes.map((c: any) => (
                                                        <div key={c.field} className="vh-diff-row">
                                                            <span className="vh-diff-field">{c.field}</span>
                                                            <span className="vh-diff-before">— {String(c.before)}</span>
                                                            <span className="vh-diff-after">+ {String(c.after)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                            {diff.line_item_changes?.added?.length > 0 && (
                                                <div className="vh-diff-section">
                                                    <div className="vh-diff-label">Added line items ({diff.line_item_changes.added.length})</div>
                                                    {diff.line_item_changes.added.map((item: any, i: number) => (
                                                        <div key={i} className="vh-diff-row vh-diff-row--added">+ {item.description}</div>
                                                    ))}
                                                </div>
                                            )}
                                            {diff.line_item_changes?.removed?.length > 0 && (
                                                <div className="vh-diff-section">
                                                    <div className="vh-diff-label">Removed line items ({diff.line_item_changes.removed.length})</div>
                                                    {diff.line_item_changes.removed.map((item: any, i: number) => (
                                                        <div key={i} className="vh-diff-row vh-diff-row--removed">— {item.description}</div>
                                                    ))}
                                                </div>
                                            )}
                                            {diff.line_item_changes?.changed?.length > 0 && (
                                                <div className="vh-diff-section">
                                                    <div className="vh-diff-label">Modified line items</div>
                                                    {diff.line_item_changes.changed.map((item: any, i: number) => (
                                                        <div key={i} className="vh-changed-item">
                                                            <div className="vh-changed-desc">✏ {item.description}</div>
                                                            {Object.entries(item.changes).map(([field, change]: [string, any]) => (
                                                                <div key={field} className="vh-diff-row">
                                                                    <span className="vh-diff-field">{field}</span>
                                                                    <span className="vh-diff-before">— {change.before}</span>
                                                                    <span className="vh-diff-after">+ {change.after}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                            {!diff.metadata_changes?.length && !diff.line_item_changes?.added?.length
                                                && !diff.line_item_changes?.removed?.length && !diff.line_item_changes?.changed?.length && (
                                                    <div className="vh-no-diff">No changes between these versions.</div>
                                                )}
                                        </>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </>
    )
}
