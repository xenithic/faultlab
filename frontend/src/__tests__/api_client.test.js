import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api, ApiError } from '../api/client';

describe('FaultLab API Client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches platform health status successfully', async () => {
    const mockHealth = { service: 'faultlab-platform', status: 'healthy', version: '0.1.0' };
    global.fetch.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => mockHealth,
    });

    const result = await api.getHealth();
    expect(result).toEqual(mockHealth);
    expect(global.fetch).toHaveBeenCalledWith('/api/health', expect.objectContaining({
      headers: expect.objectContaining({ Accept: 'application/json' }),
    }));
  });

  it('registers target with JSON payload', async () => {
    const mockTarget = { id: 1, name: 'test-app', compose_project: 'faultlab', allowed_services: ['order-service'] };
    global.fetch.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => mockTarget,
    });

    const result = await api.registerTarget({
      name: 'test-app',
      compose_project: 'faultlab',
      allowed_services: ['order-service'],
    });

    expect(result).toEqual(mockTarget);
    expect(global.fetch).toHaveBeenCalledWith('/api/targets', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        name: 'test-app',
        compose_project: 'faultlab',
        allowed_services: ['order-service'],
      }),
    }));
  });

  it('throws ApiError with server message on HTTP 400 Bad Request', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      headers: { get: () => 'application/json' },
      json: async () => ({ error: 'Bad Request', message: 'Duration must be between 1 and 300' }),
    });

    await expect(api.createExperiment({ target_id: 1 })).rejects.toThrow(
      'Duration must be between 1 and 300'
    );
  });

  it('throws ApiError on network disconnect', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Failed to fetch'));

    await expect(api.getTargets()).rejects.toThrow(/Network error connecting/);
  });
});
