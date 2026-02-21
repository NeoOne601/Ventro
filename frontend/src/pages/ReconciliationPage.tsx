import { useEffect, useState, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
    CheckCircle, AlertTriangle, Clock, Cpu, Shield, Scale, FileText,
    ChevronRight, ExternalLink, X
} from 'lucide-react'
import { api, createWebSocket } from '../services/api'
import { useAppStore } from '../store/useAppStore'

const AGENT_STEPS = [
    { id: 'extraction', icon: <FileText size={16} />, label: 'Document Extraction', desc: 'Retrieving spatial data from vector store' },
    { id: 'quantitative', icon: <Scale size={16} />, label: 'Math Validation', desc: 'Re-calculating all figures deterministically' },
    { id: 'compliance', icon: <Shield size={16} />, label: 'Compliance Check', desc: 'Evaluating regulatory requirements' },
    { id: 'samr', icon: <Cpu size={16} />, label: 'SAMR Check', desc: 'Shadow stream hallucination detection' },
    { id: 'reconciliation', icon: <Scale size={16} />, label: 'Three-Way Match', desc: 'Semantic entity resolution across documents' },
    { id: 'drafting', icon: <FileText size={16} />, label: 'Workpaper Generation', desc: 'Drafting interactive audit workpaper' },
]

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
    full_match: { label: 'Full Match', color: '#86efac', bg: 'rgba(34,197,94,0.12)', icon: <CheckCircle size={18} /> },
    partial_match: { label: 'Partial Match', color: '#fde047', bg: 'rgba(234,179,8,0.12)', icon: <AlertTriangle size={18} /> },
    mismatch: { label: 'Mismatch', color: '#fca5a5', bg: 'rgba(239,68,68,0.12)', icon: <AlertTriangle size={18} /> },
    exception: { label: 'Exception', color: '#d8b4fe', bg: 'rgba(168,85,247,0.12)', icon: <AlertTriangle size={18} /> },
    processing: { label: 'Processing', color: '#67e8f9', bg: 'rgba(6,182,212,0.12)', icon: <Cpu size={18} className="animate-spin" /> },
    pending: { label: 'Pending', color: '#93c5fd', bg: 'rgba(59,130,246,0.1)', icon: <Clock size={18} /> },
}

