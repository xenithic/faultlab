import React from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid } from 'recharts';
import { Cpu, HardDrive, Activity, AlertCircle } from 'lucide-react';

export default function PhaseMetricsChart({ resultMetrics = {}, baselineMetrics = {} }) {
  const before = resultMetrics?.before || baselineMetrics || {};
  const during = resultMetrics?.during || {};
  const after = resultMetrics?.after || {};

  // Extract HTTP Latency for Before, During, After
  const getLatency = (phaseObj) => {
    if (phaseObj?.http_health?.available && typeof phaseObj.http_health.latency_ms === 'number') {
      return phaseObj.http_health.latency_ms;
    }
    return null; // explicitly distinguish unavailable / failed probe from 0 ms
  };

  const beforeLat = getLatency(before);
  const duringLat = getLatency(during);
  const afterLat = getLatency(after);

  const hasAnyLatency = beforeLat !== null || duringLat !== null || afterLat !== null;

  const latencyData = [
    {
      phase: 'Before Fault (Baseline)',
      shortPhase: 'Before Fault',
      latency: beforeLat !== null ? beforeLat : 0,
      displayVal: beforeLat !== null ? `${beforeLat} ms` : 'Unavailable',
      isAvailable: beforeLat !== null,
      fill: '#38bdf8',
    },
    {
      phase: 'During Fault (Impact)',
      shortPhase: 'During Fault',
      latency: duringLat !== null ? duringLat : 0,
      displayVal: duringLat !== null ? `${duringLat} ms` : (during?.container_state?.status ? `Target ${during.container_state.status}` : 'Connection Refused / Down'),
      isAvailable: duringLat !== null,
      fill: '#f43f5e',
    },
    {
      phase: 'After Recovery (Outcome)',
      shortPhase: 'After Recovery',
      latency: afterLat !== null ? afterLat : 0,
      displayVal: afterLat !== null ? `${afterLat} ms` : 'Unavailable',
      isAvailable: afterLat !== null,
      fill: '#34d399',
    },
  ];

  // Extract CPU and Memory from container stats
  const stats = before?.container_stats;
  const cpuPercent = (stats?.available && typeof stats?.cpu_percent === 'number') ? stats.cpu_percent : null;
  const memUsageBytes = (stats?.available && typeof stats?.memory_usage_bytes === 'number') ? stats.memory_usage_bytes : null;
  const memUsageMb = memUsageBytes !== null ? (memUsageBytes / (1024 * 1024)).toFixed(1) : null;
  const memPercent = (stats?.available && typeof stats?.memory_percent === 'number') ? stats.memory_percent : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      {/* Latency Phase Chart */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <h4 style={{ fontSize: '1.05rem', color: 'var(--text-primary)', fontWeight: 700 }}>
              HTTP Probe Response Latency by Phase
            </h4>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginTop: 2 }}>
              Real measured round-trip time across injection lifecycle
            </p>
          </div>
          <span className="badge badge-outline">
            Snapshot Comparison
          </span>
        </div>

        {hasAnyLatency ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ width: '100%', height: 240, minHeight: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={latencyData} margin={{ top: 16, right: 24, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.08)" vertical={false} />
                  <XAxis dataKey="shortPhase" tick={{ fill: '#cbd5e1', fontSize: 13 }} />
                  <YAxis unit=" ms" tick={{ fill: '#cbd5e1', fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#172238',
                      borderColor: 'rgba(148, 163, 184, 0.25)',
                      borderRadius: '10px',
                      color: '#f8fafc',
                      fontSize: '0.92rem',
                      padding: '10px 14px',
                      boxShadow: '0 8px 24px rgba(0, 0, 0, 0.5)',
                    }}
                    formatter={(_, __, props) => [props.payload.displayVal, 'Measured Probe Latency']}
                    labelFormatter={(label) => `${label}`}
                  />
                  <Bar dataKey="latency" radius={[6, 6, 0, 0]} maxBarSize={64}>
                    {latencyData.map((entry, idx) => (
                      <Cell
                        key={`cell-${idx}`}
                        fill={entry.isAvailable ? entry.fill : '#334155'}
                        stroke={entry.isAvailable ? 'none' : '#64748b'}
                        strokeDasharray={entry.isAvailable ? '' : '4 4'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* 3 Value Cards below Chart */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
              {latencyData.map((d, i) => (
                <div
                  key={i}
                  style={{
                    padding: '14px 18px',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-color)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 4,
                  }}
                >
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {d.shortPhase}
                  </span>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, color: d.isAvailable ? '#f8fafc' : '#fb7185', fontFamily: 'var(--font-mono)' }}>
                    {d.displayVal}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="alert alert-warning" style={{ fontSize: '0.88rem' }}>
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <span>
              No HTTP probe latency data available for this experiment. The target service may not expose an HTTP health endpoint accessible to the platform network.
            </span>
          </div>
        )}
      </div>

      {/* Resource Utilization (Baseline Container Stats) */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <h4 style={{ fontSize: '1.05rem', color: 'var(--text-primary)', fontWeight: 700 }}>
              Container Resource Utilization
            </h4>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginTop: 2 }}>
              Pre-fault baseline snapshot collected via Docker daemon cgroup stats
            </p>
          </div>
          <span className="badge badge-outline">
            Baseline Snapshot
          </span>
        </div>

        {stats?.available ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
            <div className="metric-card" style={{ background: 'var(--bg-surface)', borderTop: '4px solid #38bdf8' }}>
              <div className="metric-label">
                <span>CPU Utilization</span>
                <Cpu size={18} style={{ color: '#38bdf8' }} />
              </div>
              <span className="metric-value" style={{ color: '#38bdf8' }}>
                {cpuPercent !== null ? `${cpuPercent}%` : 'N/A'}
              </span>
              <span className="metric-sub">
                Calculated via Docker delta across online CPU cores
              </span>
            </div>

            <div className="metric-card" style={{ background: 'var(--bg-surface)', borderTop: '4px solid #a78bfa' }}>
              <div className="metric-label">
                <span>Memory Usage</span>
                <HardDrive size={18} style={{ color: '#a78bfa' }} />
              </div>
              <span className="metric-value" style={{ color: '#a78bfa' }}>
                {memUsageMb !== null ? `${memUsageMb} MB` : 'N/A'}
              </span>
              <span className="metric-sub">
                {memPercent !== null ? `${memPercent}% of container memory limit` : 'No hard memory limit set'}
              </span>
            </div>
          </div>
        ) : (
          <div className="alert alert-info" style={{ fontSize: '0.88rem' }}>
            <Activity size={20} style={{ flexShrink: 0 }} />
            <span>
              Container resource stats unavailable for this experiment. {stats?.reason || 'Live container daemon stats were not accessible.'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
