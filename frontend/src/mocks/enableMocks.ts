import { mockFetch } from './mockFetch'

function toUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.toString()
  // Request
  try {
    // @ts-ignore
    return input.url || String(input)
  } catch {
    // @ts-ignore
    return String(input)
  }
}

// Replace global fetch to ensure ALL calls go through mocks in dev.
if (typeof window !== 'undefined') {
  const original = window.fetch.bind(window)
  // @ts-ignore
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = toUrl(input)
    // Allow opting-out: if request has header 'X-Bypass-Mock', go to real fetch
    if (init && (init as any).headers && (init as any).headers['X-Bypass-Mock']) {
      return original(input, init)
    }
    return mockFetch(url, init as any)
  }
}
