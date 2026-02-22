/**
 * BulkUploadPage — Drag-and-drop bulk document upload
 *
 * Flow:
 * 1. Drop up to 50 PDF/image files → shows filename + classification prediction
 * 2. Submit → POST /documents/bulk → returns batch_id
 * 3. Live progress via WebSocket /ws/batch/{batch_id}
 * 4. After batch_complete: show sessions + link to results, list unmatched
 */
import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-toastify'
import apiClient from '../services/api'
import '../styles/series_a.css'

interface FileEntry {
    id: string
    file: File
    status: 'pending' | 'queued' | 'processing' | 'processed' | 'error' | 'rejected'
    docType?: string
    vendorName?: string
    reason?: string
}

const ICON: Record<string, string> = {
    purchase_order: '📋', goods_receipt_note: '📦', invoice: '🧾', unknown: '❓',
}

export default function BulkUploadPage() {
    const navigate = useNavigate()
    const [files, setFiles] = useState<FileEntry[]>([])
    const [dragActive, setDragActive] = useState(false)
    const [submitting, setSubmitting] = useState(false)
    const [batchResult, setBatchResult] = useState<null | {
        triplets: Array<{ po: string; grn: string; invoice: string; method: string; score: number }>
        unmatched: string[]
        sessions: string[]
        stats: Record<string, unknown>
    }>(null)
    const wsRef = useRef<WebSocket | null>(null)
    const inputRef = useRef<HTMLInputElement>(null)

    const addFiles = useCallback((incoming: File[]) => {
        const newEntries: FileEntry[] = incoming.slice(0, 50 - files.length).map(f => ({
            id: crypto.randomUUID(),
            file: f,
            status: 'pending' as const,
        }))
        setFiles(prev => [...prev, ...newEntries].slice(0, 50))
    }, [files.length])

    const onDrop = (e: React.DragEvent) => {
        e.preventDefault(); setDragActive(false)
        addFiles(Array.from(e.dataTransfer.files))
    }

    const onRemove = (id: string) => setFiles(prev => prev.filter(f => f.id !== id))

    const connectWS = (batchId: string) => {
        const token = localStorage.getItem('access_token') ?? ''
        const wsUrl = `${import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000'}/ws/batch/${batchId}?token=${token}`
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onmessage = (ev) => {
            const msg = JSON.parse(ev.data) as Record<string, any>
            if (msg.event === 'processing' || msg.event === 'processed') {
                setFiles(prev => prev.map(f =>
                    f.id === msg.file_id
                        ? {
                            ...f, status: msg.event === 'processing' ? 'processing' : 'processed',
                            docType: msg.doc_type, vendorName: msg.vendor_name
                        }
                        : f
                ))
            } else if (msg.event === 'batch_complete') {
                setBatchResult({
                    triplets: [],
                    sessions: Array.isArray(msg.sessions_queued) ? msg.sessions_queued : [],
                    unmatched: Array.isArray(msg.unmatched_docs) ? msg.unmatched_docs : [],
                    stats: msg.stats ?? {},
                })
                setSubmitting(false)
                ws.close()
            } else if (msg.event === 'error') {
                setFiles(prev => prev.map(f =>
                    f.id === msg.file_id ? { ...f, status: 'error', reason: msg.error } : f
                ))
            }
        }
        ws.onerror = () => toast.error('WebSocket connection lost')
    }

    const handleSubmit = async () => {
        if (!files.length) return
        setSubmitting(true)
        const fd = new FormData()
        files.forEach(f => fd.append('files', f.file))
        try {
            const res = await apiClient.post('/documents/bulk', fd, {
                headers: { 'Content-Type': 'multipart/form-data' },
            })
            const serverFiles: Array<{ filename: string; status: string; reason?: string }> = res.data.files ?? []
            setFiles(prev => prev.map(f => {
                const match = serverFiles.find(s => s.filename === f.file.name)
                return match ? { ...f, status: match.status as FileEntry['status'], reason: match.reason } : f
            }))
            connectWS(res.data.batch_id)
            toast.info(`Batch started — processing ${res.data.accepted} files`)
        } catch (e: any) {
            toast.error('Upload failed: ' + (e.response?.data?.detail ?? e.message))
            setSubmitting(false)
        }
    }

    return (
        <div className="bulk-page">
            <div className="bulk-header">
                <div>
                    <h1 className="bulk-title">Bulk Reconciliation</h1>
                    <p className="bulk-sub">
                        Upload up to 50 PO, GRN, and Invoice files at once. Ventro auto-groups them into
                        matched triplets and runs reconciliation for each.
                    </p>
                </div>
                <button className="btn btn--secondary" onClick={() => navigate('/')}>← Back</button>
            </div>

            {!batchResult && (
                <>
                    <div
                        className={`bulk-dropzone${dragActive ? ' bulk-dropzone--active' : ''}${files.length >= 50 ? ' bulk-dropzone--full' : ''}`}
                        onDragOver={e => { e.preventDefault(); setDragActive(true) }}
                        onDragLeave={() => setDragActive(false)}
                        onDrop={onDrop}
                        onClick={() => inputRef.current?.click()}
                    >
                        <input
                            ref={inputRef}
                            type="file"
                            multiple
                            accept=".pdf,.png,.jpg,.jpeg,.tiff"
                            style={{ display: 'none' }}
                            onChange={e => addFiles(Array.from(e.target.files ?? []))}
                        />
                        <div className="bulk-drop-icon">📁</div>
                        <div className="bulk-drop-title">
                            {files.length === 0
                                ? 'Drop PDF, PNG, JPEG or TIFF files here'
                                : `${files.length} file${files.length !== 1 ? 's' : ''} selected (max 50)`}
                        </div>
                        <div className="bulk-drop-sub">Ventro auto-classifies each file as PO, GRN, or Invoice</div>
                    </div>

                    {files.length > 0 && (
                        <div className="bulk-file-list">
                            <div className="bulk-file-list-header">
                                <span>{files.length} files</span>
                                <button className="btn btn--ghost" onClick={() => setFiles([])}>Clear all</button>
                            </div>
                            {files.map(f => (
                                <div key={f.id} className={`bulk-file-row bulk-file-row--${f.status}`}>
                                    <span className="bulk-file-type-icon">{ICON[f.docType ?? 'unknown']}</span>
                                    <div className="bulk-file-info">
                                        <span className="bulk-file-name">{f.file.name}</span>
                                        {f.docType && <span className="bulk-file-dtype">{f.docType.replace('_', ' ')}</span>}
                                        {f.vendorName && <span className="bulk-file-vendor">{f.vendorName}</span>}
                                        {f.reason && <span className="bulk-file-error">{f.reason}</span>}
                                    </div>
                                    <span className={`bulk-status-dot bulk-status-dot--${f.status}`} />
                                    <span className="bulk-file-size">{(f.file.size / 1024).toFixed(0)} KB</span>
                                    {f.status === 'pending' && (
                                        <button className="bulk-remove-btn" onClick={() => onRemove(f.id)}>✕</button>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="bulk-actions">
                        <div className="bulk-hint">
                            📌 Upload files from the same transactions together — Ventro groups by vendor name and document number automatically.
                        </div>
                        <button
                            className="btn btn--primary bulk-run-btn"
                            disabled={!files.length || submitting}
                            onClick={handleSubmit}
                        >
                            {submitting
                                ? <><span className="btn-spinner" /> Processing…</>
                                : `🚀 Run Batch (${files.length} files)`}
                        </button>
                    </div>
                </>
            )}

            {batchResult && (
                <div className="bulk-results">
                    <div className="bulk-results-title">✅ Batch Complete</div>
                    <div className="bulk-results-stats">
                        <div className="bulk-stat">
                            <span className="bulk-stat-val">{batchResult.sessions.length}</span>
                            <span className="bulk-stat-label">Sessions queued</span>
                        </div>
                        <div className="bulk-stat">
                            <span className="bulk-stat-val">{batchResult.unmatched.length}</span>
                            <span className="bulk-stat-label">Unmatched docs</span>
                        </div>
                    </div>

                    <div className="bulk-sessions-title">Reconciliation sessions</div>
                    <div className="bulk-sessions">
                        {batchResult.sessions.map((sid, i) => (
                            <div key={sid} className="bulk-session-row" onClick={() => navigate(`/sessions/${sid}`)}>
                                <span>Session {i + 1}</span>
                                <span className="bulk-session-id">{sid.slice(0, 8)}…</span>
                                <span className="bulk-session-arrow">→</span>
                            </div>
                        ))}
                    </div>

                    {batchResult.unmatched.length > 0 && (
                        <div className="bulk-unmatched">
                            <div className="bulk-unmatched-title">
                                ⚠ {batchResult.unmatched.length} unmatched document{batchResult.unmatched.length > 1 ? 's' : ''}
                            </div>
                            <div className="bulk-unmatched-desc">
                                These files couldn't be automatically grouped. Upload them again as part of a manual session.
                            </div>
                        </div>
                    )}

                    <button className="btn btn--secondary" onClick={() => { setFiles([]); setBatchResult(null) }}>
                        Start Another Batch
                    </button>
                </div>
            )}
        </div>
    )
}
