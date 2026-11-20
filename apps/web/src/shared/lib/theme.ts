/**
 * Theme utilities
 * Manage light/dark theme switching
 */

type Theme = 'light' | 'dark';

const THEME_KEY = 'app-theme';

/**
 * Get current theme from localStorage or system preference
 */
function getTheme(): Theme {
  if (typeof window === 'undefined') return 'light';

  const stored = localStorage.getItem(THEME_KEY) as Theme | null;
  if (stored === 'light' || stored === 'dark') return stored;

  // Check system preference
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'dark' : 'light';
}

/**
 * Set theme and persist to localStorage
 */
function setTheme(theme: Theme): void {
  if (typeof window === 'undefined') return;

  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
}

/**
 * Toggle between light and dark theme
 */

/**
 * Initialize theme on app load
 */
export function initTheme(): void {
  const theme = getTheme();
  setTheme(theme);
}
