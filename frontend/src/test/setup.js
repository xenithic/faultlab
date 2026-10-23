import '@testing-library/jest-dom';

// Polyfill ResizeObserver for Recharts in JSDOM environment
class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

window.ResizeObserver = ResizeObserver;