export default function ReconciliationPage() {
    const { sessionId } = useParams<{ sessionId: string }>()
    const [events, setEvents] = useState<any[]>([])
    const [activeAgents, setActiveAgents] = useState<Set<string>>(new Set())
    const [completedAgents, setCompletedAgents] = useState<Set<string>>(new Set())
    const [samrAlert, setSamrAlert] = useState<any>(null)
    const [showWorkpaper, setShowWorkpaper] = useState(false)
    const wsRef = useRef<WebSocket | null>(null)
    const { setSamrAlert: setGlobalSamrAlert } = useAppStore()

    // Poll session status
    const { data: session, refetch } = useQuery({
        queryKey: ['session-status', sessionId],
        queryFn: () => api.getSessionStatus(sessionId!),
        enabled: !!sessionId,
        refetchInterval: (data) =>
            data && ['completed', 'matched', 'failed', 'discrepancy_found', 'samr_alert'].includes(data.status)
                ? false
                : 3000,
    })

    const { data: result } = useQuery({
        queryKey: ['session-result', sessionId],
        queryFn: () => api.getSessionResult(sessionId!),
        enabled: !!sessionId && !!session && !['pending', 'processing'].includes(session?.status),
    })

    // WebSocket for progress events
    useEffect(() => {
        if (!sessionId) return
        const ws = createWebSocket(sessionId, (event) => {
            setEvents((prev) => [...prev.slice(-50), event])

            if (event.event === 'agent_started') {
                setActiveAgents((prev) => new Set([...prev, event.agent]))
            }
            if (event.event === 'agent_completed') {
                setActiveAgents((prev) => { const n = new Set(prev); n.delete(event.agent); return n })
                setCompletedAgents((prev) => new Set([...prev, event.agent]))
            }
            if (event.event === 'samr_alert') {
                setSamrAlert(event)
                setGlobalSamrAlert(true)
            }
            if (event.event === 'workflow_complete') {
                refetch()
            }
        })
        wsRef.current = ws
        return () => { ws.close(); wsRef.current = null }
    }, [sessionId])

    const verdict = result?.verdict
    const workpaper = result?.workpaper
    const statusKey = verdict?.overall_status || session?.status || 'pending'
    const statusCfg = STATUS_CONFIG[statusKey] || STATUS_CONFIG.pending

    return (
        <div className="animate-fade-in">
            <div className="page-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                    <h1>Reconciliation</h1>
                    <div className="badge" style={{ background: statusCfg.bg, color: statusCfg.color, border: `1px solid ${statusCfg.color}40` }}>
                        {statusCfg.icon} {statusCfg.label}
                    </div>
                </div>
                <p style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                    Session: {sessionId}
                </p>
            </div>

            {/* SAMR Alert Banner */}
            <AnimatePresence>
                {samrAlert && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        style={{
                            background: 'rgba(239,68,68,0.12)',
                            border: '1px solid rgba(239,68,68,0.4)',
                            borderRadius: 'var(--radius-lg)',
                            padding: '1rem 1.25rem',
                            marginBottom: '1.5rem',
                            display: 'flex', alignItems: 'flex-start', gap: '0.75rem',
                        }}
                    >
                        <AlertTriangle size={20} color="#fca5a5" style={{ flexShrink: 0 }} />
                        <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600, color: '#fca5a5', marginBottom: 4 }}>
                                ⚠️ SAMR Alert: Reasoning Divergence Detected
                            </div>
                            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                                The Shadow Agent detected potential hallucination. Human review is mandatory before finalizing this audit.
                                Cosine similarity exceeded threshold.
                            </div>
                        </div>
                        <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                            onClick={() => setSamrAlert(null)}>
                            <X size={16} />
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="two-col" style={{ alignItems: 'start' }}>
                {/* Agent Pipeline */}
                <div>
                    <div className="glass-card" style={{ marginBottom: 'var(--space-lg)' }}>
                        <h3 style={{ marginBottom: '1.25rem', color: 'var(--text-accent)' }}>
                            <Cpu size={16} style={{ display: 'inline', marginRight: 8 }} />
                            Agent Pipeline
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                            {AGENT_STEPS.map((step, i) => {
                                const isActive = activeAgents.has(step.id)
                                const isDone = completedAgents.has(step.id)
                                return (
                                    <div key={step.id} style={{
                                        display: 'flex', alignItems: 'center', gap: '1rem',
                                        padding: '0.75rem 1rem',
                                        borderRadius: 'var(--radius-md)',
                                        background: isActive ? 'rgba(99,102,241,0.1)' : isDone ? 'rgba(34,197,94,0.06)' : 'var(--glass-bg)',
                                        border: `1px solid ${isActive ? 'rgba(99,102,241,0.3)' : isDone ? 'rgba(34,197,94,0.2)' : 'var(--glass-border)'}`,
                                        transition: 'all 0.3s ease',
                                    }}>
                                        {/* Step number / check */}
                                        <div style={{
                                            width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            background: isDone ? 'rgba(34,197,94,0.2)' : isActive ? 'rgba(99,102,241,0.2)' : 'rgba(255,255,255,0.05)',
                                            color: isDone ? '#22c55e' : isActive ? 'var(--color-accent-light)' : 'var(--text-muted)',
                                            fontSize: '0.75rem', fontWeight: 700,
                                        }}>
                                            {isDone ? <CheckCircle size={14} /> : isActive ? <div className="animate-spin" style={{ width: 14, height: 14, border: '2px solid var(--color-accent)', borderTopColor: 'transparent', borderRadius: '50%' }} /> : i + 1}
                                        </div>
                                        <div style={{ flex: 1 }}>
                                            <div style={{
                                                fontSize: '0.875rem', fontWeight: 600,
                                                color: isDone ? '#86efac' : isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                                            }}>
                                                {step.label}
                                            </div>
                                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                                {step.desc}
                                            </div>
                                        </div>
                                        {isActive && (
                                            <div style={{ fontSize: '0.7rem', color: 'var(--color-accent-light)', fontFamily: 'var(--font-mono)' }}>
                                                Running...
                                            </div>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    </div>

                    {/* Live Event Log */}
                    <div className="glass-card">
                        <h3 style={{ marginBottom: '0.75rem', color: 'var(--text-accent)', fontSize: '0.95rem' }}>Live Event Log</h3>
                        <div style={{ height: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
                            {events.length === 0 ? (
                                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', padding: '0.5rem' }}>
                                    Waiting for events...
                                </div>
                            ) : (
                                events.map((ev, i) => (
                                    <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                                        style={{
                                            fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)',
                                            padding: '0.2rem 0.5rem', borderRadius: 4,
                                            background: ev.event === 'samr_alert' ? 'rgba(239,68,68,0.08)' : 'transparent',
                                        }}>
                                        <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>
                                            {new Date(ev.timestamp * 1000).toLocaleTimeString()}
                                        </span>
                                        {ev.event}: {ev.message || ev.agent || ev.status || ''}
                                    </motion.div>
                                ))
                            )}
                        </div>
                    </div>
                </div>

                {/* Results Panel */}
                <div>
                    {verdict ? (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                            {/* Verdict Card */}
                            <div className="glass-card" style={{
                                marginBottom: 'var(--space-lg)',
                                background: statusCfg.bg,
                                border: `1px solid ${statusCfg.color}40`,
                            }}>
                                <div style={{ color: statusCfg.color, fontSize: '2rem', marginBottom: '0.5rem' }}>
                                    {statusCfg.icon}
                                </div>
                                <h2 style={{ color: statusCfg.color, marginBottom: '0.5rem' }}>{statusCfg.label}</h2>
                                <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
                                    Confidence: <strong style={{ color: 'var(--text-primary)' }}>
                                        {((verdict.confidence || 0) * 100).toFixed(0)}%
                                    </strong>
                                    {' · '}
                                    Recommendation: <strong style={{ color: statusCfg.color }}>
                                        {(verdict.recommendation || 'N/A').replace(/_/g, ' ')}
                                    </strong>
                                </div>
                                {verdict.discrepancy_summary?.length > 0 && (
                                    <div>
                                        {verdict.discrepancy_summary.map((d: string, i: number) => (
                                            <div key={i} style={{ fontSize: '0.8rem', color: '#fde047', marginTop: 4 }}>
                                                ⚠ {d}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* SAMR Metrics */}
                            {result?.samr_metrics && (
                                <div className="glass-card" style={{ marginBottom: 'var(--space-lg)' }}>
                                    <h3 style={{ marginBottom: '0.75rem', color: 'var(--text-accent)', fontSize: '0.95rem' }}>
                                        🛡️ SAMR Report
                                    </h3>
                                    <div style={{ fontSize: '0.85rem' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', margin: '4px 0' }}>
                                            <span style={{ color: 'var(--text-muted)' }}>Cosine Similarity</span>
                                            <strong style={{ fontFamily: 'var(--font-mono)', color: result.samr_metrics.alert_triggered ? '#fca5a5' : '#86efac' }}>
                                                {result.samr_metrics.cosine_similarity_score?.toFixed(4)}
                                            </strong>
                                        </div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', margin: '4px 0' }}>
                                            <span style={{ color: 'var(--text-muted)' }}>Alert Status</span>
                                            <span className={`badge badge-${result.samr_metrics.alert_triggered ? 'danger' : 'success'}`}>
                                                {result.samr_metrics.alert_triggered ? 'ALERT' : 'CLEAR'}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Workpaper Button */}
                            {workpaper && (
                                <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }}
                                    onClick={() => setShowWorkpaper(true)}>
                                    <FileText size={16} /> View Interactive Workpaper <ExternalLink size={14} />
                                </button>
                            )}
                        </motion.div>
                    ) : (
                        <div className="glass-card" style={{ textAlign: 'center', padding: '3rem' }}>
                            <div className="animate-pulse-glow" style={{
                                width: 60, height: 60, borderRadius: '50%',
                                background: 'rgba(99,102,241,0.1)', border: '2px solid var(--color-accent)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem',
                            }}>
                                <Cpu size={24} color="var(--color-accent-light)" />
                            </div>
                            <h3 style={{ color: 'var(--text-secondary)' }}>Agents running...</h3>
                            <p style={{ fontSize: '0.85rem' }}>Results will appear here when complete</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Workpaper Modal */}
            <AnimatePresence>
                {showWorkpaper && workpaper && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        style={{
                            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            zIndex: 1000, padding: '2rem',
                        }}
                        onClick={() => setShowWorkpaper(false)}
                    >
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            style={{
                                width: '90vw', maxWidth: '1100px', height: '85vh',
                                borderRadius: 'var(--radius-xl)',
                                overflow: 'hidden',
                                border: '1px solid var(--glass-border)',
                            }}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <iframe
                                srcDoc={workpaper.html_content}
                                style={{ width: '100%', height: '100%', border: 'none', background: '#0a0a1a' }}
                                title="Audit Workpaper"
                            />
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    )
}
