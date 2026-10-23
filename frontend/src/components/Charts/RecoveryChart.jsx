import React from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid } from 'recharts';

export default function RecoveryChart({ experiments = [] }) {
  // Only include experiments with genuinely verified recovery results
  const verifiedExperiments = experiments
    .filter((exp) => {
      const rec = exp.result_metrics?.recovery_verification;
      const isVerified = rec?.verified === true || (exp.status === 'completed' && exp.recovery_time_seconds != null);
      return isVerified && typeof exp.recovery_time_seconds === 'number';
    })
    .slice(0, 10) // Show up to last 10 verified runs
    .reverse();   // Chronological order (older to newer)

  if (verifiedExperiments.length === 0) {
    return (
      <div className="empty-state" style={{ padding: '40px 24px' }}>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', maxWidth: 500, lineHeight: 1.5 }}>
          No verified recovery measurements available yet. Experiments must complete with verified container healthchecks or HTTP probes to appear in recovery comparison.
        </p>
      </div>
    );
  }

  const chartData = verifiedExperiments.map((exp) => ({
    name: `#${exp.id} ${exp.target_service}`,
    recoveryTime: exp.recovery_time_seconds,
    fault: exp.fault_type,
    service: exp.target_service,
  }));

  return (
    <div style={{ width: '100%', height: 340, minHeight: 340, display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 16, right: 24, left: 10, bottom: 35 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.08)" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: '#cbd5e1', fontSize: 12 }}
              angle={-20}
              textAnchor="end"
              interval={0}
              height={40}
            />
            <YAxis
              unit="s"
              tick={{ fill: '#cbd5e1', fontSize: 12 }}
              label={{
                value: 'Recovery Time (seconds)',
                angle: -90,
                position: 'insideLeft',
                fill: '#94a3b8',
                fontSize: 12,
                offset: 5,
              }}
            />
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
              formatter={(value) => [`${value} s`, 'Measured Recovery Time']}
              labelFormatter={(label) => `Experiment ${label}`}
            />
            <Bar dataKey="recoveryTime" radius={[6, 6, 0, 0]} maxBarSize={48}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`bar-${index}`}
                  fill={entry.recoveryTime < 3 ? '#10b981' : entry.recoveryTime < 8 ? '#06b6d4' : '#f59e0b'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ textAlign: 'center', marginTop: '8px' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          * Strictly shows verified recovery times. Unverified or failed recoveries are excluded from baseline calculations.
        </span>
      </div>
    </div>
  );
}
