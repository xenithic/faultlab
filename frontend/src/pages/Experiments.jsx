import React, { useState } from 'react';
import {
  Zap,
  Plus,
  Play,
  Square,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  Slash,
  Eye,
  Filter,
  Lock,
  X,
} from 'lucide-react';
import { api } from '../api/client';

const SUPPORTED_FAULTS = [
  {
    id: 'service_failure',
    name: 'Service Failure',
    desc: 'Safely stops the validated container via Docker API with SIGTERM grace period, then restarts and verifies health recovery.',
  },
  {
    id: 'service_pause',
    name: 'Service Pause',
    desc: 'Freezes target container processes using Linux cgroups (docker pause), waits for duration, then unpauses and verifies recovery.',
  },
  {
    id: 'latency',
    name: 'Latency Injection',
    desc: 'Applies bounded millisecond network/traffic latency with optional jitter to target microservice application routes.',
  },
  {
    id: 'resource_stress',
    name: 'CPU / Memory Stress',
    desc: 'Runs bounded CPU and memory stress workers inside the container, tracking process termination upon verified recovery.',
  },
  {
    id: 'http_error',
    name: 'HTTP Error Injection',
    desc: 'Injects configurable HTTP error status codes (e.g., 500, 503) at a bounded error rate for target application routes.',
  },
];

const DEFERRED_FAULTS = [];

