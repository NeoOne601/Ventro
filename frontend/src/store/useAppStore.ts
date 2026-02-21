import { create } from 'zustand'

interface UploadedDoc {
    id: string
    filename: string
    document_type: string
    classification_confidence: number
}

interface AppState {
    // Uploaded documents
    poDoc: UploadedDoc | null
    grnDoc: UploadedDoc | null
    invoiceDoc: UploadedDoc | null
    setPoDoc: (doc: UploadedDoc | null) => void
    setGrnDoc: (doc: UploadedDoc | null) => void
    setInvoiceDoc: (doc: UploadedDoc | null) => void

    // Active session
    activeSessionId: string | null
    setActiveSessionId: (id: string | null) => void

    // Progress events
    progressEvents: any[]
    addProgressEvent: (event: any) => void
    clearProgressEvents: () => void

    // PDF viewer state
    pdfViewerDoc: { docId: string; page: number; bbox?: any } | null
    openPdfViewer: (docId: string, page: number, bbox?: any) => void
    closePdfViewer: () => void

    // SAMR alert
    samrAlertActive: boolean
    setSamrAlert: (active: boolean) => void
}

export const useAppStore = create<AppState>((set) => ({
    poDoc: null,
    grnDoc: null,
    invoiceDoc: null,
    setPoDoc: (doc) => set({ poDoc: doc }),
    setGrnDoc: (doc) => set({ grnDoc: doc }),
    setInvoiceDoc: (doc) => set({ invoiceDoc: doc }),

    activeSessionId: null,
    setActiveSessionId: (id) => set({ activeSessionId: id }),

    progressEvents: [],
    addProgressEvent: (event) =>
        set((state) => ({ progressEvents: [...state.progressEvents, event] })),
    clearProgressEvents: () => set({ progressEvents: [] }),

    pdfViewerDoc: null,
    openPdfViewer: (docId, page, bbox) =>
        set({ pdfViewerDoc: { docId, page, bbox } }),
    closePdfViewer: () => set({ pdfViewerDoc: null }),

    samrAlertActive: false,
    setSamrAlert: (active) => set({ samrAlertActive: active }),
}))
