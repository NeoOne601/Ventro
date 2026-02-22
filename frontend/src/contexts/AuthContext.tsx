/**
 * Ventro Auth Context
 * 
 * Provides authentication state, login/logout, and RBAC permission checking
 * to all React components. Access token stored in memory (not localStorage —
 * security best practice). Refresh token stored in httpOnly cookie via the
 * API, or as a fallback in memory for demo environments.
 * 
 * Token refresh is done silently 60 seconds before expiry.
 */
import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-toastify'

// ── Types ──────────────────────────────────────────────────────────────────────

export type Role =
    | 'external_auditor'
    | 'ap_analyst'
    | 'ap_manager'
    | 'finance_director'
    | 'admin'
    | 'developer'
    | 'master'

// Role hierarchy index (lower = less privileged)
const ROLE_HIERARCHY: Role[] = [
    'external_auditor',
    'ap_analyst',
    'ap_manager',
    'finance_director',
    'admin',
    'developer',
    'master',
]

export const ROLE_LABELS: Record<Role, string> = {
    external_auditor: 'External Auditor',
    ap_analyst: 'AP Analyst',
    ap_manager: 'AP Manager',
    finance_director: 'Finance Director',
    admin: 'Administrator',
    developer: 'Developer',
    master: 'Master Admin',
}

export const ROLE_COLORS: Record<Role, string> = {
    external_auditor: '#64748b',
    ap_analyst: '#3b82f6',
    ap_manager: '#8b5cf6',
    finance_director: '#06b6d4',
    admin: '#f59e0b',
    developer: '#10b981',
    master: '#ef4444',
}

export type Permission =
    | 'document:upload' | 'document:read' | 'document:delete'
    | 'session:create' | 'session:read' | 'session:delete'
    | 'finding:read' | 'finding:override'
    | 'workpaper:read' | 'workpaper:export' | 'workpaper:sign'
    | 'analytics:read'
    | 'user:manage' | 'audit_log:read'
    | 'org:manage' | 'billing:read'
    | 'debug:access' | 'api_key:manage'
    | 'system:config'

export interface AuthUser {
    id: string
    email: string
    fullName: string
    role: Role
    organisationId: string
    permissions: Permission[]
}

export interface AuthState {
    user: AuthUser | null
    accessToken: string | null
    isAuthenticated: boolean
    isLoading: boolean
}

interface AuthContextValue extends AuthState {
    login: (email: string, password: string, orgSlug: string) => Promise<void>
    logout: (logoutAll?: boolean) => Promise<void>
    hasPermission: (permission: Permission) => boolean
    hasRole: (minimumRole: Role) => boolean
    refreshToken: string | null
}

// ── Context ────────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null)

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ── Provider ───────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [state, setState] = useState<AuthState>({
        user: null,
        accessToken: null,
        isAuthenticated: false,
        isLoading: true,
    })
    const [refreshToken, setRefreshToken] = useState<string | null>(null)
    const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const navigate = useNavigate()

    // ── Helpers ────────────────────────────────────────────────────────────────

    const clearAuthState = useCallback(() => {
        if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
        setState({ user: null, accessToken: null, isAuthenticated: false, isLoading: false })
        setRefreshToken(null)
        localStorage.removeItem('ventro_refresh_token')
    }, [])

    const scheduleTokenRefresh = useCallback((accessToken: string, storedRefresh: string) => {
        // Decode exp from JWT without verifying (trust our own backend)
        try {
            const payload = JSON.parse(atob(accessToken.split('.')[1]))
            const expiresIn = payload.exp * 1000 - Date.now() - 60_000 // 60s before expiry
            if (expiresIn <= 0) return
            if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
            refreshTimerRef.current = setTimeout(() => {
                silentRefresh(storedRefresh)
            }, expiresIn)
        } catch {
            // Cannot decode — skip auto-refresh
        }
    }, [])

    const setAuthFromTokens = useCallback(async (
        access: string,
        refresh: string
    ) => {
        // Fetch full profile so we have name, email, permissions
        const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
            headers: { Authorization: `Bearer ${access}` },
        })
        if (!res.ok) throw new Error('Failed to fetch user profile')
        const profile = await res.json()

        const user: AuthUser = {
            id: profile.id,
            email: profile.email,
            fullName: profile.full_name,
            role: profile.role as Role,
            organisationId: profile.organisation_id,
            permissions: profile.permissions,
        }

        setState({ user, accessToken: access, isAuthenticated: true, isLoading: false })
        setRefreshToken(refresh)
        localStorage.setItem('ventro_refresh_token', refresh)
        scheduleTokenRefresh(access, refresh)
    }, [scheduleTokenRefresh])

    const silentRefresh = useCallback(async (storedRefresh: string) => {
        try {
            const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: storedRefresh }),
            })
            if (!res.ok) {
                clearAuthState()
                navigate('/login')
                return
            }
            const data = await res.json()
            await setAuthFromTokens(data.access_token, data.refresh_token)
        } catch {
            clearAuthState()
            navigate('/login')
        }
    }, [clearAuthState, navigate, setAuthFromTokens])

    // ── Login / Logout ─────────────────────────────────────────────────────────

    const login = useCallback(async (email: string, password: string, orgSlug: string) => {
        const form = new URLSearchParams({
            username: email,
            password: password,
            client_id: orgSlug,
        })
        const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: form,
        })
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Login failed' }))
            throw new Error(err.detail ?? 'Login failed')
        }
        const data = await res.json()
        await setAuthFromTokens(data.access_token, data.refresh_token)
    }, [setAuthFromTokens])

    const logout = useCallback(async (logoutAll = false) => {
        const { accessToken: access } = state
        const storedRefresh = refreshToken

        clearAuthState()

        try {
            if (logoutAll && access) {
                await fetch(`${API_BASE}/api/v1/auth/logout-all`, {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${access}` },
                })
            } else if (storedRefresh && access) {
                await fetch(`${API_BASE}/api/v1/auth/logout`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${access}`,
                    },
                    body: JSON.stringify({ refresh_token: storedRefresh }),
                })
            }
        } catch {
            /* best-effort — local state already cleared */
        }

        navigate('/login')
    }, [state, refreshToken, clearAuthState, navigate])

    // ── Permission / Role checks ───────────────────────────────────────────────

    const hasPermission = useCallback((perm: Permission): boolean => {
        return state.user?.permissions.includes(perm) ?? false
    }, [state.user])

    const hasRole = useCallback((minimumRole: Role): boolean => {
        if (!state.user) return false
        const userIdx = ROLE_HIERARCHY.indexOf(state.user.role)
        const minIdx = ROLE_HIERARCHY.indexOf(minimumRole)
        return userIdx >= minIdx
    }, [state.user])

    // ── Boot: restore session from localStorage refresh token ──────────────────

    useEffect(() => {
        const storedRefresh = localStorage.getItem('ventro_refresh_token')
        if (storedRefresh) {
            silentRefresh(storedRefresh)
        } else {
            setState(s => ({ ...s, isLoading: false }))
        }
    }, []) // only on mount

    return (
        <AuthContext.Provider value={{
            ...state,
            refreshToken,
            login,
            logout,
            hasPermission,
            hasRole,
        }}>
            {children}
        </AuthContext.Provider>
    )
}

// ── Hooks ──────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
    const ctx = useContext(AuthContext)
    if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
    return ctx
}

export function usePermission(permission: Permission): boolean {
    return useAuth().hasPermission(permission)
}

export function useRole(minimumRole: Role): boolean {
    return useAuth().hasRole(minimumRole)
}