export default function Experiments({
  experiments = [],
  targets = [],
  loading,
  error,
  onRefresh,
  onSelectExperiment,
  onNavigate,
}) {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [startingId, setStartingId] = useState(null);
  const [cancellingId, setCancellingId] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  // Filters
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterFault, setFilterFault] = useState('all');

  // Form State
  const validatedTargets = targets.filter((t) => t.validation_status === 'valid');
  const [selectedTargetId, setSelectedTargetId] = useState(
    validatedTargets.length > 0 ? validatedTargets[0].id : (targets[0]?.id || '')
  );
  const currentTarget = targets.find((t) => t.id === Number(selectedTargetId));
  const availableServices = currentTarget?.allowed_services || [];

  const [formData, setFormData] = useState({
    fault_type: 'service_failure',
    target_service: availableServices[0] || '',
    duration_seconds: 10,
    stop_timeout: 5,
    recovery_timeout: 15,
    // Latency
    latency_ms: 200,
    jitter_ms: 50,
    // Resource stress
    stress_type: 'both',
    cpu_workers: 2,
    cpu_load: 80,
    memory_mb: 128,
    // HTTP error
    error_code: 503,
    error_rate: 1.0,
  });
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  // Handle target switch in modal
  const handleTargetChange = (newTargetId) => {
    setSelectedTargetId(newTargetId);
    const target = targets.find((t) => t.id === Number(newTargetId));
    const svcs = target?.allowed_services || [];
    setFormData((prev) => ({
      ...prev,
      target_service: svcs[0] || '',
    }));
  };

  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);

    if (!selectedTargetId) {
      setFormError('Please select a target environment.');
      return;
    }
    if (!formData.target_service) {
      setFormError('Please select an authorized service from the target allowlist.');
      return;
    }

    const duration = Number(formData.duration_seconds);
    if (isNaN(duration) || duration < 1 || duration > 300) {
      setFormError('Duration must be between 1 and 300 seconds.');
      return;
    }

    const params = {
      duration_seconds: duration,
      recovery_timeout: Number(formData.recovery_timeout) || 15,
    };

    if (formData.fault_type === 'service_failure') {
      const stopTimeout = Number(formData.stop_timeout);
      if (isNaN(stopTimeout) || stopTimeout < 1 || stopTimeout > 30) {
        setFormError('Stop timeout must be between 1 and 30 seconds.');
        return;
      }
      params.stop_timeout = stopTimeout;
    } else if (formData.fault_type === 'latency') {
      const latMs = Number(formData.latency_ms);
      const jitMs = Number(formData.jitter_ms);
      if (isNaN(latMs) || latMs < 10 || latMs > 10000) {
        setFormError('Latency must be between 10 and 10000 ms.');
        return;
      }
      if (isNaN(jitMs) || jitMs < 0 || jitMs > 5000 || jitMs > latMs) {
        setFormError('Jitter must be between 0 and 5000 ms and cannot exceed latency.');
        return;
      }
      params.latency_ms = latMs;
      params.jitter_ms = jitMs;
    } else if (formData.fault_type === 'resource_stress') {
      const workers = Number(formData.cpu_workers);
      const cpuLoad = Number(formData.cpu_load);
      const memMb = Number(formData.memory_mb);
      if (isNaN(workers) || workers < 1 || workers > 4) {
        setFormError('CPU workers must be between 1 and 4.');
        return;
      }
      if (isNaN(cpuLoad) || cpuLoad < 1 || cpuLoad > 100) {
        setFormError('CPU load must be between 1% and 100%.');
        return;
      }
      if (isNaN(memMb) || memMb < 10 || memMb > 512) {
        setFormError('Memory stress must be between 10 MB and 512 MB.');
        return;
      }
      params.stress_type = formData.stress_type;
      params.cpu_workers = workers;
      params.cpu_load = cpuLoad;
      params.memory_bytes = `${memMb}M`;
    } else if (formData.fault_type === 'http_error') {
      const errCode = Number(formData.error_code);
      const errRate = Number(formData.error_rate);
      const allowedCodes = [400, 404, 429, 500, 502, 503, 504];
      if (!allowedCodes.includes(errCode)) {
        setFormError(`Invalid HTTP status code. Allowed: ${allowedCodes.join(', ')}`);
        return;
      }
      if (isNaN(errRate) || errRate < 0.01 || errRate > 1.0) {
        setFormError('Error rate must be between 0.01 (1%) and 1.0 (100%).');
        return;
      }
      params.error_code = errCode;
      params.error_rate = errRate;
    }

    setFormSubmitting(true);
    try {
      const newExp = await api.createExperiment({
        target_id: Number(selectedTargetId),
        fault_type: formData.fault_type,
        target_service: formData.target_service,
        parameters: params,
      });

      setShowCreateModal(false);
      setActionSuccess(`Experiment #${newExp.id} created in 'pending' status against ${formData.target_service}. Click Start to run.`);
      await onRefresh();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleStart = async (expId) => {
    setStartingId(expId);
    setActionError(null);
    setActionSuccess(null);
    try {
      await api.startExperiment(expId);
      setActionSuccess(`Experiment #${expId} started. Injection lifecycle running.`);
      await onRefresh();
    } catch (err) {
      setActionError(`Failed to start experiment: ${err.message}`);
    } finally {
      setStartingId(null);
    }
  };

  const handleCancel = async (expId) => {
    setCancellingId(expId);
    setActionError(null);
    setActionSuccess(null);
    try {
      const res = await api.cancelExperiment(expId);
      setActionSuccess(res.message || `Experiment #${expId} cancellation requested.`);
      await onRefresh();
    } catch (err) {
      setActionError(`Failed to cancel experiment: ${err.message}`);
    } finally {
      setCancellingId(null);
    }
  };

  // Filtered experiments
  const filteredExperiments = experiments.filter((exp) => {
    if (filterStatus !== 'all' && exp.status !== filterStatus) return false;
    if (filterFault !== 'all' && exp.fault_type !== filterFault) return false;
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      {/* Top Header & Create Button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Experiment Management
          </h3>
          <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginTop: 2 }}>
            Controlled chaos injection sessions with verified recovery and telemetry recording
          </p>
        </div>

        <button
          className="btn btn-primary"
          onClick={() => {
            if (validatedTargets.length === 0) {
              setActionError('Cannot create experiment: No validated target found. Please validate a target on the Targets page first.');
              return;
            }
            setShowCreateModal(true);
          }}
        >
          <Plus size={18} /> New Experiment
        </button>
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

      {/* Filter Toolbar */}
      <div className="card" style={{ padding: '18px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: '0.88rem' }}>
            <Filter size={18} />
            <span>Filter by:</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <label style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Status:</label>
            <select
              className="form-select"
              style={{ width: 'auto', padding: '8px 14px', fontSize: '0.88rem' }}
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
            >
              <option value="all">All Statuses ({experiments.length})</option>
              <option value="running">Running</option>
              <option value="pending">Pending</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <label style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Fault:</label>
            <select
              className="form-select"
              style={{ width: 'auto', padding: '8px 14px', fontSize: '0.88rem' }}
              value={filterFault}
              onChange={(e) => setFilterFault(e.target.value)}
            >
              <option value="all">All Fault Types</option>
              <option value="service_failure">Service Failure</option>
              <option value="service_pause">Service Pause</option>
              <option value="latency">Latency Injection</option>
              <option value="resource_stress">Resource Stress</option>
              <option value="http_error">HTTP Error</option>
            </select>
          </div>

          <div style={{ marginLeft: 'auto', fontSize: '0.84rem', color: 'var(--text-muted)' }}>
            Showing <strong>{filteredExperiments.length}</strong> of {experiments.length} experiments
          </div>
        </div>
      </div>

      {/* Experiments Table */}
      {loading && experiments.length === 0 ? (
        <div className="empty-state" style={{ padding: '60px 24px' }}>
          <div className="loading-spinner" style={{ width: 36, height: 36 }} />
          <h3>Loading experiments...</h3>
        </div>
      ) : filteredExperiments.length === 0 ? (
        <div className="card empty-state">
          <Zap size={56} className="empty-state-icon" />
          <h3>No Experiments Found</h3>
          <p style={{ fontSize: '0.95rem' }}>
            {experiments.length === 0
              ? 'Create a pending experiment against a validated target to begin testing.'
              : 'No experiments match the selected filter criteria.'}
          </p>
          {experiments.length === 0 && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => {
                if (validatedTargets.length === 0) {
                  onNavigate('targets');
                } else {
                  setShowCreateModal(true);
                }
              }}
            >
              {validatedTargets.length === 0 ? 'Go to Targets to Validate' : 'New Experiment'}
            </button>
          )}
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Target & Service</th>
                  <th>Fault Type</th>
                  <th>Parameters</th>
                  <th>Status</th>
                  <th>Recovery</th>
                  <th>Timestamps</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredExperiments.map((exp) => {
                  const isStarting = startingId === exp.id;
                  const isCancelling = cancellingId === exp.id;
                  const isRunning = exp.status === 'running';
                  const isPending = exp.status === 'pending';

                  return (
                    <tr key={exp.id}>
                      <td>
                        <code className="code-badge">#{exp.id}</code>
                      </td>
                      <td>
                        <div style={{ fontWeight: 700, color: '#f8fafc', fontSize: '0.95rem' }}>
                          {exp.target_service}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 2 }}>
                          Target ID: {exp.target_id}
                          {exp.target_container_id && (
                            <span> | <code className="code-badge" style={{ fontSize: '0.78rem' }}>{exp.target_container_id.substring(0, 12)}</code></span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className="code-badge">{exp.fault_type}</span>
                      </td>
                      <td style={{ fontSize: '0.84rem' }}>
                        <div>Duration: <strong>{exp.parameters?.duration_seconds}s</strong></div>
                        {exp.parameters?.stop_timeout && (
                          <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>Stop Timeout: {exp.parameters.stop_timeout}s</div>
                        )}
                        {exp.parameters?.latency_ms && (
                          <div style={{ color: '#38bdf8', marginTop: 2 }}>
                            Latency: {exp.parameters.latency_ms}ms (±{exp.parameters.jitter_ms || 0}ms)
                          </div>
                        )}
                        {exp.parameters?.stress_type && (
                          <div style={{ color: '#a78bfa', marginTop: 2 }}>
                            Stress: {exp.parameters.stress_type} (CPU: {exp.parameters.cpu_load}%, Mem: {exp.parameters.memory_bytes})
                          </div>
                        )}
                        {exp.parameters?.error_code && (
                          <div style={{ color: '#fb7185', marginTop: 2 }}>
                            HTTP {exp.parameters.error_code} ({Math.round((exp.parameters.error_rate || 1) * 100)}% rate)
                          </div>
                        )}
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span className={`badge badge-${exp.status}`}>
                            {exp.status}
                          </span>
                          {isRunning && <span className="loading-spinner" style={{ width: 14, height: 14 }} />}
                        </div>
                        {exp.error_message && (
                          <div
                            style={{
                              fontSize: '0.78rem',
                              color: '#fb7185',
                              maxWidth: 240,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              marginTop: 4,
                            }}
                            title={exp.error_message}
                          >
                            {exp.error_message}
                          </div>
                        )}
                      </td>
                      <td>
                        {exp.recovery_time_seconds != null && exp.status === 'completed' ? (
                          <div>
                            <span style={{ color: '#34d399', fontWeight: 700, fontSize: '0.95rem' }}>
                              {exp.recovery_time_seconds}s
                            </span>
                            <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                              {exp.result_metrics?.recovery_verification?.status || 'verified'}
                            </div>
                          </div>
                        ) : (
                          <div>
                            {exp.status === 'failed' && exp.result_metrics?.recovery_verification?.status ? (
                              <span
                                className={`badge badge-${exp.result_metrics.recovery_verification.status}`}
                                style={{ fontSize: '0.75rem', textTransform: 'capitalize' }}
                              >
                                {exp.result_metrics.recovery_verification.status}
                              </span>
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>—</span>
                            )}
                          </div>
                        )}
                      </td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        <div>Created: {exp.created_at ? new Date(exp.created_at).toLocaleTimeString() : '—'}</div>
                        {exp.started_at && <div>Started: {new Date(exp.started_at).toLocaleTimeString()}</div>}
                        {exp.ended_at && <div>Ended: {new Date(exp.ended_at).toLocaleTimeString()}</div>}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: 8 }}>
                          {isPending && (
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => handleStart(exp.id)}
                              disabled={isStarting || isCancelling}
                              title="Start execution of this experiment"
                            >
                              <Play size={14} className={isStarting ? 'loading-spinner' : ''} />
                              <span>{isStarting ? 'Starting...' : 'Start'}</span>
                            </button>
                          )}

                          {(isPending || isRunning) && (
                            <button
                              className="btn btn-danger btn-sm"
                              onClick={() => handleCancel(exp.id)}
                              disabled={isStarting || isCancelling}
                              title={isRunning ? "Trigger immediate recovery and cancellation" : "Cancel pending experiment"}
                            >
                              <Square size={14} className={isCancelling ? 'loading-spinner' : ''} />
                              <span>{isCancelling ? 'Cancelling...' : 'Cancel'}</span>
                            </button>
                          )}

                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => onSelectExperiment(exp.id)}
                            title="Inspect detailed metrics and observations"
                          >
                            <Eye size={14} />
                            <span>Details</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create Experiment Modal */}
      {showCreateModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
            padding: 24,
          }}
        >
          <div
            className="card"
            style={{
              width: '100%',
              maxWidth: 700,
              backgroundColor: '#101626',
              boxShadow: 'var(--shadow-lg)',
              border: '1px solid var(--border-accent)',
              maxHeight: '92vh',
              overflowY: 'auto',
            }}
          >
            <div className="card-header">
              <h3 className="card-title">
                <Zap size={20} style={{ color: 'var(--accent-primary)' }} />
                Create Resilience Experiment
              </h3>
              <button className="btn-icon" onClick={() => setShowCreateModal(false)}><X size={18} /></button>
            </div>

            {formError && (
              <div className="alert alert-danger" style={{ marginBottom: 20 }}>
                <AlertTriangle size={20} style={{ flexShrink: 0 }} />
                <span>{formError}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit}>
              {/* Target Selector */}
              <div className="form-group">
                <label className="form-label">Target Environment *</label>
                <select
                  className="form-select"
                  value={selectedTargetId}
                  onChange={(e) => handleTargetChange(e.target.value)}
                  required
                >
                  {validatedTargets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} (Compose: {t.compose_project}) — Validated Active
                    </option>
                  ))}
                </select>
                <span className="form-hint">Only targets with validation_status 'valid' can accept experiments</span>
              </div>

              {/* Service Selector */}
              <div className="form-group">
                <label className="form-label">Target Microservice *</label>
                <select
                  className="form-select"
                  value={formData.target_service}
                  onChange={(e) => setFormData({ ...formData, target_service: e.target.value })}
                  required
                >
                  {availableServices.map((svc) => (
                    <option key={svc} value={svc}>
                      {svc}
                    </option>
                  ))}
                </select>
                <span className="form-hint">Restricted strictly to the target environment's authorized service allowlist</span>
              </div>

              {/* Fault Type Selection */}
              <div className="form-group">
                <label className="form-label">Fault Type Selection *</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 4 }}>
                  {/* Supported Fault Cards */}
                  {SUPPORTED_FAULTS.map((f) => {
                    const isSelected = formData.fault_type === f.id;
                    return (
                      <label
                        key={f.id}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: 14,
                          padding: '16px 18px',
                          background: isSelected ? 'rgba(59, 130, 246, 0.14)' : 'var(--bg-surface)',
                          border: `2px solid ${isSelected ? 'var(--accent-primary)' : 'var(--border-color)'}`,
                          borderRadius: 'var(--radius-md)',
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <input
                          type="radio"
                          name="fault_type"
                          value={f.id}
                          checked={isSelected}
                          onChange={(e) => setFormData({ ...formData, fault_type: e.target.value })}
                          style={{ marginTop: 4, width: 16, height: 16 }}
                        />
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <strong style={{ fontSize: '0.98rem', color: '#f8fafc' }}>{f.name}</strong>
                            <span className="badge badge-completed" style={{ fontSize: '0.7rem' }}>Supported</span>
                          </div>
                          <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.4 }}>
                            {f.desc}
                          </div>
                        </div>
                      </label>
                    );
                  })}

                  {/* Deferred Fault Cards (if any) */}
                  {DEFERRED_FAULTS.length > 0 && (
                    <>
                      <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', marginTop: 8, letterSpacing: '0.06em' }}>
                        DEFERRED FAULT TYPES:
                      </div>
                      {DEFERRED_FAULTS.map((f) => (
                        <div
                          key={f.id}
                          style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 14,
                            padding: '14px 18px',
                            background: 'rgba(15, 23, 42, 0.4)',
                            border: '1px solid rgba(71, 85, 105, 0.25)',
                            borderRadius: 'var(--radius-md)',
                            opacity: 0.55,
                            cursor: 'not-allowed',
                          }}
                        >
                          <Lock size={16} style={{ marginTop: 4, color: 'var(--text-muted)', flexShrink: 0 }} />
                          <div style={{ flex: 1 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-secondary)' }}>
                                {f.name}
                              </span>
                              <span className="badge badge-unvalidated" style={{ fontSize: '0.68rem' }}>Deferred</span>
                            </div>
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.4 }}>
                              {f.desc}
                            </div>
                          </div>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>

              {/* Common Duration & Recovery Parameters */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 12 }}>
                <div className="form-group">
                  <label className="form-label">Duration (seconds) *</label>
                  <input
                    type="number"
                    className="form-input"
                    min="1"
                    max="300"
                    value={formData.duration_seconds}
                    onChange={(e) => setFormData({ ...formData, duration_seconds: e.target.value })}
                    required
                  />
                  <span className="form-hint">Fault duration window (1 – 300 seconds)</span>
                </div>

                <div className="form-group">
                  <label className="form-label">Recovery Timeout (seconds)</label>
                  <input
                    type="number"
                    className="form-input"
                    min="1"
                    max="60"
                    value={formData.recovery_timeout}
                    onChange={(e) => setFormData({ ...formData, recovery_timeout: e.target.value })}
                  />
                  <span className="form-hint">Max wait for health verification (1 – 60 seconds)</span>
                </div>
              </div>

              {/* Fault-Specific Parameters */}
              {formData.fault_type === 'service_failure' && (
                <div className="form-group" style={{ marginTop: 12 }}>
                  <label className="form-label">Stop Timeout (seconds) *</label>
                  <input
                    type="number"
                    className="form-input"
                    min="1"
                    max="30"
                    value={formData.stop_timeout}
                    onChange={(e) => setFormData({ ...formData, stop_timeout: e.target.value })}
                    required
                  />
                  <span className="form-hint">Grace period for SIGTERM before SIGKILL (1 – 30 seconds)</span>
                </div>
              )}

              {formData.fault_type === 'latency' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Latency (ms) *</label>
                    <input
                      type="number"
                      className="form-input"
                      min="10"
                      max="10000"
                      step="10"
                      value={formData.latency_ms}
                      onChange={(e) => setFormData({ ...formData, latency_ms: e.target.value })}
                      required
                    />
                    <span className="form-hint">Added delay on target traffic (10 – 10,000 ms)</span>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Jitter (ms)</label>
                    <input
                      type="number"
                      className="form-input"
                      min="0"
                      max="5000"
                      step="5"
                      value={formData.jitter_ms}
                      onChange={(e) => setFormData({ ...formData, jitter_ms: e.target.value })}
                    />
                    <span className="form-hint">Variance added to delay (0 – 5,000 ms)</span>
                  </div>
                </div>
              )}

              {formData.fault_type === 'resource_stress' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Stress Type *</label>
                    <select
                      className="form-select"
                      value={formData.stress_type}
                      onChange={(e) => setFormData({ ...formData, stress_type: e.target.value })}
                    >
                      <option value="both">Both CPU & Memory</option>
                      <option value="cpu">CPU Stress Only</option>
                      <option value="memory">Memory Stress Only</option>
                    </select>
                    <span className="form-hint">Target resource subsystem to stress</span>
                  </div>

                  <div className="form-group">
                    <label className="form-label">CPU Workers (1–4)</label>
                    <input
                      type="number"
                      className="form-input"
                      min="1"
                      max="4"
                      value={formData.cpu_workers}
                      onChange={(e) => setFormData({ ...formData, cpu_workers: e.target.value })}
                      disabled={formData.stress_type === 'memory'}
                    />
                    <span className="form-hint">Number of worker threads (1 – 4)</span>
                  </div>

                  <div className="form-group">
                    <label className="form-label">CPU Target Load (%)</label>
                    <input
                      type="number"
                      className="form-input"
                      min="1"
                      max="100"
                      value={formData.cpu_load}
                      onChange={(e) => setFormData({ ...formData, cpu_load: e.target.value })}
                      disabled={formData.stress_type === 'memory'}
                    />
                    <span className="form-hint">Target worker duty cycle (1 – 100%)</span>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Memory Stress (MB)</label>
                    <input
                      type="number"
                      className="form-input"
                      min="10"
                      max="512"
                      step="10"
                      value={formData.memory_mb}
                      onChange={(e) => setFormData({ ...formData, memory_mb: e.target.value })}
                      disabled={formData.stress_type === 'cpu'}
                    />
                    <span className="form-hint">Bounded buffer size (10 – 512 MB)</span>
                  </div>
                </div>
              )}

              {formData.fault_type === 'http_error' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 12 }}>
                  <div className="form-group">
                    <label className="form-label">HTTP Error Code *</label>
                    <select
                      className="form-select"
                      value={formData.error_code}
                      onChange={(e) => setFormData({ ...formData, error_code: Number(e.target.value) })}
                    >
                      <option value={503}>503 Service Unavailable</option>
                      <option value={500}>500 Internal Server Error</option>
                      <option value={502}>502 Bad Gateway</option>
                      <option value={504}>504 Gateway Timeout</option>
                      <option value={429}>429 Too Many Requests</option>
                      <option value={400}>400 Bad Request</option>
                      <option value={404}>404 Not Found</option>
                    </select>
                    <span className="form-hint">HTTP status injected on application routes</span>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Error Rate (Probability) *</label>
                    <select
                      className="form-select"
                      value={formData.error_rate}
                      onChange={(e) => setFormData({ ...formData, error_rate: Number(e.target.value) })}
                    >
                      <option value={1.0}>100% (All requests fail)</option>
                      <option value={0.75}>75% (3 in 4 requests fail)</option>
                      <option value={0.5}>50% (1 in 2 requests fail)</option>
                      <option value={0.25}>25% (1 in 4 requests fail)</option>
                      <option value={0.1}>10% (1 in 10 requests fail)</option>
                    </select>
                    <span className="form-hint">Fraction of incoming requests receiving error</span>
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 14, marginTop: 32 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                  disabled={formSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={formSubmitting}
                >
                  {formSubmitting ? 'Creating...' : 'Create Pending Experiment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
