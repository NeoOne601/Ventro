/**
 * Register Page — visually stunning onboarding for Ventro
 * 
 * Multi-step form:
 *   Step 1 → Organisation slug lookup (confirm the org exists)
 *   Step 2 → Personal details (name, email, password with strength meter)
 * 
 * Design: full-screen glassmorphism with animated network graph background
 * (SVG-based — pure CSS, no libraries).
 */
import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/api'
import '../styles/auth.css'
import '../styles/register.css'

// ── Password strength logic ───────────────────────────────────────────────────

function passwordStrength(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string; color: string } {
    let score = 0
    if (pw.length >= 12) score++
    if (/[A-Z]/.test(pw)) score++
    if (/[0-9]/.test(pw)) score++
    if (/[^A-Za-z0-9]/.test(pw)) score++
    const labels = ['Too weak', 'Weak', 'Fair', 'Strong', 'Very strong']
    const colors = ['#ef4444', '#f97316', '#f59e0b', '#10b981', '#06b6d4']
    return { score: score as 0 | 1 | 2 | 3 | 4, label: labels[score], color: colors[score] }
}

// ── Role descriptions shown to new users ─────────────────────────────────────

const ROLE_INFO: Record<string, { icon: string; desc: string }> = {
    ap_analyst: { icon: '👨‍💼', desc: 'Upload documents, create and run reconciliations' },
    ap_manager: { icon: '🧑‍💼', desc: 'Approve findings, sign workpapers, manage sessions' },
    finance_director: { icon: '📊', desc: 'Full analytics, audit log, billing overview' },
    external_auditor: { icon: '🔍', desc: 'Read-only access to sessions and workpapers' },
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function RegisterPage() {
    const navigate = useNavigate()
    const [step, setStep] = useState<1 | 2>(1)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState('')
    const [success, setSuccess] = useState(false)

    const [orgSlug, setOrgSlug] = useState('')
    const [fullName, setFullName] = useState('')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [confirmPw, setConfirmPw] = useState('')
    const [showPw, setShowPw] = useState(false)

    const strength = passwordStrength(password)

    const handleStep1 = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        if (!orgSlug.trim()) return
        setStep(2)
    }

    const handleStep2 = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        if (password !== confirmPw) { setError('Passwords do not match'); return }
        if (strength.score < 2) { setError('Please choose a stronger password (min. 12 chars, uppercase, number, symbol)'); return }

        setSubmitting(true)
        try {
            await authApi.register({
                email, full_name: fullName, password, org_slug: orgSlug,
            })
            setSuccess(true)
            setTimeout(() => navigate('/login', { state: { registered: true } }), 2800)
        } catch (err: any) {
            setError(err.response?.data?.detail ?? err.message ?? 'Registration failed')
        } finally {
            setSubmitting(false)
        }
    }

    if (success) {
        return (
            <div className="auth-page">
                <div className="auth-bg">
                    <div className="auth-bg-blob auth-bg-blob-1" />
                    <div className="auth-bg-blob auth-bg-blob-2" />
                </div>
                <div className="auth-card rg-success-card">
                    <div className="rg-success-icon">✅</div>
                    <h2 className="rg-success-title">Account created!</h2>
                    <p className="rg-success-sub">Redirecting to sign in…</p>
                    <div className="rg-success-spinner" />
                </div>
            </div>
        )
    }

    return (
        <div className="auth-page">
            {/* Animated background */}
            <div className="auth-bg">
                <div className="auth-bg-blob auth-bg-blob-1" />
                <div className="auth-bg-blob auth-bg-blob-2" />
                <div className="auth-bg-blob auth-bg-blob-3" />
            </div>

            {/* Animated SVG network in background */}
            <svg className="rg-network" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice">
                {[...Array(12)].map((_, i) => (
                    <circle
                        key={i}
                        className="rg-node"
                        cx={100 + (i % 4) * 190 + (i > 7 ? 50 : 0)}
                        cy={80 + Math.floor(i / 4) * 180}
                        r="4"
                        style={{ animationDelay: `${i * 0.3}s` }}
                    />
                ))}
                {[...Array(10)].map((_, i) => (
                    <line
                        key={i}
                        className="rg-edge"
                        x1={100 + (i % 3) * 190} y1={80 + Math.floor(i / 3) * 180}
                        x2={290 + (i % 3) * 95} y2={260 + Math.floor(i / 4) * 160}
                        style={{ animationDelay: `${i * 0.5}s` }}
                    />
                ))}
            </svg>

            <div className="auth-card rg-card">
                {/* Logo + step indicator */}
                <div className="rg-top-row">
                    <div className="auth-logo" style={{ marginBottom: 0 }}>
                        <svg width="32" height="32" viewBox="0 0 40 40" fill="none">
                            <rect width="40" height="40" rx="12" fill="url(#lgR)" />
                            <path d="M10 20L18 28L30 12" stroke="white" strokeWidth="3"
                                strokeLinecap="round" strokeLinejoin="round" />
                            <defs>
                                <linearGradient id="lgR" x1="0" y1="0" x2="40" y2="40">
                                    <stop stopColor="#6366f1" />
                                    <stop offset="1" stopColor="#8b5cf6" />
                                </linearGradient>
                            </defs>
                        </svg>
                        <span className="auth-logo-text">Ventro</span>
                    </div>

                    {/* Step breadcrumb */}
                    <div className="rg-steps">
                        <div className={`rg-step ${step >= 1 ? 'rg-step--active' : ''}`}>
                            <div className="rg-step-dot">{step > 1 ? '✓' : '1'}</div>
                            <span>Organisation</span>
                        </div>
                        <div className="rg-step-line" />
                        <div className={`rg-step ${step >= 2 ? 'rg-step--active' : ''}`}>
                            <div className="rg-step-dot">2</div>
                            <span>Your Details</span>
                        </div>
                    </div>
                </div>

                {step === 1 && (
                    <>
                        <h1 className="auth-title" style={{ marginTop: 20 }}>Join your workspace</h1>
                        <p className="auth-subtitle">Enter your organisation's unique identifier</p>

                        {error && <div className="auth-error">⚠ {error}</div>}

                        <form className="auth-form" onSubmit={handleStep1}>
                            <div className="auth-field">
                                <label htmlFor="org">Organisation slug</label>
                                <div className="rg-org-input-wrap">
                                    <span className="rg-org-prefix">ventro.io/</span>
                                    <input
                                        id="org"
                                        type="text"
                                        placeholder="acme-corp"
                                        value={orgSlug}
                                        onChange={e => setOrgSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                                        required
                                        autoFocus
                                        style={{ paddingLeft: 96 }}
                                    />
                                </div>
                                <div className="rg-org-hint">
                                    Ask your Administrator for your organisation's slug
                                </div>
                            </div>

                            {/* Role info cards */}
                            <div className="rg-role-grid">
                                {Object.entries(ROLE_INFO).map(([role, info]) => (
                                    <div key={role} className="rg-role-card">
                                        <span>{info.icon}</span>
                                        <div>
                                            <div className="rg-role-name">
                                                {role.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                                            </div>
                                            <div className="rg-role-desc">{info.desc}</div>
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <button type="submit" className="auth-submit">
                                Continue →
                            </button>
                        </form>
                    </>
                )}

                {step === 2 && (
                    <>
                        <h1 className="auth-title" style={{ marginTop: 20 }}>Create your account</h1>
                        <p className="auth-subtitle">
                            Joining <strong style={{ color: '#818cf8' }}>{orgSlug}</strong>
                        </p>

                        {error && <div className="auth-error">⚠ {error}</div>}

                        <form className="auth-form" onSubmit={handleStep2}>
                            <div className="auth-field">
                                <label htmlFor="fullname">Full name</label>
                                <input
                                    id="fullname"
                                    type="text"
                                    placeholder="Jane Smith"
                                    value={fullName}
                                    onChange={e => setFullName(e.target.value)}
                                    required autoFocus
                                    disabled={submitting}
                                />
                            </div>

                            <div className="auth-field">
                                <label htmlFor="reg-email">Work email</label>
                                <input
                                    id="reg-email"
                                    type="email"
                                    placeholder="jane@acme-corp.com"
                                    value={email}
                                    onChange={e => setEmail(e.target.value)}
                                    required autoComplete="email"
                                    disabled={submitting}
                                />
                            </div>

                            <div className="auth-field">
                                <label htmlFor="reg-pw">Password</label>
                                <div className="auth-password-wrapper">
                                    <input
                                        id="reg-pw"
                                        type={showPw ? 'text' : 'password'}
                                        placeholder="Min. 12 characters"
                                        value={password}
                                        onChange={e => setPassword(e.target.value)}
                                        required
                                        disabled={submitting}
                                    />
                                    <button type="button" className="auth-toggle-password"
                                        onClick={() => setShowPw(p => !p)}>
                                        {showPw ? '🙈' : '👁'}
                                    </button>
                                </div>
                                {/* Strength meter */}
                                {password && (
                                    <div className="rg-strength">
                                        <div className="rg-strength-bar">
                                            {[0, 1, 2, 3].map(i => (
                                                <div
                                                    key={i}
                                                    className="rg-strength-seg"
                                                    style={{ background: i < strength.score ? strength.color : 'rgba(255,255,255,0.07)' }}
                                                />
                                            ))}
                                        </div>
                                        <span style={{ color: strength.color }}>{strength.label}</span>
                                    </div>
                                )}
                                <div className="rg-pw-rules">
                                    {['12+ characters', 'Uppercase letter', 'Number', 'Symbol (e.g. !@#$)'].map(rule => (
                                        <span key={rule} className="rg-pw-rule">· {rule}</span>
                                    ))}
                                </div>
                            </div>

                            <div className="auth-field">
                                <label htmlFor="reg-cpw">Confirm password</label>
                                <input
                                    id="reg-cpw"
                                    type={showPw ? 'text' : 'password'}
                                    placeholder="Repeat password"
                                    value={confirmPw}
                                    onChange={e => setConfirmPw(e.target.value)}
                                    required
                                    disabled={submitting}
                                    style={{
                                        borderColor: confirmPw && confirmPw !== password
                                            ? 'rgba(239,68,68,0.5)' : undefined,
                                    }}
                                />
                            </div>

                            <div className="rg-actions">
                                <button
                                    type="button"
                                    className="btn btn--ghost"
                                    onClick={() => setStep(1)}
                                    disabled={submitting}
                                >
                                    ← Back
                                </button>
                                <button
                                    type="submit"
                                    className={`auth-submit rg-submit ${submitting ? 'auth-submit--loading' : ''}`}
                                    disabled={submitting}
                                >
                                    {submitting ? <><span className="auth-spinner" /> Creating account…</> : 'Create account'}
                                </button>
                            </div>
                        </form>
                    </>
                )}

                <div className="rg-signin-link">
                    Already have an account? <Link to="/login">Sign in</Link>
                </div>
            </div>
        </div>
    )
}
