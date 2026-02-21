import axios from 'axios'

const apiClient = axios.create({
    baseURL: '/api/v1',
    timeout: 120_000,
    headers: { 'Content-Type': 'application/json' },
})

export const api = {
    // Documents
    uploadDocument: async (file: File): Promise<any> => {
        const formData = new FormData()
        formData.append('file', file)
        const { data } = await apiClient.post('/documents/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        })
        return data
    },
    getDocument: async (id: string) => {
        const { data } = await apiClient.get(`/documents/${id}`)
        return data
    },
    getParsedDocument: async (id: string) => {
        const { data } = await apiClient.get(`/documents/${id}/parsed`)
        return data
    },

    // Reconciliation
    createSession: async (payload: {
        po_document_id: string
        grn_document_id: string
        invoice_document_id: string
    }) => {
        const { data } = await apiClient.post('/reconciliation/sessions', payload)
        return data
    },
    runReconciliation: async (sessionId: string) => {
        const { data } = await apiClient.post(`/reconciliation/sessions/${sessionId}/run`)
        return data
    },
    getSessionStatus: async (sessionId: string) => {
        const { data } = await apiClient.get(`/reconciliation/sessions/${sessionId}/status`)
        return data
    },
    getSessionResult: async (sessionId: string) => {
        const { data } = await apiClient.get(`/reconciliation/sessions/${sessionId}/result`)
        return data
    },
    listSessions: async (limit = 20, offset = 0) => {
        const { data } = await apiClient.get('/reconciliation/sessions', { params: { limit, offset } })
        return data
    },

    // Analytics
    getMetrics: async () => {
        const { data } = await apiClient.get('/analytics/metrics')
        return data
    },
    getHealth: async () => {
        const { data } = await apiClient.get('/analytics/health')
        return data
    },
}

export const createWebSocket = (sessionId: string, onMessage: (data: any) => void): WebSocket => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.hostname
    const port = import.meta.env.DEV ? '8000' : window.location.port
    const ws = new WebSocket(`${protocol}://${host}:${port}/ws/reconciliation/${sessionId}`)
    ws.onmessage = (e) => {
        try { onMessage(JSON.parse(e.data)) } catch { /* ignore */ }
    }
    return ws
}
