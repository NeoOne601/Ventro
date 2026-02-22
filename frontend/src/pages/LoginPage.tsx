/**
 * Login Page — Ventro Authentication
 * Premium glassmorphism design with org slug, animated state, and error handling.
 */
import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import '../styles/auth.css'

export default function LoginPage() {
    const { login, isAuthenticated, isLoading } = useAuth()
    const navigate = useNavigate()
    const location = useLocation()
    const from = (location.state as { from?: Location })?.from?.pathname ?? '/dashboard'

    const [form, setForm] = useState({ email: '', password: '', orgSlug: 'dev' })
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState('')
    const [showPassword, setShowPassword] = useState(false)

    useEffect(() => {
        if (isAuthenticated && !isLoading) navigate(from, { replace: true })
    }, [isAuthenticated, isLoading, navigate, from])

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        setSubmitting(true)
        try {
            await login(form.email.trim(), form.password, form.orgSlug.trim() || 'dev')
            navigate(from, { replace: true })
        } catch (err: any) {
            setError(err.message ?? 'Login failed. Please try again.')
        } finally {
            setSubmitting(false)
        }
    }

    if (isLoading) return null

    return (
        <div className="auth-page">
            {/* Animated gradient background */}
            <div className="auth-bg">
                <div className="auth-bg-blob auth-bg-blob-1" />
                <div className="auth-bg-blob auth-bg-blob-2" />
                <div className="auth-bg-blob auth-bg-blob-3" />
            </div>

            <div className="auth-card">
                {/* Logo */}
                <div className="auth-logo">
                    <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                        <rect width="40" height="40" rx="12" fill="url(#logoGrad)" />
                        <path d="M10 20L18 28L30 12" stroke="white" strokeWidth="3"
                            strokeLinecap="round" strokeLinejoin="round" />
                        <defs>
                            <linearGradient id="logoGrad" x1="0" y1="0" x2="40" y2="40">
                                <stop stopColor="#6366f1" />
                                <stop offset="1" stopColor="#8b5cf6" />
                            </linearGradient>
                        </defs>
                    </svg>
                    <span className="auth-logo-text">Ventro</span>
                </div>

                <h1 className="auth-title">Welcome back</h1>
                <p className="auth-subtitle">Sign in to your reconciliation workspace</p>

                {error && (
                    <div className="auth-error">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="12" y1="8" x2="12" y2="12" />
                            <line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                        {error}
                    </div>
                )}

                <form className="auth-form" onSubmit={handleSubmit}>
                    <div className="auth-field">
                        <label htmlFor="email">Email address</label>
                        <input
                            id="email"
                            type="email"
                            autoComplete="email"
                            placeholder="name@company.com"
                            value={form.email}
                            onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                            required
                            disabled={submitting}
                        />
                    </div>

                    <div className="auth-field">
                        <label htmlFor="password">Password</label>
                        <div className="auth-password-wrapper">
                            <input
                                id="password"
                                type={showPassword ? 'text' : 'password'}
                                autoComplete="current-password"
                                placeholder="Min. 12 characters"
                                value={form.password}
                                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                                required
                                disabled={submitting}
                            />
                            <button
                                type="button"
                                className="auth-toggle-password"
                                onClick={() => setShowPassword(p => !p)}
                                aria-label={showPassword ? 'Hide password' : 'Show password'}
                            >
                                {showPassword ? '🙈' : '👁'}
                            </button>
                        </div>
                    </div>

                    <div className="auth-field">
                        <label htmlFor="orgSlug">
                            Organisation
                            <span className="auth-field-hint"> (URL slug)</span>
                        </label>
                        <input
                            id="orgSlug"
                            type="text"
                            autoComplete="organization"
                            placeholder="e.g. acme-corp"
                            value={form.orgSlug}
                            onChange={e => setForm(f => ({ ...f, orgSlug: e.target.value }))}
                            required
                            disabled={submitting}
                        />
                    </div>

                    <button
                        type="submit"
                        className={`auth-submit ${submitting ? 'auth-submit--loading' : ''}`}
                        disabled={submitting}
                    >
                        {submitting ? (
                            <>
                                <span className="auth-spinner" />
                                Signing in…
                            </>
                        ) : 'Sign in'}
                    </button>
                </form>

                <div className="auth-divider">
                    <span>Role-based access control enforced on every request</span>
                </div>

                <div className="auth-role-badges">
                    {['External Auditor', 'AP Analyst', 'AP Manager', 'Finance Director',
                        'Admin', 'Developer', 'Master'].map(role => (
                            <span key={role} className="auth-role-badge">{role}</span>
                        ))}
                </div>
            </div>
        </div>
    )
}
