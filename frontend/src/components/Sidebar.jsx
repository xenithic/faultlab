import React from 'react';
import {
  LayoutDashboard,
  Server,
  Zap,
  Activity,
  Flame,
  Radio,
} from 'lucide-react';

export default function Sidebar({
  currentView,
  setCurrentView,
  platformHealth,
  runningExperimentsCount = 0,
}) {
  const navItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'targets', label: 'Target Environments', icon: Server },
    {
      id: 'experiments',
      label: 'Experiments',
      icon: Zap,
      badge: runningExperimentsCount > 0 ? `${runningExperimentsCount} Running` : null,
    },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-icon">
          <Flame size={22} />
        </div>
        <div className="logo-text">
          <h1>FaultLab</h1>
          <p>Resilience Testing</p>
        </div>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              className={`nav-item ${isActive ? 'active' : ''}`}
              onClick={() => setCurrentView(item.id)}
            >
              <Icon size={20} />
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.badge && (
                <span
                  className="badge badge-running"
                  style={{ fontSize: '0.74rem', padding: '3px 8px' }}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div className="system-status-indicator">
          <span
            className={`status-dot ${
              platformHealth?.status === 'healthy'
                ? 'healthy'
                : platformHealth === null
                ? 'running'
                : 'error'
            }`}
          />
          <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            {platformHealth?.status === 'healthy'
              ? 'Platform Online'
              : platformHealth === null
              ? 'Connecting...'
              : 'Platform Offline'}
          </span>
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
          Flask Platform Backend {platformHealth?.version ? `v${platformHealth.version}` : ''}
        </div>
      </div>
    </aside>
  );
}
