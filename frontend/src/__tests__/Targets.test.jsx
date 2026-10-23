import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Targets from '../pages/Targets';

describe('Targets Component', () => {
  const mockTargets = [
    {
      id: 1,
      name: 'faultlab-demo-app',
      compose_project: 'faultlab',
      description: 'Demo application target environment',
      target_type: 'docker_compose',
      validation_status: 'valid',
      last_validated_at: '2026-10-21T00:00:00Z',
      allowed_services: ['product-service', 'order-service', 'inventory-service'],
      discovered_services: {
        'order-service': {
          is_allowed: true,
          opt_in: true,
          primary_container: {
            container_id: 'abc123def456',
            container_name: 'faultlab-order-service-1',
            status: 'running',
            health: 'healthy',
          },
        },
      },
    },
  ];

  it('renders target environments list with validation status and allowlist', () => {
    render(
      <Targets
        targets={mockTargets}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
      />
    );

    expect(screen.getByText('faultlab-demo-app')).toBeInTheDocument();
    expect(screen.getByText('valid')).toBeInTheDocument();
    expect(screen.getByText('order-service')).toBeInTheDocument();
    expect(screen.getByText('product-service')).toBeInTheDocument();
    expect(screen.getByText('inventory-service')).toBeInTheDocument();
  });

  it('blocks registration if protected service names are entered', async () => {
    render(
      <Targets
        targets={mockTargets}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
      />
    );

    // Open Register modal
    fireEvent.click(screen.getByRole('button', { name: /Register Target/i }));

    // Fill form with protected service postgres
    const nameInput = screen.getByPlaceholderText(/e\.g\. faultlab-demo-app/i);
    fireEvent.change(nameInput, { target: { value: 'forbidden-app' } });

    const servicesTextarea = screen.getByDisplayValue(/product-service, order-service/i);
    fireEvent.change(servicesTextarea, { target: { value: 'order-service, postgres' } });

    // Click submit in modal
    const registerButtons = screen.getAllByRole('button', { name: /Register Target/i });
    fireEvent.click(registerButtons[registerButtons.length - 1]);

    expect(
      screen.getByText(/Protected platform services cannot be registered as fault targets: postgres/i)
    ).toBeInTheDocument();
  });
});
