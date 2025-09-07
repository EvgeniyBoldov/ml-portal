// Auto-enable mocks when VITE_USE_MOCKS === 'true'
// No top-level await to keep TS/Vite happy in all setups.
if (import.meta.env.VITE_USE_MOCKS === 'true') {
  import('./mockFetch');
}
export {};
