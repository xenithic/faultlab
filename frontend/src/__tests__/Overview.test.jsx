import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import Overview from '../pages/Overview';

describe('Overview Component', () => {
  it('renders loading state when initial data is being fetched', () => {
    render(<Overview experiments={[]} targets={[]} loading={true} error={null} />);
    expect(screen.getByText(/Connecting to FaultLab Platform/i)).toBeInTheDocument();
  });

  it('renders backend error banner when API is unreachable', () => {
    render(
      <Overview
        experiments={[]}
        targets={[]}
        loading={false}
        error="Network error connecting to platform API at /api/health"
      />
    );
    expect(screen.getByText(/Platform Backend Unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/Network error connecting/i)).toBeInTheDocument();
  });

  it('calculates and displays real experiment status counts correctly', () => {
    const mockExperiments = [
      { id: 1, target_service: 'order-service', status: 'completed', fault_type: 'service_failure', recovery_time_seconds: 2.5 },
      { id: 2, target_service: 'inventory-service', status: 'failed', fault_type: 'service_pause' },
      { id: 3, target_service: 'product-service', status: 'running', fault_type: 'service_failure' },
      { id: 4, target_service: 'payment-service', status: 'cancelled', fault_type: 'service_failure' },
      { id: 5, target_service: 'order-service', status: 'pending', fault_type: 'service_pause' },
    ];
    const mockTargets = [
      { id: 1, name: 'demo-app', compose_project: 'faultlab', validation_status: 'valid', allowed_services: ['order-service'] },
    ];

    render(
      <Overview
        experiments={mockExperiments}
        targets={mockTargets}
        loading={false}
        error={null}
        onSelectExperiment={vi.fn()}
        onNavigate={vi.fn()}
      />
    );

    // Total should be 5
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText(/Recorded resilience test runs in database/i)).toBeInTheDocument();
    expect(screen.getByText('demo-app')).toBeInTheDocument();
  });
});
