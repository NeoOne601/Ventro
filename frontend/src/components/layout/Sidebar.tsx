import { NavLink } from 'react-router-dom'
import {
    LayoutDashboard, Upload, FileSearch, BarChart3,
    Layers, ShieldCheck, Zap, LogOut, ChevronDown
} from 'lucide-react'
import { useState } from 'react'
import { useAuth, ROLE_LABELS, ROLE_COLORS } from '../../contexts/AuthContext'
import './Sidebar.css'

const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', minRole: null },
    { to: '/upload', icon: Upload, label: 'Upload Documents', minRole: 'ap_analyst' },
    { to: '/sessions', icon: FileSearch, label: 'Sessions', minRole: 'ap_analyst' },
    { to: '/analytics', icon: BarChart3, label: 'Analytics', minRole: 'finance_director' },
]

const ROLE_HIERARCHY = [
    'external_auditor', 'ap_analyst', 'ap_manager',
    'finance_director', 'admin', 'developer', 'master'
]

export default function Sidebar() {
    const { user, logout, hasRole } = useAuth()
    const [showUserMenu, setShowUserMenu] = useState(false)

    const visibleNav = navItems.filter(item =>
        !item.minRole || (user && ROLE_HIERARCHY.indexOf(user.role) >= ROLE_HIERARCHY.indexOf(item.minRole as any))
    )

    return (
        <aside className="sidebar">
            {/* Logo */}
            <div className="sidebar-logo">
                <div className="logo-icon">
                    <ShieldCheck size={22} strokeWidth={1.5} />
                </div>
                <div>
                    <div className="logo-name">Ventro</div>
                    <div className="logo-tagline">AI Audit Intelligence</div>
                </div>
            </div>

            {/* Nav */}
            <nav className="sidebar-nav">
                <div className="nav-section-label">Navigation</div>
                {visibleNav.map(({ to, icon: Icon, label }) => (
                    <NavLink
                        key={to}
                        to={to}
                        className={({ isActive }) =>
                            `sidebar-link ${isActive ? 'sidebar-link--active' : ''}`
                        }
                    >
                        <Icon size={18} strokeWidth={1.5} />
                        <span>{label}</span>
                    </NavLink>
                ))}
            </nav>

            {/* Feature Tags */}
            <div className="sidebar-features">
                <div className="feature-tag"><Layers size={12} />LangGraph Agents</div>
                <div className="feature-tag"><Zap size={12} />SAMR Protection</div>
                <div className="feature-tag"><ShieldCheck size={12} />Visual Grounding</div>
            </div>

            {/* User badge + logout */}
            {user && (
                <div className="sidebar-user">
                    <button
                        className="sidebar-user-btn"
                        onClick={() => setShowUserMenu(m => !m)}
                    >
                        <div className="sidebar-user-avatar">
                            {user.fullName.charAt(0).toUpperCase() || user.email.charAt(0).toUpperCase()}
                        </div>
                        <div className="sidebar-user-info">
                            <div className="sidebar-user-name">
                                {user.fullName || user.email}
                            </div>
                            <div
                                className="sidebar-user-role"
                                style={{ color: ROLE_COLORS[user.role] }}
                            >
                                {ROLE_LABELS[user.role]}
                            </div>
                        </div>
                        <ChevronDown
                            size={14}
                            style={{
                                transform: showUserMenu ? 'rotate(180deg)' : 'none',
                                transition: 'transform 0.2s',
                                opacity: 0.5,
                            }}
                        />
                    </button>

                    {showUserMenu && (
                        <div className="sidebar-user-menu">
                            <button
                                className="sidebar-user-menu-item"
                                onClick={() => { setShowUserMenu(false); logout() }}
                            >
                                <LogOut size={14} />
                                Sign out
                            </button>
                            <button
                                className="sidebar-user-menu-item sidebar-user-menu-item--danger"
                                onClick={() => { setShowUserMenu(false); logout(true) }}
                            >
                                <LogOut size={14} />
                                Sign out all devices
                            </button>
                        </div>
                    )}
                </div>
            )}
        </aside>
    )
}
