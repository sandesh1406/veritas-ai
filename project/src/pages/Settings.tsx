import { useEffect, useState, type ReactNode } from 'react';
import {
  UserRound,
  Bell,
  LockKeyhole,
  Palette,
  Check,
} from 'lucide-react';

import { PageIntro } from '@/components/PageIntro';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api';

type SettingsTab = 'profile' | 'notifications' | 'security' | 'appearance';

export function Settings() {
  const { user, profile, refreshProfile } = useAuth();

  const [activeTab, setActiveTab] = useState<SettingsTab>('profile');
  const [fullName, setFullName] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [saved, setSaved] = useState(false);
  const [emailUpdates, setEmailUpdates] = useState(true);
  const [reviewAlerts, setReviewAlerts] = useState(true);
  const [message, setMessage] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const [isDark, setIsDark] = useState(() => {
    const storedTheme = localStorage.getItem('theme');

    return storedTheme
      ? storedTheme === 'dark'
      : document.documentElement.classList.contains('dark');
  });

  // Keep profile fields synchronized with the authenticated profile.
  useEffect(() => {
    setFullName(profile?.full_name ?? '');
    setAvatarUrl(profile?.avatar_url ?? '');
  }, [profile]);

  // Keep the Appearance tab synchronized with the global theme toggle.
  useEffect(() => {
    const updateTheme = (event: Event) => {
      const customEvent = event as CustomEvent<{ isDark: boolean }>;
      setIsDark(customEvent.detail.isDark);
    };

    const syncTheme = () => {
      setIsDark(document.documentElement.classList.contains('dark'));
    };

    window.addEventListener('veritas-theme-change', updateTheme);
    window.addEventListener('storage', syncTheme);

    return () => {
      window.removeEventListener('veritas-theme-change', updateTheme);
      window.removeEventListener('storage', syncTheme);
    };
  }, []);

  const save = async () => {
    if (!user) return;

    setMessage('');
    setSaved(false);
    setIsSaving(true);

    try {
      await api.request('/profile', {
        method: 'PUT',
        body: JSON.stringify({
          full_name: fullName,
          avatar_url: avatarUrl || null,
        }),
      });

      await refreshProfile();
      setSaved(true);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'We could not save your profile.'
      );
    } finally {
      setIsSaving(false);
    }
  };

  const toggleTheme = () => {
    const newIsDark = !isDark;

    setIsDark(newIsDark);

    document.documentElement.classList.toggle('dark', newIsDark);
    document.documentElement.classList.toggle('light', !newIsDark);

    localStorage.setItem('theme', newIsDark ? 'dark' : 'light');

    window.dispatchEvent(
      new CustomEvent('veritas-theme-change', {
        detail: { isDark: newIsDark },
      })
    );
  };

  const tabs: {
    id: SettingsTab;
    label: string;
    icon: ReactNode;
  }[] = [
    { id: 'profile', label: 'Profile', icon: <UserRound size={16} /> },
    { id: 'notifications', label: 'Notifications', icon: <Bell size={16} /> },
    { id: 'security', label: 'Security', icon: <LockKeyhole size={16} /> },
    { id: 'appearance', label: 'Appearance', icon: <Palette size={16} /> },
  ];

  return (
    <div className="inner-page settings-page">
      <PageIntro
        eyebrow="Workspace / Preferences"
        title="Settings"
        description="Tune your profile and the way your team receives evidence updates."
      />

      <div className="settings-layout">
        <aside className="settings-nav">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={`settings-nav-item ${
                activeTab === tab.id ? 'active' : ''
              }`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </aside>

        <div className="settings-content">
          {activeTab === 'profile' && (
            <section className="panel settings-card">
              <div className="settings-heading">
                <div>
                  <span className="eyebrow">Personal details</span>
                  <h2>Profile information</h2>
                </div>

                <div className="profile-large">
                  {fullName.slice(0, 1).toUpperCase() || 'V'}
                </div>
              </div>

              <div className="form-grid">
                <label>
                  Full name
                  <input
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="Your name"
                  />
                </label>

                <label>
                  Account email
                  <input
                    value={profile?.email || user?.email || ''}
                    readOnly
                    type="email"
                  />
                </label>

                <label className="full-field">
                  Avatar URL <span className="field-hint">Optional</span>
                  <input
                    value={avatarUrl}
                    onChange={(event) => setAvatarUrl(event.target.value)}
                    placeholder="https://..."
                  />
                </label>
              </div>
            </section>
          )}

          {activeTab === 'notifications' && (
            <section className="panel settings-card">
              <div className="settings-heading">
                <div>
                  <span className="eyebrow">Stay informed</span>
                  <h2>Notification preferences</h2>
                </div>
              </div>

              <label className="toggle-row">
                <span>
                  <strong>Analysis complete</strong>
                  <small>
                    Get notified when a document is ready to review.
                  </small>
                </span>

                <input
                  type="checkbox"
                  checked={emailUpdates}
                  onChange={(event) =>
                    setEmailUpdates(event.target.checked)
                  }
                />
                <i />
              </label>

              <label className="toggle-row">
                <span>
                  <strong>Claims needing review</strong>
                  <small>
                    Receive alerts when evidence needs your attention.
                  </small>
                </span>

                <input
                  type="checkbox"
                  checked={reviewAlerts}
                  onChange={(event) =>
                    setReviewAlerts(event.target.checked)
                  }
                />
                <i />
              </label>
            </section>
          )}

          {activeTab === 'security' && (
            <section className="panel settings-card">
              <div className="settings-heading">
                <div>
                  <span className="eyebrow">Account security</span>
                  <h2>Security settings</h2>
                </div>
              </div>

              <p className="settings-info">
                Password and authentication are managed by Supabase Auth.

                <a
                  href="#"
                  onClick={(event) => {
                    event.preventDefault();
                    alert(
                      'Password management is handled by your authentication provider.'
                    );
                  }}
                >
                  Manage password and 2FA in Supabase Dashboard
                </a>
              </p>
            </section>
          )}

          {activeTab === 'appearance' && (
            <section className="panel settings-card">
              <div className="settings-heading">
                <div>
                  <span className="eyebrow">Visual preferences</span>
                  <h2>Appearance</h2>
                </div>
              </div>

              <label className="toggle-row">
                <span>
                  <strong>Dark mode</strong>
                  <small>
                    Switch between light and dark themes.
                  </small>
                </span>

                <input
                  type="checkbox"
                  checked={isDark}
                  onChange={toggleTheme}
                />
                <i />
              </label>
            </section>
          )}

          {message && (
            <div className="form-message error-message">
              {message}
            </div>
          )}

          <div className="settings-actions">
            <span className={saved ? 'save-confirmed' : ''}>
              {saved && <Check size={15} />}
              {saved
                ? 'Changes saved'
                : 'Changes are saved to your profile'}
            </span>

            <button
              className="primary-button"
              onClick={() => void save()}
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}