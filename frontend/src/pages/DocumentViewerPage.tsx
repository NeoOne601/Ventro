import React, { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Printer, Download, FileText } from 'lucide-react'

export default function DocumentViewerPage() {
    const { docId, page } = useParams<{ docId: string, page: string }>()
    const [searchParams] = useSearchParams()

    const x0 = parseFloat(searchParams.get('x0') || '0')
    const y0 = parseFloat(searchParams.get('y0') || '0')
    const x1 = parseFloat(searchParams.get('x1') || '0')
    const y1 = parseFloat(searchParams.get('y1') || '0')
    const [imageUrl, setImageUrl] = useState('')
    const [imageLoaded, setImageLoaded] = useState(false)
    const [imgWidth, setImgWidth] = useState(1)
    const [imgHeight, setImgHeight] = useState(1)

    useEffect(() => {
        const url = `${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/api/v1/documents/${docId}/page/${page}`
        setImageUrl(url)
    }, [docId, page])

    const handlePrint = () => {
        window.print()
    }

    const handleDownload = async () => {
        try {
            const response = await fetch(imageUrl)
            const blob = await response.blob()
            const url = window.URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `Document_${docId}_Page_${page}.png`
            document.body.appendChild(a)
            a.click()
            window.URL.revokeObjectURL(url)
        } catch (error) {
            console.error('Download failed', error)
        }
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#0a0a1a' }}>
            <style>
                {`
                    @media print {
                        .no-print { display: none !important; }
                        body, html, #root { background: white !important; height: auto !important; overflow: visible !important; }
                        .print-container { padding: 0 !important; max-width: none !important; box-shadow: none !important; }
                    }
                `}
            </style>

            <div className="no-print" style={{ padding: '1rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#1e1e2d' }}>
                <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-primary)' }}>
                    <FileText size={20} color="var(--color-accent)" /> Document Viewer — Page {page}
                </h2>
                <div style={{ display: 'flex', gap: '1rem' }}>
                    <button onClick={handlePrint} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', background: 'var(--color-primary)', border: 'none', borderRadius: '4px', cursor: 'pointer', color: 'white' }}>
                        <Printer size={16} /> Print
                    </button>
                    <button onClick={handleDownload} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: '4px', cursor: 'pointer', color: 'var(--text-primary)' }}>
                        <Download size={16} /> Download
                    </button>
                </div>
            </div>

            <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '2rem', overflow: 'auto' }} className="print-container">
                <div style={{ position: 'relative', width: '100%', maxWidth: '900px', backgroundColor: 'white', boxShadow: '0 4px 20px rgba(0,0,0,0.5)' }}>
                    <img
                        src={imageUrl}
                        alt={`Page ${page}`}
                        style={{ width: '100%', height: 'auto', display: 'block' }}
                        crossOrigin="anonymous"
                        onLoad={(e) => {
                            const img = e.target as HTMLImageElement
                            setImgWidth(img.naturalWidth || 1)
                            setImgHeight(img.naturalHeight || 1)
                            setImageLoaded(true)
                        }}
                    />
                    {(imageLoaded && x1 > x0 && y1 > y0) && (
                        <div style={{
                            position: 'absolute',
                            left: `${x0 * 100}%`,
                            top: `${y0 * 100}%`,
                            width: `${(x1 - x0) * 100}%`,
                            height: `${(y1 - y0) * 100}%`,
                            border: '3px solid #ef4444',
                            backgroundColor: 'rgba(239,68,68,0.3)',
                            boxShadow: '0 0 15px rgba(239,68,68,0.6)',
                            pointerEvents: 'none'
                        }} />
                    )}
                </div>
            </div>
        </div>
    )
}
