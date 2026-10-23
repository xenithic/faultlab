import React from 'react';
import { RefreshCw, AlertCircle } from 'lucide-react';

export default function Topbar({
  title,
  subtitle,
  onRefresh,
  isRefreshing,
  lastUpdated,
  error,
}) {
  return (
    <header className="topbar">
      <div className="page-title">
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>

      <div className="topbar-actions">
        {error && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              color: '#fb7185',
              fontSize: '0.86rem',
              background: 'rgba(244, 63, 94, 0.1)',
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid rgba(244, 63, 94, 0.25)',
            }}
          >
            <AlertCircle size={17} />
            <span>API Error</span>
          </div>
        )}

        {lastUpdated && (
          <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            Updated: {lastUpdated.toLocaleTimeString()}
          </span>
        )}

        <button
          className="btn btn-secondary btn-sm"
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Refresh real-time platform data"
          style={{ gap: 8 }}
        >
          <RefreshCw size={15} className={isRefreshing ? 'loading-spinner' : ''} />
          <span>Refresh</span>
        </button>
      </div>
    </header>
  );
}
