import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  Play,
  Square,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Shield,
  Activity,
  Layers,
  RefreshCw,
  Cpu,
  Check,
  X,
  Terminal,
} from 'lucide-react';
import { api } from '../api/client';
import PhaseMetricsChart from '../components/Charts/PhaseMetricsChart';

export default function ExperimentDetail({
  experimentId,
  onBack,
  onRefreshParent,
}) {
  const [experiment, setExperiment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  const fetchExperiment = async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await api.getExperiment(experimentId);
      setExperiment(data);
    } catch (err) {
      setError(`Failed to load experiment details: ${err.message}`);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    fetchExperiment();
  }, [experimentId]);

  // Polling: refresh experiment status while running, and STOP polling once terminal state is reached
  useEffect(() => {
    if (!experiment || experiment.status !== 'running') {
      return;
    }

    const timer = setInterval(() => {
      fetchExperiment(true);
    }, 2000);

    return () => clearInterval(timer);
  }, [experiment?.status]);

  const handleStart = async () => {
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      await api.startExperiment(experimentId);
      setActionSuccess(`Experiment #${experimentId} execution started.`);
      await fetchExperiment(true);
      if (onRefreshParent) onRefreshParent();
    } catch (err) {
      setActionError(`Failed to start: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const res = await api.cancelExperiment(experimentId);
      setActionSuccess(res.message || `Experiment #${experimentId} cancelled.`);
      await fetchExperiment(true);
      if (onRefreshParent) onRefreshParent();
    } catch (err) {
      setActionError(`Failed to cancel: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && !experiment) {
    return (
      <div className="empty-state" style={{ padding: '80px 24px' }}>
        <div className="loading-spinner" style={{ width: 40, height: 40 }} />
        <h3>Loading experiment #{experimentId}...</h3>
      </div>
    );
  }

  if (error || !experiment) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <button className="btn btn-secondary btn-sm" onClick={onBack} style={{ width: 'fit-content' }}>
          <ArrowLeft size={16} /> Back to Experiments
        </button>
        <div className="alert alert-danger">
          <AlertTriangle size={22} style={{ flexShrink: 0 }} />
          <span>{error || 'Experiment not found.'}</span>
        </div>
      </div>
    );
  }

  const isRunning = experiment.status === 'running';
  const isPending = experiment.status === 'pending';

  const resultMetrics = experiment.result_metrics || {};
  const baselineMetrics = experiment.baseline_metrics || {};
  const before = resultMetrics.before || baselineMetrics;
  const during = resultMetrics.during || {};
  const after = resultMetrics.after || {};
  const recovery = resultMetrics.recovery_verification || {};
  const cleanup = resultMetrics.cleanup || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      {/* Top Navigation & Status Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button className="btn btn-secondary btn-sm" onClick={onBack}>
            <ArrowLeft size={16} /> Back
          </button>
          <h3 style={{ fontSize: '1.45rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Experiment #{experiment.id}: <span style={{ color: '#38bdf8' }}>{experiment.target_service}</span>
          </h3>
          <span className={`badge badge-${experiment.status}`}>
            {experiment.status}
          </span>
          {isRunning && <span className="loading-spinner" style={{ width: 16, height: 16 }} />}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => fetchExperiment(false)}
            title="Reload details"
          >
            <RefreshCw size={15} /> Refresh
          </button>

          {isPending && (
            <button
              className="btn btn-primary btn-sm"
              onClick={handleStart}
              disabled={actionLoading}
            >
              <Play size={15} />
              <span>{actionLoading ? 'Starting...' : 'Start Experiment'}</span>
            </button>
          )}

          {(isPending || isRunning) && (
            <button
              className="btn btn-danger btn-sm"
              onClick={handleCancel}
              disabled={actionLoading}
            >
              <Square size={15} />
              <span>{actionLoading ? 'Cancelling...' : 'Cancel Experiment'}</span>
            </button>
          )}
        </div>
      </div>

      {actionSuccess && (
        <div className="alert alert-success">
          <CheckCircle2 size={20} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>{actionSuccess}</span>
          <button className="btn-icon" onClick={() => setActionSuccess(null)}><X size={16} /></button>
        </div>
      )}

      {actionError && (
        <div className="alert alert-danger">
          <AlertTriangle size={20} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>{actionError}</span>
          <button className="btn-icon" onClick={() => setActionError(null)}><X size={16} /></button>
        </div>
      )}

      {/* Execution Error Banner (if any) */}
      {experiment.error_message && (
        <div className="alert alert-danger">
          <AlertTriangle size={22} style={{ flexShrink: 0 }} />
          <div>
            <strong style={{ fontSize: '0.98rem' }}>Execution or Verification Error:</strong>
            <p style={{ marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: '0.86rem', lineHeight: 1.5 }}>
              {experiment.error_message}
            </p>
          </div>
        </div>
      )}

      {/* Core Lifecycle Cards */}
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-label">Fault Injected</span>
          <span className="metric-value" style={{ fontSize: '1.45rem', color: '#f8fafc' }}>
            {experiment.fault_type}
          </span>
          <span className="metric-sub">
            Target Service: <strong style={{ color: '#f8fafc' }}>{experiment.target_service}</strong>
          </span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Parameters</span>
          <span className="metric-value" style={{ fontSize: '1.45rem', color: '#38bdf8' }}>
            {experiment.parameters?.duration_seconds ? `${experiment.parameters.duration_seconds}s` : 'N/A'}
          </span>
          <span className="metric-sub">
            {experiment.fault_type === 'latency' && (
              <span>Delay: <strong>{experiment.parameters?.latency_ms}ms</strong> (±{experiment.parameters?.jitter_ms || 0}ms)</span>
            )}
            {experiment.fault_type === 'resource_stress' && (
              <span>Stress: <strong>{experiment.parameters?.stress_type}</strong> (CPU {experiment.parameters?.cpu_load}%, Mem {experiment.parameters?.memory_bytes})</span>
            )}
            {experiment.fault_type === 'http_error' && (
              <span>Error: <strong>HTTP {experiment.parameters?.error_code}</strong> ({Math.round((experiment.parameters?.error_rate || 1) * 100)}% rate)</span>
            )}
            {experiment.fault_type === 'service_failure' && (
              <span>Stop Timeout: <strong>{experiment.parameters?.stop_timeout || 5}s</strong></span>
            )}
            {experiment.fault_type === 'service_pause' && (
              <span>Recovery Timeout: <strong>{experiment.parameters?.recovery_timeout || 15}s</strong></span>
            )}
          </span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Recovery Measurement</span>
          <span
            className="metric-value"
            style={{
              fontSize: '1.45rem',
              color: recovery.verified ? '#34d399' : recovery.status === 'failed' ? '#fb7185' : '#fbbf24',
            }}
          >
            {experiment.recovery_time_seconds != null && recovery.verified ? `${experiment.recovery_time_seconds}s` : (recovery.status ? (recovery.status.charAt(0).toUpperCase() + recovery.status.slice(1)) : 'Pending')}
          </span>
          <span className="metric-sub">
            Verification: <strong>{recovery.status || 'Not evaluated'}</strong>
          </span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Bound Container</span>
          <span className="metric-value" style={{ fontSize: '1.05rem', fontFamily: 'var(--font-mono)', color: '#a78bfa' }}>
            {experiment.target_container_id ? experiment.target_container_id.substring(0, 16) : 'Unbound'}
          </span>
          <span className="metric-sub">Validated Docker container ID</span>
        </div>
      </div>

      {/* Three-Phase Observation Grid: BEFORE, DURING, AFTER */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <Layers size={20} style={{ color: 'var(--accent-primary)' }} />
              Phase Observations Sequence
            </h3>
            <p className="card-subtitle">
              Discrete telemetry snapshots recorded during the chaos testing lifecycle
            </p>
          </div>
        </div>

        <div className="phase-grid">
          {/* BEFORE */}
          <div className="phase-card">
            <div className="phase-header before">
              <span>Phase 1: Before Fault</span>
              <span className="badge badge-outline" style={{ fontSize: '0.7rem' }}>Baseline</span>
            </div>
            <div className="phase-metric-row">
              <span>Timestamp:</span>
              <span className="phase-metric-val">
                {before?.timestamp ? new Date(before.timestamp).toLocaleTimeString() : 'Pending'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>Container Status:</span>
              <span className="phase-metric-val" style={{ color: '#34d399' }}>
                {before?.container_state?.status || 'Unknown'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>Docker Health:</span>
              <span className="phase-metric-val">
                {before?.container_state?.health || 'None'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>HTTP Probe:</span>
              <span className="phase-metric-val">
                {before?.http_health?.available
                  ? `${before.http_health.latency_ms} ms (HTTP ${before.http_health.status_code})`
                  : 'Unavailable'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>CPU Utilization:</span>
              <span className="phase-metric-val">
                {before?.container_stats?.available
                  ? `${before.container_stats.cpu_percent}%`
                  : 'Unavailable'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>Memory Usage:</span>
              <span className="phase-metric-val">
                {before?.container_stats?.available
                  ? `${(before.container_stats.memory_usage_bytes / (1024 * 1024)).toFixed(1)} MB`
                  : 'Unavailable'}
              </span>
            </div>
          </div>

          {/* DURING */}
          <div className="phase-card">
            <div className="phase-header during">
              <span>Phase 2: During Fault</span>
              <span className="badge badge-failed" style={{ fontSize: '0.7rem' }}>Impact</span>
            </div>
            <div className="phase-metric-row">
              <span>Timestamp:</span>
              <span className="phase-metric-val">
                {during?.timestamp ? new Date(during.timestamp).toLocaleTimeString() : 'Pending / Skipped'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>Container Status:</span>
              <span className="phase-metric-val" style={{ color: '#fb7185' }}>
                {during?.container_state?.status || (isRunning ? 'In transition...' : 'Not recorded')}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>Docker Health:</span>
              <span className="phase-metric-val">
                {during?.container_state?.health || 'None'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>HTTP Probe:</span>
              <span className="phase-metric-val" style={{ color: during?.http_health?.available ? '#f8fafc' : '#fb7185' }}>
                {during?.http_health?.available
                  ? `${during.http_health.latency_ms} ms (HTTP ${during.http_health.status_code})`
                  : 'Down / Connection Refused'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>Mechanism:</span>
              <span className="phase-metric-val">
                {experiment.fault_type === 'service_pause' && 'Processes Paused (Cgroups)'}
                {experiment.fault_type === 'service_failure' && 'Container Stopped (SIGTERM)'}
                {experiment.fault_type === 'latency' && `Route Delay (${experiment.parameters?.latency_ms || 0}ms)`}
                {experiment.fault_type === 'resource_stress' && `Resource Worker (${experiment.parameters?.stress_type || 'both'})`}
                {experiment.fault_type === 'http_error' && `HTTP Error (${experiment.parameters?.error_code || 500})`}
              </span>
            </div>
            {during?.traffic_probe && (
              <div className="phase-metric-row">
                <span>App Route Probe:</span>
                <span className="phase-metric-val" style={{ color: during.traffic_probe.status_code >= 400 ? '#fb7185' : '#34d399' }}>
                  {during.traffic_probe.status_code ? `HTTP ${during.traffic_probe.status_code} (${during.traffic_probe.latency_ms} ms)` : 'Probe Refused/Failed'}
                </span>
              </div>
            )}
          </div>

          {/* AFTER */}
          <div className="phase-card">
            <div className="phase-header after">
              <span>Phase 3: After Recovery</span>
              <span className="badge badge-valid" style={{ fontSize: '0.7rem' }}>Outcome</span>
            </div>
            <div className="phase-metric-row">
              <span>Timestamp:</span>
              <span className="phase-metric-val">
                {after?.timestamp ? new Date(after.timestamp).toLocaleTimeString() : 'Pending'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>Container Status:</span>
              <span className="phase-metric-val" style={{ color: after?.container_state?.status === 'running' ? '#34d399' : '#fb7185' }}>
                {after?.container_state?.status || 'Pending'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>Docker Health:</span>
              <span className="phase-metric-val">
                {after?.container_state?.health || 'None'}
              </span>
            </div>
            <div className="phase-metric-row">
              <span>HTTP Probe:</span>
              <span className="phase-metric-val">
                {after?.http_health?.available
                  ? `${after.http_health.latency_ms} ms (HTTP ${after.http_health.status_code})`
                  : (isPending || isRunning ? 'Pending recovery...' : 'Unavailable')}
              </span>
            </div>
            {after?.traffic_probe && (
              <div className="phase-metric-row">
                <span>App Route Probe:</span>
                <span className="phase-metric-val" style={{ color: after.traffic_probe.status_code === 200 ? '#34d399' : '#fb7185' }}>
                  {after.traffic_probe.status_code ? `HTTP ${after.traffic_probe.status_code} (${after.traffic_probe.latency_ms} ms)` : 'Unavailable'}
                </span>
              </div>
            )}
            <div className="phase-metric-row">
              <span>Cleanup Status:</span>
              <span className="phase-metric-val" style={{ color: cleanup.success ? '#34d399' : '#fb7185' }}>
                {cleanup.success ? 'Guaranteed Clean' : (cleanup.error || 'Pending')}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Recovery Verification Evidence Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <Shield size={20} style={{ color: 'var(--accent-emerald)' }} />
              Recovery Verification & Evidence
            </h3>
            <p className="card-subtitle">
              Automated resilience validation outcome and supporting evidence recorded by the platform
            </p>
          </div>
          <span className={`badge badge-${recovery.status || 'unvalidated'}`}>
            {recovery.status || 'Unverified'}
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20 }}>
            <div style={{ background: 'var(--bg-surface)', padding: 18, borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>VERIFICATION OUTCOME</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: recovery.verified ? '#34d399' : '#fb7185', marginTop: 6 }}>
                {recovery.verified ? 'Verified Healthy Recovery' : (recovery.status === 'unverified' ? 'Unverified Recovery' : 'Failed Recovery')}
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: 18, borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>MEASURED RECOVERY TIME</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#38bdf8', marginTop: 6 }}>
                {recovery.recovery_time_seconds != null ? `${recovery.recovery_time_seconds} seconds` : 'Not Measured'}
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: 18, borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>CLEANUP SAFETY STATUS</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: cleanup.success ? '#34d399' : '#fb7185', marginTop: 6 }}>
                {cleanup.success ? 'All Containers Recovered' : 'Cleanup Error Detected'}
              </div>
            </div>
          </div>

          <div
            style={{
              background: 'rgba(15, 23, 42, 0.65)',
              padding: 18,
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 8, letterSpacing: '0.05em' }}>
              <Terminal size={16} /> VERIFICATION EVIDENCE LOG:
            </div>
            <p style={{ fontSize: '0.94rem', color: '#f8fafc', fontFamily: 'var(--font-mono)', lineHeight: 1.55 }}>
              {recovery.evidence || 'No recovery verification has been performed yet.'}
            </p>
          </div>
        </div>
      </div>

      {/* Telemetry Charts */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <Activity size={20} style={{ color: 'var(--accent-primary)' }} />
              Experiment Telemetry & Measurements
            </h3>
            <p className="card-subtitle">
              Visual phase comparison of real HTTP probe latency and container resource snapshots
            </p>
          </div>
        </div>

        <PhaseMetricsChart
          resultMetrics={resultMetrics}
          baselineMetrics={baselineMetrics}
        />
      </div>
    </div>
  );
}
