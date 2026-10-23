import React, { useState } from 'react';
import {
  Server,
  Plus,
  RefreshCw,
  Trash2,
  CheckCircle,
  AlertTriangle,
  Shield,
  Layers,
  ChevronDown,
  ChevronRight,
  X,
} from 'lucide-react';
import { api } from '../api/client';

const PROTECTED_NAMES = ['postgres', 'faultlab-platform', 'platform', 'db', 'database'];

export default function Targets({
  targets = [],
  loading,
  error,
  onRefresh,
}) {
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [validatingId, setValidatingId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [expandedTargetId, setExpandedTargetId] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  // Form State
  const [formData, setFormData] = useState({
    name: '',
    compose_project: 'faultlab',
    description: '',
    allowed_services_input: 'product-service, order-service, inventory-service, payment-service, api-gateway',
  });
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);

    const name = formData.name.trim();
    const composeProject = formData.compose_project.trim();
    if (!name) {
      setFormError('Target environment name is required.');
      return;
    }
    if (!composeProject) {
      setFormError('Docker Compose project name is required.');
      return;
    }

    const services = formData.allowed_services_input
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    if (services.length === 0) {
      setFormError('At least one allowed service name must be specified in the allowlist.');
      return;
    }

    // Check for protected services in frontend input
    const protectedMatches = services.filter((s) =>
      PROTECTED_NAMES.includes(s.toLowerCase())
    );
    if (protectedMatches.length > 0) {
      setFormError(
        `Protected platform services cannot be registered as fault targets: ${protectedMatches.join(', ')}`
      );
      return;
    }

    setFormSubmitting(true);
    try {
      await api.registerTarget({
        name,
        compose_project: composeProject,
        description: formData.description.trim(),
        target_type: 'docker_compose',
        allowed_services: services,
      });

      setShowRegisterModal(false);
      setFormData({
        name: '',
        compose_project: 'faultlab',
        description: '',
        allowed_services_input: 'product-service, order-service, inventory-service, payment-service, api-gateway',
      });
      setActionSuccess(`Target environment '${name}' registered successfully. Run live validation to inspect containers.`);
      await onRefresh();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleValidate = async (targetId) => {
    setValidatingId(targetId);
    setActionError(null);
    setActionSuccess(null);
    try {
      const result = await api.validateTarget(targetId);
      const status = result.target?.validation_status;
      if (status === 'valid') {
        setActionSuccess(`Target validated successfully! Live Docker containers discovered and verified.`);
      } else {
        setActionError(`Target validation returned '${status}'. Some services may be missing or unlabelled.`);
      }
      await onRefresh();
    } catch (err) {
      setActionError(`Validation failed: ${err.message}`);
    } finally {
      setValidatingId(null);
    }
  };

  const handleDelete = async (target) => {
    if (!window.confirm(`Are you sure you want to unregister target '${target.name}'? This will also remove associated experiment history.`)) {
      return;
    }

    setDeletingId(target.id);
    setActionError(null);
    setActionSuccess(null);
    try {
      await api.deleteTarget(target.id);
      setActionSuccess(`Target '${target.name}' unregistered successfully.`);
      await onRefresh();
    } catch (err) {
      setActionError(`Failed to unregister target: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const toggleExpand = (id) => {
    setExpandedTargetId(expandedTargetId === id ? null : id);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      {/* Top action row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Target Environments
          </h3>
          <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginTop: 2 }}>
            Explicitly authorized Docker Compose targets eligible for controlled resilience testing
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowRegisterModal(true)}
        >
          <Plus size={18} /> Register Target
        </button>
      </div>

      {actionSuccess && (
        <div className="alert alert-success">
          <CheckCircle size={20} style={{ flexShrink: 0 }} />
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

      {/* Safety Notice Banner */}
      <div className="alert alert-info" style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
        <Shield size={22} style={{ flexShrink: 0, marginTop: 2, color: 'var(--accent-cyan)' }} />
        <div style={{ fontSize: '0.9rem', lineHeight: 1.55 }}>
          <strong>Safety & Scope Invariant:</strong> FaultLab targets must be containerized in Docker Compose, carry the opt-in label <code className="code-badge">faultlab.target=true</code>, and belong to the target's explicit service allowlist. Platform infrastructure (<code className="code-badge">postgres</code>, <code className="code-badge">faultlab-platform</code>, <code className="code-badge">frontend</code>) is protected by invariant enforcement and can never be targeted.
        </div>
      </div>

      {/* Target List */}
      {loading && targets.length === 0 ? (
        <div className="empty-state" style={{ padding: '60px 24px' }}>
          <div className="loading-spinner" style={{ width: 36, height: 36 }} />
          <h3>Loading targets...</h3>
        </div>
      ) : targets.length === 0 ? (
        <div className="card empty-state">
          <Server size={56} className="empty-state-icon" />
          <h3>No Target Environments Registered</h3>
          <p style={{ fontSize: '0.95rem' }}>Register your target Docker Compose application to begin resilience testing.</p>
          <button className="btn btn-primary btn-sm" onClick={() => setShowRegisterModal(true)}>
            <Plus size={16} /> Register Target
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {targets.map((target) => {
            const isExpanded = expandedTargetId === target.id;
            const isValidating = validatingId === target.id;
            const isDeleting = deletingId === target.id;
            const discovered = target.discovered_services || {};
            const discoveredCount = Object.keys(discovered).length;

            return (
              <div key={target.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                    <div
                      style={{
                        padding: 12,
                        borderRadius: 'var(--radius-md)',
                        background: 'rgba(59, 130, 246, 0.12)',
                        color: 'var(--accent-primary)',
                      }}
                    >
                      <Server size={26} />
                    </div>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                        <h4 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                          {target.name}
                        </h4>
                        <span className={`badge badge-${target.validation_status}`}>
                          {target.validation_status}
                        </span>
                        <span className="badge badge-outline">
                          {target.target_type}
                        </span>
                      </div>
                      {target.description && (
                        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.4 }}>
                          {target.description}
                        </p>
                      )}
                      <div style={{ display: 'flex', gap: 20, marginTop: 10, fontSize: '0.84rem', color: 'var(--text-muted)' }}>
                        <span>
                          Compose Project: <code className="code-badge">{target.compose_project}</code>
                        </span>
                        <span>
                          Validated:{' '}
                          {target.last_validated_at
                            ? new Date(target.last_validated_at).toLocaleString()
                            : 'Never validated'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleValidate(target.id)}
                      disabled={isValidating || isDeleting}
                      title="Run live Docker inspection to validate containers and labels"
                    >
                      <RefreshCw size={15} className={isValidating ? 'loading-spinner' : ''} />
                      <span>{isValidating ? 'Validating...' : 'Validate Target'}</span>
                    </button>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => handleDelete(target)}
                      disabled={isValidating || isDeleting}
                      title="Unregister target environment"
                    >
                      <Trash2 size={15} />
                      <span>{isDeleting ? 'Deleting...' : 'Delete'}</span>
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => toggleExpand(target.id)}
                      title="Toggle discovered services breakdown"
                    >
                      {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    </button>
                  </div>
                </div>

                {/* Allowed services list */}
                <div style={{ marginTop: 20, paddingTop: 18, borderTop: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 10, letterSpacing: '0.06em' }}>
                    AUTHORIZED SERVICE ALLOWLIST:
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {target.allowed_services && target.allowed_services.length > 0 ? (
                      target.allowed_services.map((svc) => (
                        <span
                          key={svc}
                          style={{
                            fontSize: '0.84rem',
                            padding: '5px 12px',
                            borderRadius: '6px',
                            background: 'rgba(30, 41, 59, 0.75)',
                            border: '1px solid var(--border-color)',
                            color: '#e2e8f0',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {svc}
                        </span>
                      ))
                    ) : (
                      <span style={{ color: '#fb7185', fontSize: '0.84rem' }}>
                        No services in allowlist. Experiments cannot be created.
                      </span>
                    )}
                  </div>
                </div>

                {/* Expanded Discovered Services breakdown */}
                {isExpanded && (
                  <div
                    style={{
                      marginTop: 20,
                      padding: 22,
                      background: 'rgba(15, 23, 42, 0.65)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-color)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                      <h5 style={{ fontSize: '0.98rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Layers size={18} style={{ color: 'var(--accent-cyan)' }} />
                        Live Discovered Services ({discoveredCount})
                      </h5>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        Live container state from Docker daemon
                      </span>
                    </div>

                    {discoveredCount === 0 ? (
                      <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)' }}>
                        No live services discovered yet. Click "Validate Target" above to perform live Docker inspection.
                      </p>
                    ) : (
                      <div className="table-responsive">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Service Name</th>
                              <th>Allowlist Status</th>
                              <th>Opt-In Label</th>
                              <th>Container ID</th>
                              <th>Container Name</th>
                              <th>Docker Health</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(discovered).map(([svcName, svcInfo]) => {
                              const primary = svcInfo.primary_container || {};
                              return (
                                <tr key={svcName}>
                                  <td><strong style={{ color: '#f8fafc' }}>{svcName}</strong></td>
                                  <td>
                                    {svcInfo.is_allowed ? (
                                      <span className="badge badge-valid">Allowed</span>
                                    ) : (
                                      <span className="badge badge-failed">Disallowed</span>
                                    )}
                                  </td>
                                  <td>
                                    {svcInfo.opt_in ? (
                                      <span className="badge badge-valid">Present</span>
                                    ) : (
                                      <span className="badge badge-failed">Missing</span>
                                    )}
                                  </td>
                                  <td>
                                    <code className="code-badge">
                                      {primary.container_short_id || (primary.container_id ? primary.container_id.substring(0, 12) : '—')}
                                    </code>
                                  </td>
                                  <td>{primary.container_name || '—'}</td>
                                  <td>
                                    <span className={`badge badge-${primary.health || 'unvalidated'}`}>
                                      {primary.health || 'none'}
                                    </span>
                                  </td>
                                  <td>
                                    <span className={`badge badge-${primary.status === 'running' ? 'healthy' : 'failed'}`}>
                                      {primary.status || 'unknown'}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Register Modal */}
      {showRegisterModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.78)',
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
              maxWidth: 640,
              backgroundColor: '#101626',
              boxShadow: 'var(--shadow-lg)',
              border: '1px solid var(--border-accent)',
            }}
          >
            <div className="card-header">
              <h3 className="card-title">
                <Plus size={20} style={{ color: 'var(--accent-primary)' }} />
                Register Target Environment
              </h3>
              <button className="btn-icon" onClick={() => setShowRegisterModal(false)}><X size={18} /></button>
            </div>

            {formError && (
              <div className="alert alert-danger" style={{ marginBottom: 20 }}>
                <AlertTriangle size={20} style={{ flexShrink: 0 }} />
                <span>{formError}</span>
              </div>
            )}

            <form onSubmit={handleRegisterSubmit}>
              <div className="form-group">
                <label className="form-label">Target Name *</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. faultlab-demo-app"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
                <span className="form-hint">Unique identifier for this target environment</span>
              </div>

              <div className="form-group">
                <label className="form-label">Docker Compose Project Name *</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="faultlab"
                  value={formData.compose_project}
                  onChange={(e) => setFormData({ ...formData, compose_project: e.target.value })}
                  required
                />
                <span className="form-hint">Must match com.docker.compose.project label on target containers</span>
              </div>

              <div className="form-group">
                <label className="form-label">Authorized Services Allowlist (comma separated) *</label>
                <textarea
                  className="form-textarea"
                  value={formData.allowed_services_input}
                  onChange={(e) => setFormData({ ...formData, allowed_services_input: e.target.value })}
                  rows={3}
                  required
                />
                <span className="form-hint">
                  Only explicitly listed services can be selected for experiments. Protected services (postgres, platform, frontend) are forbidden.
                </span>
              </div>

              <div className="form-group">
                <label className="form-label">Description (Optional)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Microservice e-commerce target application"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 14, marginTop: 28 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowRegisterModal(false)}
                  disabled={formSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={formSubmitting}
                >
                  {formSubmitting ? 'Registering...' : 'Register Target'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
