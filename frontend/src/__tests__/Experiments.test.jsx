import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Experiments from '../pages/Experiments';

describe('Experiments Component', () => {
  const mockTargets = [
    {
      id: 1,
      name: 'demo-app',
      compose_project: 'faultlab',
      validation_status: 'valid',
      allowed_services: ['order-service', 'inventory-service'],
    },
  ];

  const mockExperiments = [
    {
      id: 10,
      target_id: 1,
      target_service: 'order-service',
      fault_type: 'service_failure',
      status: 'pending',
      parameters: { duration_seconds: 15, stop_timeout: 5 },
      created_at: '2026-10-21T01:00:00Z',
    },
    {
      id: 11,
      target_id: 1,
      target_service: 'inventory-service',
      fault_type: 'service_pause',
      status: 'running',
      parameters: { duration_seconds: 20 },
      created_at: '2026-10-21T01:05:00Z',
    },
  ];

  it('renders experiment table with status badges and action buttons', () => {
    render(
      <Experiments
        experiments={mockExperiments}
        targets={mockTargets}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        onSelectExperiment={vi.fn()}
        onNavigate={vi.fn()}
      />
    );

    expect(screen.getByText('#10')).toBeInTheDocument();
    expect(screen.getByText('#11')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();

    // Start button should be visible for pending experiment #10
    expect(screen.getByRole('button', { name: /Start/i })).toBeInTheDocument();
    // Cancel button should be visible for running experiment #11
    expect(screen.getAllByRole('button', { name: /Cancel/i }).length).toBeGreaterThanOrEqual(1);
  });

  it('filters experiments by status', () => {
    render(
      <Experiments
        experiments={mockExperiments}
        targets={mockTargets}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        onSelectExperiment={vi.fn()}
        onNavigate={vi.fn()}
      />
    );

    const statusSelect = screen.getByDisplayValue(/All Statuses/i);
    fireEvent.change(statusSelect, { target: { value: 'running' } });

    // #11 running is visible
    expect(screen.getByText('#11')).toBeInTheDocument();
    // #10 pending is filtered out
    expect(screen.queryByText('#10')).not.toBeInTheDocument();
  });

  it('enables all 5 fault types in the creation modal', () => {
    render(
      <Experiments
        experiments={mockExperiments}
        targets={mockTargets}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        onSelectExperiment={vi.fn()}
        onNavigate={vi.fn()}
      />
    );

    // Open creation modal
    fireEvent.click(screen.getByRole('button', { name: /New Experiment/i }));

    expect(screen.getAllByText(/Service Failure/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Service Pause/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Latency Injection/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/CPU \/ Memory Stress/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/HTTP Error Injection/i).length).toBeGreaterThanOrEqual(1);

    // All 5 should have 'Supported' badge
    const supportedBadges = screen.getAllByText('Supported');
    expect(supportedBadges.length).toBe(5);
  });

  it('renders dynamic parameter inputs when selecting latency fault', () => {
    render(
      <Experiments
        experiments={mockExperiments}
        targets={mockTargets}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        onSelectExperiment={vi.fn()}
        onNavigate={vi.fn()}
      />
    );

    // Open creation modal
    fireEvent.click(screen.getByRole('button', { name: /New Experiment/i }));

    // Select latency
    const latencyRadio = screen.getByLabelText(/Latency Injection/i);
    fireEvent.click(latencyRadio);

    expect(screen.getByText(/Latency \(ms\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Jitter \(ms\)/i)).toBeInTheDocument();
  });
});
