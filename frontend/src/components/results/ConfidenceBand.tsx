/**
 * ConfidenceBand — Colour-coded CI chip + expandable tooltip
 * Used on every line-item row in the reconciliation results table.
 */
import { useState } from 'react'
import './ConfidenceBand.css'

interface FieldCI {
    field: string
    value: number
    ci: {
        '90': [number, number]
        '95': [number, number]
        '99': [number, number]
    }
    sigma: number
    grade: 'green' | 'amber' | 'red'
    ocr_confidence: number
    doc_type?: string
    item_index?: number
    item_description?: string
}

const GRADE_COLORS = {
    green: { bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.4)', text: '#10b981' },
    amber: { bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.4)', text: '#f59e0b' },
    red: { bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.4)', text: '#ef4444' },
}
const GRADE_LABELS = { green: '< 1%', amber: '1–5%', red: '> 5%' }

interface Props {
    band: FieldCI
    compact?: boolean
}

export default function ConfidenceBand({ band, compact = false }: Props) {
    const [open, setOpen] = useState(false)
    const colors = GRADE_COLORS[band.grade]

    const chipWidth = Math.round((band.ci['95'][1] - band.ci['95'][0]) / Math.max(Math.abs(band.value), 1) * 100)

    return (
        <div className="ci-wrap" style={{ position: 'relative' }}>
            <button
                className="ci-chip"
                style={{
                    background: colors.bg,
                    border: `1px solid ${colors.border}`,
                    color: colors.text,
                }}
                onClick={() => setOpen(o => !o)}
                title="Click for confidence intervals"
            >
                {!compact && (
                    <span className="ci-bar-track">
                        <span
                            className="ci-bar"
                            style={{ width: `${Math.min(chipWidth, 100)}%`, background: colors.text }}
                        />
                    </span>
                )}
                <span className="ci-grade-label">{GRADE_LABELS[band.grade]}</span>
                <span className="ci-chevron">{open ? '▲' : '▼'}</span>
            </button>

            {open && (
                <div className="ci-tooltip">
                    <div className="ci-tooltip-title">
                        Confidence Intervals — {band.field}
                    </div>
                    <div className="ci-tooltip-value">
                        Value: <strong>{band.value.toLocaleString()}</strong>
                    </div>
                    {(['90', '95', '99'] as const).map(level => (
                        <div key={level} className="ci-level-row">
                            <span className="ci-level-pct">{level}%</span>
                            <span className="ci-level-range">
                                [{band.ci[level][0].toFixed(2)}, {band.ci[level][1].toFixed(2)}]
                            </span>
                            <span className="ci-level-width">
                                ±{((band.ci[level][1] - band.ci[level][0]) / 2).toFixed(2)}
                            </span>
                        </div>
                    ))}
                    <div className="ci-tooltip-meta">
                        OCR confidence: {(band.ocr_confidence * 100).toFixed(0)}% · σ = {band.sigma.toFixed(4)}
                    </div>
                </div>
            )}
        </div>
    )
}

/** Render a row of CI chips for all fields matching a line-item index */
export function ConfidenceBandRow({ bands, docType, itemIndex }: {
    bands: FieldCI[]
    docType: string
    itemIndex: number
}) {
    const relevant = bands.filter(b => b.doc_type === docType && b.item_index === itemIndex)
    if (!relevant.length) return null
    return (
        <div className="ci-row">
            {relevant.map(b => (
                <ConfidenceBand key={b.field} band={b} compact />
            ))}
        </div>
    )
}
