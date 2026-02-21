import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-toastify'
import { motion, AnimatePresence } from 'framer-motion'
import { Upload, FileText, CheckCircle, ArrowRight, Loader, AlertTriangle } from 'lucide-react'
import { api } from '../services/api'
import { useAppStore } from '../store/useAppStore'

type DocSlot = 'po' | 'grn' | 'invoice'

const DOC_CONFIG: Record<DocSlot, { label: string; subtitle: string; color: string; icon: string }> = {
    po: {
        label: 'Purchase Order',
        subtitle: 'Upload your PO document',
        color: 'var(--color-accent)',
        icon: '📋',
    },
    grn: {
        label: 'Goods Receipt Note',
        subtitle: 'Upload your GRN document',
        color: 'var(--color-cyan)',
        icon: '📦',
    },
    invoice: {
        label: 'Supplier Invoice',
        subtitle: 'Upload the vendor invoice',
        color: '#a855f7',
        icon: '🧾',
    },
}

function DropZone({
    slot,
    onUploaded,
    uploaded,
}: {
    slot: DocSlot
    onUploaded: (slot: DocSlot, data: any) => void
    uploaded: any | null
}) {
    const [loading, setLoading] = useState(false)
    const cfg = DOC_CONFIG[slot]

    const onDrop = useCallback(
        async (accepted: File[]) => {
            const file = accepted[0]
            if (!file) return
            setLoading(true)
            try {
                const result = await api.uploadDocument(file)
                onUploaded(slot, result)
                toast.success(`${cfg.label} uploaded & processed!`)
            } catch (err: any) {
                toast.error(`Upload failed: ${err?.response?.data?.detail || err.message}`)
            } finally {
                setLoading(false)
            }
        },
        [slot, cfg.label, onUploaded]
    )

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: { 'application/pdf': ['.pdf'], 'image/*': ['.png', '.jpg', '.jpeg', '.tiff'] },
        maxFiles: 1,
        disabled: loading,
    })

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
                background: uploaded
                    ? `rgba(34,197,94,0.07)`
                    : isDragActive
                        ? `rgba(99,102,241,0.1)`
                        : 'var(--glass-bg)',
                border: `2px dashed ${uploaded ? 'rgba(34,197,94,0.4)' : isDragActive ? cfg.color : 'var(--glass-border)'}`,
                borderRadius: 'var(--radius-xl)',
                padding: '2.5rem',
                cursor: loading ? 'wait' : 'pointer',
                transition: 'all 0.25s ease',
                backdropFilter: 'blur(16px)',
                textAlign: 'center',
            }}
            {...(getRootProps() as any)}
        >
            <input {...getInputProps()} />

            {/* Icon Badge */}
            <div style={{
                width: 64, height: 64, margin: '0 auto 1.25rem',
                borderRadius: 16,
                background: uploaded ? 'rgba(34,197,94,0.15)' : `${cfg.color}18`,
                border: `1px solid ${uploaded ? 'rgba(34,197,94,0.4)' : `${cfg.color}40`}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '1.75rem',
                boxShadow: uploaded ? '0 4px 20px rgba(34,197,94,0.2)' : `0 4px 20px ${cfg.color}20`,
            }}>
                {loading ? <Loader size={28} color={cfg.color} className="animate-spin" /> :
                    uploaded ? <CheckCircle size={28} color="#22c55e" /> : cfg.icon}
            </div>

            <h3 style={{ color: 'var(--text-primary)', marginBottom: '0.4rem', fontSize: '1rem' }}>
                {cfg.label}
            </h3>

            {uploaded ? (
                <>
                    <div style={{ fontSize: '0.8rem', color: '#86efac', marginBottom: '0.5rem' }}>
                        ✅ {uploaded.filename}
                    </div>
                    <div className="badge badge-success" style={{ display: 'inline-flex', gap: '0.4rem' }}>
                        {uploaded.document_type.replace('_', ' ')} · {(uploaded.classification_confidence * 100).toFixed(0)}% confidence
                    </div>
                    <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        ID: <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>
                            {uploaded.document_id.slice(0, 12)}...
                        </code>
                    </div>
                </>
            ) : (
                <>
                    <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                        {isDragActive ? 'Drop it here!' : cfg.subtitle}
                    </p>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {loading ? 'Processing with AI pipeline...' : 'Drag & drop or click to browse · PDF, PNG, JPG, TIFF'}
                    </p>
                </>
            )}
        </motion.div>
    )
}

export default function UploadPage() {
    const navigate = useNavigate()
    const { setPoDoc, setGrnDoc, setInvoiceDoc, setActiveSessionId } = useAppStore()
    const [uploads, setUploads] = useState<Record<DocSlot, any | null>>({
        po: null, grn: null, invoice: null,
    })
    const [creating, setCreating] = useState(false)

    const allUploaded = uploads.po && uploads.grn && uploads.invoice

    const handleUploaded = (slot: DocSlot, data: any) => {
        setUploads((prev) => ({ ...prev, [slot]: data }))
        if (slot === 'po') setPoDoc(data)
        if (slot === 'grn') setGrnDoc(data)
        if (slot === 'invoice') setInvoiceDoc(data)
    }

    const startReconciliation = async () => {
        if (!allUploaded) return
        setCreating(true)
        try {
            const session = await api.createSession({
                po_document_id: uploads.po.document_id,
                grn_document_id: uploads.grn.document_id,
                invoice_document_id: uploads.invoice.document_id,
            })
            setActiveSessionId(session.id)

            await api.runReconciliation(session.id)
            toast.success('Reconciliation workflow started!')
            navigate(`/reconciliation/${session.id}`)
        } catch (err: any) {
            toast.error(`Failed: ${err?.response?.data?.detail || err.message}`)
        } finally {
            setCreating(false)
        }
    }

    return (
        <div className="animate-fade-in">
            <div className="page-header">
                <h1>Upload Documents</h1>
                <p>Upload all three documents below to initiate the three-way match audit.</p>
            </div>

            {/* Document Upload Grid */}
            <div className="three-col" style={{ marginBottom: 'var(--space-xl)' }}>
                {(Object.keys(DOC_CONFIG) as DocSlot[]).map((slot) => (
                    <DropZone key={slot} slot={slot} onUploaded={handleUploaded} uploaded={uploads[slot]} />
                ))}
            </div>

            {/* Info Banner */}
            <div className="glass-card" style={{
                marginBottom: 'var(--space-xl)',
                borderLeft: '3px solid var(--color-accent)',
                background: 'rgba(99,102,241,0.05)',
            }}>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
                    <AlertTriangle size={18} color="var(--color-accent-light)" style={{ flexShrink: 0, marginTop: 2 }} />
                    <div>
                        <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--text-accent)' }}>What happens next?</div>
                        <p style={{ fontSize: '0.85rem' }}>
                            After uploading, the system runs a 6-agent pipeline: Document Classification →
                            Bounding-Box Extraction → Mathematical Validation → Compliance Check →
                            SAMR Hallucination Detection → Three-Way Match → Workpaper Generation.
                            You'll see real-time progress via WebSocket.
                        </p>
                    </div>
                </div>
            </div>

            {/* CTA Button */}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <motion.button
                    className="btn btn-primary"
                    style={{
                        fontSize: '1rem', padding: '0.8rem 2rem',
                        opacity: allUploaded && !creating ? 1 : 0.5,
                    }}
                    disabled={!allUploaded || creating}
                    onClick={startReconciliation}
                    whileHover={{ scale: allUploaded ? 1.03 : 1 }}
                    whileTap={{ scale: 0.98 }}
                >
                    {creating ? (
                        <><Loader size={18} className="animate-spin" /> Creating Session...</>
                    ) : (
                        <><ArrowRight size={18} /> Start AI Reconciliation</>
                    )}
                </motion.button>
            </div>
        </div>
    )
}
