import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

const STATUS_COLORS = {
  completed: '#10b981', // emerald
  failed: '#f43f5e',    // rose
  cancelled: '#64748b', // slate
  running: '#8b5cf6',   // purple
  pending: '#f59e0b',   // amber
};

export default function OutcomeChart({ experiments = [] }) {
  const counts = experiments.reduce((acc, exp) => {
    const status = exp.status || 'unknown';
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});

  const total = experiments.length;

  const data = Object.entries(counts).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    statusKey: name,
    value,
    percentage: total > 0 ? ((value / total) * 100).toFixed(0) : 0,
  }));

  if (data.length === 0) {
    return (
      <div className="empty-state" style={{ padding: '40px 24px' }}>
        <p style={{ fontSize: '0.95rem' }}>No experiment records available yet to chart outcomes.</p>
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: 340, minHeight: 340 }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="46%"
            innerRadius={70}
            outerRadius={115}
            paddingAngle={5}
            dataKey="value"
          >
            {data.map((entry) => (
              <Cell
                key={`cell-${entry.statusKey}`}
                fill={STATUS_COLORS[entry.statusKey] || '#94a3b8'}
                stroke="#090d16"
                strokeWidth={3}
              />
            ))}
          </Pie>
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
            formatter={(value, name, item) => [
              `${value} (${item.payload.percentage}%)`,
              item.payload.name,
            ]}
          />
          <Legend
            verticalAlign="bottom"
            height={44}
            formatter={(value, entry) => (
              <span style={{ color: '#cbd5e1', fontSize: '0.88rem', marginRight: 16 }}>
                {value}: <strong style={{ color: '#f8fafc' }}>{entry.payload.value}</strong>
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
