import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ExperimentDetail from '../pages/ExperimentDetail';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    getExperiment: vi.fn(),
    startExperiment: vi.fn(),
    cancelExperiment: vi.fn(),
  },
}));

describe('ExperimentDetail Component', () => {
  const mockExp = {
    id: 42,
    target_id: 1,
    target_service: 'order-service',
    target_container_id: 'container-sha256-42',
    fault_type: 'service_failure',
    status: 'completed',
    parameters: { duration_seconds: 10, stop_timeout: 5 },
    recovery_time_seconds: 1.45,
    baseline_metrics: {
      timestamp: '2026-10-21T02:00:00Z',
      container_state: { status: 'running', health: 'healthy' },
      container_stats: { available: true, cpu_percent: 1.8, memory_usage_bytes: 48000000, memory_limit_bytes: 8000000000, memory_percent: 0.6 },
      http_health: { available: true, latency_ms: 12.5, status_code: 200, is_healthy: true },
    },
    result_metrics: {
      before: {
        timestamp: '2026-10-21T02:00:00Z',
        container_state: { status: 'running', health: 'healthy' },
        container_stats: { available: true, cpu_percent: 1.8, memory_usage_bytes: 48000000, memory_limit_bytes: 8000000000, memory_percent: 0.6 },
        http_health: { available: true, latency_ms: 12.5, status_code: 200 },
      },
      during: {
        timestamp: '2026-10-21T02:00:01Z',
        container_state: { status: 'exited', health: 'none' },
        http_health: { available: false, reason: 'Connection refused' },
      },
      after: {
        timestamp: '2026-10-21T02:00:11Z',
        container_state: { status: 'running', health: 'healthy' },
        http_health: { available: true, latency_ms: 13.8, status_code: 200 },
      },
      recovery_verification: {
        status: 'verified',
        verified: true,
        recovery_time_seconds: 1.45,
        evidence: 'Container status returned to running and healthcheck reported healthy in 1.45s.',
      },
      cleanup: {
        success: true,
        error: null,
      },
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders detailed telemetry, before/during/after observations, and recovery evidence', async () => {
    api.getExperiment.mockResolvedValueOnce(mockExp);

    render(
      <ExperimentDetail
        experimentId={42}
        onBack={vi.fn()}
        onRefreshParent={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Experiment #42/i)).toBeInTheDocument();
    });

    // Check bound container ID
    expect(screen.getByText('container-sha256')).toBeInTheDocument();

    // Check Phase Observation headers
    expect(screen.getByText(/Phase 1: Before Fault/i)).toBeInTheDocument();
    expect(screen.getByText(/Phase 2: During Fault/i)).toBeInTheDocument();
    expect(screen.getByText(/Phase 3: After Recovery/i)).toBeInTheDocument();

    // Check evidence
    expect(screen.getByText(/Container status returned to running and healthcheck reported healthy in 1.45s/i)).toBeInTheDocument();

    // Check recovery measurement
    expect(screen.getByText('1.45 seconds')).toBeInTheDocument();
  });
});
