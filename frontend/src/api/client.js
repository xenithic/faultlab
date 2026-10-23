/**
 * FaultLab Platform API Client
 * Connects React Frontend to the Flask platform backend.
 * Uses environment variable VITE_API_BASE_URL when present, or defaults to '/api'.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

class ApiError extends Error {
  constructor(message, status, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const defaultHeaders = {
    'Accept': 'application/json',
  };

  if (options.body && !(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);
    const contentType = response.headers.get('content-type');
    let data = null;

    if (contentType && contentType.includes('application/json')) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    if (!response.ok) {
      const errorMsg = (data && data.message) || (data && data.error) || response.statusText || 'Request failed';
      throw new ApiError(errorMsg, response.status, data);
    }

    return data;
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    // Network or parser error
    throw new ApiError(
      `Network error connecting to platform API at ${url}: ${err.message}`,
      0,
      null
    );
  }
}

export const api = {
  // Health
  getHealth: () => request('/health'),

  // Targets
  getTargets: () => request('/targets'),
  getTarget: (id) => request(`/targets/${id}`),
  registerTarget: (payload) =>
    request('/targets', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  validateTarget: (id) =>
    request(`/targets/${id}/validate`, {
      method: 'POST',
    }),
  deleteTarget: (id) =>
    request(`/targets/${id}`, {
      method: 'DELETE',
    }),

  // Experiments
  getExperiments: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.target_id) params.append('target_id', filters.target_id);
    if (filters.status) params.append('status', filters.status);
    if (filters.fault_type) params.append('fault_type', filters.fault_type);
    const query = params.toString() ? `?${params.toString()}` : '';
    return request(`/experiments${query}`);
  },
  getExperiment: (id) => request(`/experiments/${id}`),
  createExperiment: (payload) =>
    request('/experiments', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  startExperiment: (id, sync = false) =>
    request(`/experiments/${id}/start${sync ? '?sync=true' : ''}`, {
      method: 'POST',
    }),
  cancelExperiment: (id) =>
    request(`/experiments/${id}/cancel`, {
      method: 'POST',
    }),
};

export { ApiError };
