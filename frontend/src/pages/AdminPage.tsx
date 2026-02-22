/**
 * Admin Page — User Management + Webhook Management + Compliance
 *
 * Access: ADMIN (own org) or MASTER (all orgs)
 *
 * Sections:
 *   👥 Users — searchable table, invite modal, role/status edit drawer
 *   🔔 Webhooks — register endpoints, test, view delivery log
 *   📋 Compliance — SOC 2 evidence pack generator
 */
import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-toastify'
import { useAuth } from '../contexts/AuthContext'
import apiClient from '../services/api'
import UserTable from '../components/admin/UserTable'
import InviteUserModal from '../components/admin/InviteUserModal'
import WebhookPanel from '../components/admin/WebhookPanel'
import '../styles/admin.css'

type AdminTab = 'users' | 'webhooks' | 'compliance'

export default function AdminPage() {
    const { user } = useAuth()
    const [activeTab, setActiveTab] = useState<AdminTab>('users')
    const [showInvite, setShowInvite] = useState(false)
    const [generatingPack, setGeneratingPack] = useState(false)
    const qc = useQueryClient()

    const isMaster = user?.role === 'master'

    const handleGeneratePack = async () => {
        setGeneratingPack(true)
        try {
            const res = await apiClient.get('/admin/compliance/evidence-pack', {
                responseType: 'blob',
            })
            const url = URL.createObjectURL(res.data)
            const a = document.createElement('a')
            a.href = url
            a.download = `ventro-evidence-pack-${new Date().toISOString().slice(0, 10)}.zip`
            a.click()
            URL.revokeObjectURL(url)
            toast.success('Evidence pack downloaded ✓')
        } catch {
            toast.error('Failed to generate evidence pack')
        } finally {
            setGeneratingPack(false)
        }
    }

    const TABS: { id: AdminTab; label: string; icon: string }[] = [
        { id: 'users', label: 'User Management', icon: '👥' },
        { id: 'webhooks', label: 'Webhooks', icon: '🔔' },
        { id: 'compliance', label: 'Compliance', icon: '📋' },
    ]

    return (
        <div className="admin-page">
            {/* Page header */}
            <div className="admin-header">
                <div>
                    <h1 className="admin-title">Admin Console</h1>
                    <p className="admin-subtitle">
                        {isMaster ? '🌐 Master Admin — all organisations' : `Organisation: ${user?.organisationId?.slice(0, 8)}…`}
                    </p>
                </div>
                {activeTab === 'users' && (
                    <button
                        className="btn btn--primary admin-invite-btn"
                        onClick={() => setShowInvite(true)}
                    >
                        + Invite User
                    </button>
                )}
            </div>

            {/* Tab bar */}
            <div className="admin-tabs">
                {TABS.map(tab => (
                    <button
                        key={tab.id}
                        className={`admin-tab ${activeTab === tab.id ? 'admin-tab--active' : ''}`}
                        onClick={() => setActiveTab(tab.id)}
                    >
                        {tab.icon} {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab content */}
            <div className="admin-content">
                {activeTab === 'users' && <UserTable isMaster={isMaster} />}
                {activeTab === 'webhooks' && <WebhookPanel />}
                {activeTab === 'compliance' && (
                    <CompliancePanel
                        onGenerate={handleGeneratePack}
                        generating={generatingPack}
                    />
                )}
            </div>

            {showInvite && (
                <InviteUserModal
                    isMaster={isMaster}
                    onClose={() => setShowInvite(false)}
                    onSuccess={() => {
                        setShowInvite(false)
                        qc.invalidateQueries({ queryKey: ['admin-users'] })
                        toast.success('User invited successfully')
                    }}
                />
            )}
        </div>
    )
}

// ── Compliance Panel ──────────────────────────────────────────────────────────

function CompliancePanel({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
    return (
        <div className="compliance-panel">
            <div className="compliance-hero">
                <div className="compliance-icon">🛡️</div>
                <div>
                    <h2 className="compliance-title">SOC 2 Evidence Pack</h2>
                    <p className="compliance-desc">
                        Generate a signed ZIP containing your complete audit trail,
                        RBAC matrix, session statistics, and data retention certificate —
                        ready to hand directly to your external auditor.
                    </p>
                </div>
            </div>

            <div className="compliance-manifest">
                {[
                    { file: 'audit_log_export.csv', desc: 'Full, chronological audit log with SHA-256 chain' },
                    { file: 'rbac_matrix.json', desc: 'Role → permissions mapping for all 7 roles' },
                    { file: 'session_statistics.json', desc: 'Pipeline counts, error rates, avg. duration' },
                    { file: 'data_retention_certificate.txt', desc: 'Signed retention & encryption policy cert' },
                    { file: 'manifest.json', desc: 'SHA-256 hash of every file — tamper-evident' },
                ].map(({ file, desc }) => (
                    <div key={file} className="compliance-item">
                        <span className="compliance-file">📄 {file}</span>
                        <span className="compliance-item-desc">{desc}</span>
                    </div>
                ))}
            </div>

            <button
                className={`btn btn--primary compliance-btn ${generating ? 'compliance-btn--loading' : ''}`}
                onClick={onGenerate}
                disabled={generating}
            >
                {generating ? (
                    <><span className="auth-spinner" /> Generating…</>
                ) : (
                    '⬇ Download Evidence Pack'
                )}
            </button>

            <p className="compliance-note">
                Pack is generated on-demand from live data. Each download produces a new signed manifest.
            </p>
        </div>
    )
}
