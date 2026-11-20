import {
  Bell,
  ChevronRight,
  FileCheck2,
  FileClock,
  FileText,
  Home,
  Library,
  Menu,
  Moon,
  Settings,
  Sparkles,
  Sun,
  X,
  LifeBuoy,
} from 'lucide-react';

import {
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from 'react-router-dom';

import { useState, useEffect } from 'react';
import { BrandLogo } from '@/components/BrandLogo';
import { useAuth } from '@/contexts/AuthContext';

const primaryLinks = [
  { label: 'Dashboard', path: '/', icon: Home },
  { label: 'Verify Document', path: '/verify', icon: FileCheck2 },
  { label: 'Analysis History', path: '/history', icon: FileClock },
  { label: 'Research Library', path: '/library', icon: Library },
  { label: 'Saved Reports', path: '/reports', icon: FileText },
  { label: 'Settings', path: '/settings', icon: Settings },
];

const topLinks = [
  { label: 'Home', path: '/' },
  { label: 'Verify', path: '/verify' },
  { label: 'Library', path: '/library' },
  { label: 'Reports', path: '/reports' },
];

export function DashboardLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const [isDark, setIsDark] = useState(() => {
    const stored = localStorage.getItem('theme');

    return stored
      ? stored === 'dark'
      : window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  const { user, profile, signOut } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const currentLabel =
    primaryLinks.find((link) => link.path === location.pathname)?.label ??
    (location.pathname.startsWith('/workspace')
      ? 'Analysis Workspace'
      : 'Dashboard');

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
    document.documentElement.classList.toggle('light', !isDark);

    localStorage.setItem('theme', isDark ? 'dark' : 'light');

    window.dispatchEvent(
      new CustomEvent('veritas-theme-change', {
        detail: { isDark },
      })
    );
  }, [isDark]);

  const toggleTheme = () => {
    setIsDark((previous) => !previous);
  };

  const closeMobile = () => setMobileOpen(false);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-top">
          <BrandLogo />

          <button
            className="close-menu"
            onClick={closeMobile}
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        </div>

        <nav className="side-nav" aria-label="Main navigation">
          <div className="nav-section-label">Workspace</div>

          {primaryLinks.map(({ label, path, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/'}
              onClick={closeMobile}
              className={({ isActive }) =>
                `side-link ${isActive ? 'active' : ''}`
              }
            >
              <Icon size={18} strokeWidth={1.8} />

              <span>{label}</span>

              {label === 'Dashboard' && (
                <Sparkles className="link-spark" size={12} />
              )}
            </NavLink>
          ))}

          <div className="nav-section-label support-label">
            Support
          </div>

          <NavLink
            to="/help"
            onClick={closeMobile}
            className={({ isActive }) =>
              `side-link side-button ${isActive ? 'active' : ''}`
            }
          >
            <LifeBuoy size={18} strokeWidth={1.8} />
            <span>Help Center</span>
          </NavLink>
        </nav>

        {/* Team Vertex footer removed */}
      </aside>

      {mobileOpen && (
        <button
          className="mobile-backdrop"
          onClick={closeMobile}
          aria-label="Close navigation"
        />
      )}

      <main className="main-area">
        <header className="topbar">
          <button
            className="menu-trigger"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu size={21} />
          </button>

          <div className="breadcrumb">
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{currentLabel}</strong>
          </div>

          <nav className="top-nav">
            {topLinks.map((link) => (
              <NavLink
                key={link.path}
                to={link.path}
                end={link.path === '/'}
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="top-actions">
            <div className="notification-wrap">
              <button
                className={`icon-button ${
                  notificationsOpen ? 'selected' : ''
                }`}
                onClick={() => setNotificationsOpen(!notificationsOpen)}
                aria-label="Notifications"
              >
                <Bell size={18} />
                <span className="notification-dot" />
              </button>

              {notificationsOpen && (
                <div className="notification-popover">
                  <strong>Notifications</strong>
                  <p>Your latest workspace updates will appear here.</p>
                  <button
                    onClick={() => {
                      setNotificationsOpen(false);
                      navigate('/workspace');
                    }}
                  >
                    Open workspace
                  </button>
                </div>
              )}
            </div>

            <button
              className="icon-button"
              aria-label="Toggle theme"
              onClick={toggleTheme}
              title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <div className="profile-wrap">
              <button
                className="profile-button"
                onClick={() => setProfileOpen(!profileOpen)}
                aria-label="Open profile"
              >
                {(profile?.full_name || user?.email || 'V')
                  .slice(0, 1)
                  .toUpperCase()}
              </button>

              {profileOpen && (
                <div className="profile-popover">
                  <strong>
                    {profile?.full_name || 'Veritas researcher'}
                  </strong>

                  <span>{user?.email}</span>

                  <button onClick={() => void signOut()}>
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="page-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}