import React from 'react';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  PlayCircle,
  AlertTriangle,
  Server,
  ArrowRight,
  ShieldCheck,
  Slash,
  BarChart3,
  Check,
} from 'lucide-react';
import OutcomeChart from '../components/Charts/OutcomeChart';
import RecoveryChart from '../components/Charts/RecoveryChart';

export default function Overview({
  experiments = [],
  targets = [],
  loading,
  error,
  onSelectExperiment,
  onNavigate,
}) {
  if (loading && experiments.length === 0 && targets.length === 0) {
    return (
      <div className="empty-state" style={{ padding: '80px 24px' }}>
        <div className="loading-spinner" style={{ width: 40, height: 40 }} />
        <h3>Connecting to FaultLab Platform...</h3>
        <p style={{ fontSize: '0.95rem' }}>Retrieving target status and experiment history from platform backend.</p>
      </div>
    );
  }

  if (error && experiments.length === 0 && targets.length === 0) {
    return (
      <div className="alert alert-danger" style={{ maxWidth: 840, margin: '32px auto' }}>
        <AlertTriangle size={28} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <h4 style={{ fontWeight: 700, fontSize: '1.05rem', marginBottom: 6 }}>Platform Backend Unavailable</h4>
          <p>{error}</p>
          <p style={{ marginTop: 10, fontSize: '0.85rem', color: '#cbd5e1' }}>
            Verify that the FaultLab platform API container is running on port 5050 and PostgreSQL is healthy.
          </p>
        </div>
      </div>
    );
  }

  // Derive genuine counts from backend records
  const totalExperiments = experiments.length;
  const runningCount = experiments.filter((e) => e.status === 'running').length;
  const completedCount = experiments.filter((e) => e.status === 'completed').length;
  const failedCount = experiments.filter((e) => e.status === 'failed').length;
  const pendingCount = experiments.filter((e) => e.status === 'pending').length;
  const cancelledCount = experiments.filter((e) => e.status === 'cancelled').length;

  // Calculate verified recovery success rate
  const finishedRuns = completedCount + failedCount;
  const verifiedRecoveryRate = finishedRuns > 0
    ? Math.round((completedCount / finishedRuns) * 100)
    : null;

  // Target validation status breakdown
  const totalTargets = targets.length;
  const validTargets = targets.filter((t) => t.validation_status === 'valid').length;

  // Recent experiments (up to 5)
  const recentExperiments = experiments.slice(0, 5);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      {/* Target & Platform Summary Banner if targets need validation */}
      {totalTargets > 0 && validTargets === 0 && (
        <div className="alert alert-warning" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <AlertTriangle size={24} style={{ flexShrink: 0 }} />
          <div style={{ flex: 1, fontSize: '0.92rem' }}>
            <strong>Action Required:</strong> Target environments are registered ({totalTargets}), but none are currently validated.
            Run live Docker validation on the Targets page before initiating experiments.
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => onNavigate('targets')}>
            Go to Targets
          </button>
        </div>
      )}

      {/* Primary KPI Header (3 Structured Cards) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20 }}>
        {/* Total Runs */}
        <div className="metric-card primary">
          <div className="metric-label">
            <span>Total Experiments</span>
            <Activity size={18} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <div className="metric-value">{totalExperiments}</div>
          <div className="metric-sub">
            Recorded resilience test runs in database
          </div>
        </div>

        {/* Active Injections */}
        <div className={`metric-card ${runningCount > 0 ? 'purple' : ''}`}>
          <div className="metric-label">
            <span>Active Execution</span>
            <PlayCircle size={18} style={{ color: runningCount > 0 ? 'var(--accent-purple)' : 'var(--text-muted)' }} />
          </div>
          <div className="metric-value" style={{ color: runningCount > 0 ? '#c084fc' : 'var(--text-primary)' }}>
            {runningCount > 0 ? `${runningCount} Running` : 'Idle'}
          </div>
          <div className="metric-sub">
            {runningCount > 0 ? 'Fault injection lifecycle currently in progress' : 'No active fault injection in progress'}
          </div>
        </div>

        {/* Verified Recovery Success Rate */}
        <div className="metric-card success">
          <div className="metric-label">
            <span>Verified Recovery Rate</span>
            <ShieldCheck size={18} style={{ color: 'var(--accent-emerald)' }} />
          </div>
          <div className="metric-value" style={{ color: '#34d399' }}>
            {verifiedRecoveryRate !== null ? `${verifiedRecoveryRate}%` : '—'}
          </div>
          <div className="metric-sub">
            {finishedRuns > 0
              ? `${completedCount} of ${finishedRuns} concluded runs verified healthy`
              : 'Awaiting concluded experiment runs'}
          </div>
        </div>
      </div>

      {/* Status Breakdown Segmented Bar */}
      <div
        className="card"
        style={{
          padding: '20px 28px',
          background: 'var(--bg-card-elevated)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
          <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Experiment Lifecycle Breakdown
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="badge badge-completed" style={{ padding: '4px 8px' }}>
                <Check size={12} /> Completed
              </span>
              <strong style={{ fontSize: '1.05rem', color: '#f8fafc' }}>{completedCount}</strong>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="badge badge-failed" style={{ padding: '4px 8px' }}>
                <XCircle size={12} /> Failed
              </span>
              <strong style={{ fontSize: '1.05rem', color: '#f8fafc' }}>{failedCount}</strong>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="badge badge-pending" style={{ padding: '4px 8px' }}>
                <Clock size={12} /> Pending
              </span>
              <strong style={{ fontSize: '1.05rem', color: '#f8fafc' }}>{pendingCount}</strong>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="badge badge-cancelled" style={{ padding: '4px 8px' }}>
                <Slash size={12} /> Cancelled
              </span>
              <strong style={{ fontSize: '1.05rem', color: '#f8fafc' }}>{cancelledCount}</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Target Status Overview Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <Server size={20} style={{ color: 'var(--accent-primary)' }} />
              Registered Target Environments
            </h3>
            <p className="card-subtitle">
              Isolated Docker Compose applications explicitly authorized for resilience testing
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => onNavigate('targets')}>
            Manage Targets <ArrowRight size={15} />
          </button>
        </div>

        {targets.length === 0 ? (
          <div className="empty-state" style={{ padding: '36px 24px' }}>
            <p style={{ fontSize: '0.95rem' }}>No target environments registered yet.</p>
            <button className="btn btn-primary btn-sm" onClick={() => onNavigate('targets')}>
              Register Target Environment
            </button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20 }}>
            {targets.map((target) => (
              <div
                key={target.id}
                style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: '20px 22px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ fontSize: '1.05rem', color: '#f8fafc' }}>{target.name}</strong>
                  <span className={`badge badge-${target.validation_status}`}>
                    {target.validation_status}
                  </span>
                </div>
                <div style={{ fontSize: '0.86rem', color: 'var(--text-muted)' }}>
                  Compose Project: <code className="code-badge">{target.compose_project}</code>
                </div>
                <div style={{ fontSize: '0.86rem', color: 'var(--text-secondary)' }}>
                  Authorized Services: <strong>{target.allowed_services?.length || 0}</strong>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 'auto', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
                  {target.last_validated_at
                    ? `Last validated: ${new Date(target.last_validated_at).toLocaleTimeString()}`
                    : 'Not validated yet'}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Visual Analytics & Charts Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))', gap: 24 }}>
        {/* Outcome Breakdown Chart */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">
                <BarChart3 size={20} style={{ color: 'var(--accent-cyan)' }} />
                Experiment Outcomes
              </h3>
              <p className="card-subtitle">
                Distribution of recorded experiment results
              </p>
            </div>
          </div>
          <OutcomeChart experiments={experiments} />
        </div>

        {/* Verified Recovery Comparison Chart */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">
                <ShieldCheck size={20} style={{ color: 'var(--accent-emerald)' }} />
                Recovery Time Comparison
              </h3>
              <p className="card-subtitle">
                Measured duration (seconds) until health verification
              </p>
            </div>
          </div>
          <RecoveryChart experiments={experiments} />
        </div>
      </div>

      {/* Recent Experiments Activity Table */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Recent Experiment Activity</h3>
            <p className="card-subtitle">Latest recorded chaos experiments and observations</p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => onNavigate('experiments')}>
            View All Experiments <ArrowRight size={15} />
          </button>
        </div>

        {recentExperiments.length === 0 ? (
          <div className="empty-state" style={{ padding: '36px 24px' }}>
            <p style={{ fontSize: '0.95rem' }}>No experiment runs recorded yet.</p>
            <button className="btn btn-primary btn-sm" onClick={() => onNavigate('experiments')}>
              Create First Experiment
            </button>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Target Service</th>
                  <th>Fault Type</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Recovery</th>
                  <th>Created At</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {recentExperiments.map((exp) => (
                  <tr key={exp.id}>
                    <td>
                      <code className="code-badge">#{exp.id}</code>
                    </td>
                    <td>
                      <strong style={{ color: '#f8fafc', fontSize: '0.95rem' }}>{exp.target_service}</strong>
                    </td>
                    <td>
                      <span className="code-badge">{exp.fault_type}</span>
                    </td>
                    <td>
                      <span className={`badge badge-${exp.status}`}>
                        {exp.status}
                      </span>
                    </td>
                    <td>
                      {exp.parameters?.duration_seconds ? `${exp.parameters.duration_seconds}s` : '—'}
                    </td>
                    <td>
                      {exp.recovery_time_seconds != null && exp.status === 'completed' ? (
                        <span style={{ color: '#34d399', fontWeight: 700 }}>
                          {exp.recovery_time_seconds}s
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                    </td>
                    <td>
                      {exp.created_at ? new Date(exp.created_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => onSelectExperiment(exp.id)}
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
