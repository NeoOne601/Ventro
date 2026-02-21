import { NavLink } from 'react-router-dom'
import {
    LayoutDashboard, Upload, FileSearch, BarChart3,
    Layers, ShieldCheck, Zap
} from 'lucide-react'
import './Sidebar.css'

const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/upload', icon: Upload, label: 'Upload Documents' },
    { to: '/sessions', icon: FileSearch, label: 'Sessions' },
    { to: '/analytics', icon: BarChart3, label: 'Analytics' },
]

export default function Sidebar() {
    return (
        <aside className="sidebar">
            {/* Logo */}
            <div className="sidebar-logo">
                <div className="logo-icon">
                    <ShieldCheck size={22} strokeWidth={1.5} />
                </div>
                <div>
                    <div className="logo-name">MAS-VGFR</div>
                    <div className="logo-tagline">AI Audit Intelligence</div>
                </div>
            </div>

            {/* Nav */}
            <nav className="sidebar-nav">
                <div className="nav-section-label">Navigation</div>
                {navItems.map(({ to, icon: Icon, label }) => (
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

            {/* Footer */}
            <div className="sidebar-footer">
                <div className="version-badge">v1.0.0 Production</div>
            </div>
        </aside>
    )
}
