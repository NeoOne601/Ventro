/**
 * Ventro API Client — Axios with full auth integration
 *
 * Features:
 *   - Bearer token auto-injected on every request from AuthContext memory store
 *   - Transparent silent token refresh on 401 (single queued retry, no thundering herd)
 *   - Request deduplication: concurrent 401s share one refresh, then all retry
 *   - RFC 7807 Problem Detail error normalisation
 *   - Multipart upload helper for documents
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

// ── Token store (in-memory, set by AuthContext on login/refresh) ─────────────

let _accessToken: string | null = null
let _refreshToken: string | null = null
let _onUnauthorized: (() => void) | null = null   // callback to log the user out

export function setAuthTokens(access: string, refresh: string) {
    _accessToken = access
    _refreshToken = refresh
}

export function clearAuthTokens() {
    _accessToken = null
    _refreshToken = null
}

export function setUnauthorizedHandler(handler: () => void) {
    _onUnauthorized = handler
}

// ── Axios instance ────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const apiClient = axios.create({
    baseURL: `${API_BASE}/api/v1`,
    timeout: 120_000,
    headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor: inject Bearer token ──────────────────────────────────

apiClient.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
        if (_accessToken && !config.headers['Authorization']) {
            config.headers['Authorization'] = `Bearer ${_accessToken}`
        }
        return config
    },
    err => Promise.reject(err),
)

// ── 401 refresh machinery ─────────────────────────────────────────────────────

// All concurrent 401 failures queue here while one refresh is in flight
let _refreshing = false
let _waiters: Array<(token: string | null) => void> = []

function _waitForRefresh(): Promise<string | null> {
    return new Promise(resolve => _waiters.push(resolve))
}

function _resolveWaiters(token: string | null) {
    _waiters.forEach(fn => fn(token))
    _waiters = []
}

async function _doRefresh(): Promise<string | null> {
    const stored = _refreshToken ?? localStorage.getItem('ventro_refresh_token')
    if (!stored) return null
    try {
        const res = await axios.post(`${API_BASE}/api/v1/auth/refresh`, {
            refresh_token: stored,
        })
        const { access_token, refresh_token } = res.data
        setAuthTokens(access_token, refresh_token)
        localStorage.setItem('ventro_refresh_token', refresh_token)
        return access_token
    } catch {
        clearAuthTokens()
        localStorage.removeItem('ventro_refresh_token')
        return null
    }
}

// ── Response interceptor: handle 401 with transparent refresh ─────────────────

apiClient.interceptors.response.use(
    res => res,
    async (error: AxiosError) => {
        const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean }

        if (error.response?.status === 401 && !original._retried) {
            original._retried = true

            if (_refreshing) {
                // Another request is already refreshing — wait for it
                const token = await _waitForRefresh()
                if (!token) {
                    _onUnauthorized?.()
                    return Promise.reject(error)
                }
                original.headers['Authorization'] = `Bearer ${token}`
                return apiClient(original)
            }

            _refreshing = true
            const newToken = await _doRefresh()
            _refreshing = false
            _resolveWaiters(newToken)

            if (!newToken) {
                _onUnauthorized?.()
                return Promise.reject(error)
            }

            original.headers['Authorization'] = `Bearer ${newToken}`
            return apiClient(original)
        }

        // Normalise RFC 7807 problem detail errors
        const detail = (error.response?.data as any)?.detail
        if (detail && typeof detail === 'string') {
            error.message = detail
        }

        return Promise.reject(error)
    },
)

// ── Auth API ──────────────────────────────────────────────────────────────────

export const authApi = {
    login: async (email: string, password: string, orgSlug: string) => {
        const form = new URLSearchParams({
            username: email, password, client_id: orgSlug,
        })
        const { data } = await axios.post(`${API_BASE}/api/v1/auth/login`, form, {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })
        return data
    },

    register: async (payload: {
        email: string
        full_name: string
        password: string
        org_slug: string
    }) => {
        const { data } = await axios.post(`${API_BASE}/api/v1/auth/register`, payload)
        return data
    },

    refresh: async (refreshToken: string) => {
        const { data } = await axios.post(`${API_BASE}/api/v1/auth/refresh`, {
            refresh_token: refreshToken,
        })
        return data
    },

    me: async () => {
        const { data } = await apiClient.get('/auth/me')
        return data
    },

    logout: async (refreshToken: string) => {
        await apiClient.post('/auth/logout', { refresh_token: refreshToken })
        clearAuthTokens()
    },

    logoutAll: async () => {
        await apiClient.post('/auth/logout-all')
        clearAuthTokens()
    },
}

// ── Documents API ─────────────────────────────────────────────────────────────

export const documentsApi = {
    upload: async (file: File, onProgress?: (pct: number) => void) => {
        const formData = new FormData()
        formData.append('file', file)
        const { data } = await apiClient.post('/documents/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: e => {
                if (e.total) onProgress?.(Math.round((e.loaded / e.total) * 100))
            },
        })
        return data
    },
    get: async (id: string) => (await apiClient.get(`/documents/${id}`)).data,
    parsed: async (id: string) => (await apiClient.get(`/documents/${id}/parsed`)).data,
}

// ── Reconciliation API ────────────────────────────────────────────────────────

export const reconciliationApi = {
    createSession: async (payload: {
        po_document_id: string
        grn_document_id: string
        invoice_document_id: string
    }) => (await apiClient.post('/reconciliation/sessions', payload)).data,

    run: async (id: string) => (await apiClient.post(`/reconciliation/sessions/${id}/run`)).data,
    status: async (id: string) => (await apiClient.get(`/reconciliation/sessions/${id}/status`)).data,
    result: async (id: string) => (await apiClient.get(`/reconciliation/sessions/${id}/result`)).data,
    list: async (limit = 20, offset = 0) =>
        (await apiClient.get('/reconciliation/sessions', { params: { limit, offset } })).data,
}

// ── Analytics API ─────────────────────────────────────────────────────────────

export const analyticsApi = {
    metrics: async () => (await apiClient.get('/analytics/metrics')).data,
    health: async () => (await apiClient.get('/analytics/health')).data,
}

// ── WebSocket factory ─────────────────────────────────────────────────────────

export const createWebSocket = (
    sessionId: string,
    onMessage: (data: any) => void,
    onDone?: () => void,
    onError?: (err: string) => void,
): WebSocket => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.hostname
    const port = import.meta.env.DEV ? '8000' : window.location.port
    const ws = new WebSocket(`${protocol}://${host}:${port}/ws/reconciliation/${sessionId}`)

    ws.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data)
            if (data.event === 'ping') return
            if (data.event === 'done') { onDone?.(); return }
            if (data.event === 'error') { onError?.(data.data?.error ?? 'Pipeline error'); return }
            onMessage(data)
        } catch { /* ignore malformed messages */ }
    }
    ws.onerror = () => onError?.('WebSocket connection error')
    return ws
}

// Backward-compat default export (existing pages use `api.xxx`)
export const api = {
    uploadDocument: documentsApi.upload,
    getDocument: documentsApi.get,
    getParsedDocument: documentsApi.parsed,
    createSession: reconciliationApi.createSession,
    runReconciliation: reconciliationApi.run,
    getSessionStatus: reconciliationApi.status,
    getSessionResult: reconciliationApi.result,
    listSessions: reconciliationApi.list,
    getMetrics: analyticsApi.metrics,
    getHealth: analyticsApi.health,
}

export default apiClient
