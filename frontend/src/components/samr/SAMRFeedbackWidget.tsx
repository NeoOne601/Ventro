/**
 * SAMRFeedbackWidget
 * Shown below SAMR metrics on the results page.
 * Lets analysts submit correct / false_positive / false_negative feedback.
 * Shows current adaptive threshold + 30-day trend if available.
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'react-toastify'
import apiClient from '../../services/api'
import './SAMRFeedback.css'

interface Props {
    sessionId: string
    samrTriggered: boolean
    cosineScore: number
    thresholdUsed: number
}

type Verdict = 'correct' | 'false_positive' | 'false_negative'

const LABELS: Record<Verdict, { icon: string; label: string; desc: string; color: string }> = {
    correct: { icon: '✅', label: 'Correct Alert', desc: 'Alert was right — real issue found', color: '#10b981' },
    false_positive: { icon: '🔕', label: 'False Alarm', desc: 'No real issue — threshold too sensitive', color: '#f59e0b' },
    false_negative: { icon: '⚠️', label: 'Missed Issue', desc: 'No alert was fired but there was a problem', color: '#ef4444' },
}

export default function SAMRFeedbackWidget({ sessionId, samrTriggered, cosineScore, thresholdUsed }: Props) {
    const [selected, setSelected] = useState<Verdict | null>(null)
    const [submitted, setSubmitted] = useState(false)

    const { data: analytics } = useQuery({
        queryKey: ['samr-analytics'],
        queryFn: async () => (await apiClient.get('/samr/analytics')).data,
        staleTime: 60_000,
    })

    const { data: thresholdData } = useQuery({
        queryKey: ['samr-threshold'],
        queryFn: async () => (await apiClient.get('/samr/threshold')).data,
        staleTime: 60_000,
    })

    const feedbackMutation = useMutation({
        mutationFn: (verdict: Verdict) => apiClient.post('/samr/feedback', {
            session_id: sessionId,
            feedback: verdict,
            samr_triggered: samrTriggered,
            cosine_score: cosineScore,
            threshold_used: thresholdUsed,
        }),
        onSuccess: () => {
            setSubmitted(true)
            toast.success('Feedback submitted — SAMR is learning 🧠')
        },
        onError: () => toast.error('Failed to submit feedback'),
    })

    return (
        <div className="samr-feedback">
            <div className="samr-feedback-header">
                <div>
                    <div className="samr-feedback-title">🧠 SAMR Adaptive Feedback</div>
                    <div className="samr-feedback-sub">
                        Your feedback trains the hallucination detector for your organisation.
                    </div>
                </div>
                {thresholdData && (
                    <div className="samr-threshold-badge">
                        Threshold: <strong>{thresholdData.threshold.toFixed(3)}</strong>
                        <span className="samr-threshold-src">
                            {thresholdData.threshold !== thresholdData.global_prior ? ' (adaptive)' : ' (default)'}
                        </span>
                    </div>
                )}
            </div>

            {submitted ? (
                <div className="samr-submitted">
                    ✅ Feedback recorded. The threshold will update before your next session.
                </div>
            ) : (
                <>
                    <div className="samr-feedback-prompt">
                        {samrTriggered
                            ? 'Was this SAMR hallucination alert correct?'
                            : 'No SAMR alert was fired. Was that the right call?'}
                    </div>
                    <div className="samr-verdict-row">
                        {(Object.entries(LABELS) as [Verdict, typeof LABELS[Verdict]][]).map(([v, meta]) => (
                            <button
                                key={v}
                                className={`samr-verdict-btn ${selected === v ? 'samr-verdict-btn--selected' : ''}`}
                                style={selected === v ? { borderColor: meta.color, background: `${meta.color}18` } : {}}
                                onClick={() => setSelected(v)}
                            >
                                <span className="samr-verdict-icon">{meta.icon}</span>
                                <span className="samr-verdict-label">{meta.label}</span>
                                <span className="samr-verdict-desc">{meta.desc}</span>
                            </button>
                        ))}
                    </div>
                    <button
                        className="btn btn--primary samr-submit-btn"
                        disabled={!selected || feedbackMutation.isPending}
                        onClick={() => selected && feedbackMutation.mutate(selected)}
                    >
                        {feedbackMutation.isPending ? 'Submitting…' : 'Submit Feedback'}
                    </button>
                </>
            )}

            {/* 30-day trend micro-chart */}
            {analytics?.daily_trend?.length > 0 && (
                <div className="samr-trend">
                    <div className="samr-trend-label">30-day feedback trend</div>
                    <div className="samr-trend-bars">
                        {analytics.daily_trend.map((d: any, i: number) => {
                            const total = (d.correct || 0) + (d.false_pos || 0) + (d.false_neg || 0)
                            const correctPct = total > 0 ? (d.correct / total) * 100 : 0
                            return (
                                <div key={i} className="samr-trend-bar-wrap" title={`${d.day}: ${d.correct}C ${d.false_pos}FP ${d.false_neg}FN`}>
                                    <div className="samr-trend-bar" style={{ height: `${Math.max(correctPct, 4)}%` }} />
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}
        </div>
    )
}
