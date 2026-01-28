---
trigger: always_on
---

You are refactoring a React 18 + TypeScript + Vite app with React Router, TanStack Query, Zustand, CSS-modules, SSE. Follow these NON-NEGOTIABLE rules:

LANGUAGE & CODE REUSE
- Use ONLY Russian or English in UI text, comments, and variable names. NO Ukrainian or other languages.
- Maximize component reuse. Extract common patterns into shared components. Never duplicate code.
- All components must be theme-aware and styled via CSS modules (no inline styles except dynamic values).

ARCHITECTURE
- Use domain-first folders:
  src/app (providers, router, layouts), src/domains/* (pages, components, hooks, types), src/shared/{api,ui,lib,config,hooks,types}.
- Keep a single HTTP client in src/shared/api/client.ts (fetch + refresh + idempotency + timeout). Delete duplicates.
- Server state: TanStack Query only. Local UI state: Zustand only. Never store server data in Zustand.
- Create src/shared/api/keys.ts with a query-key factory. All queries/mutations must use it.
- SSE updates must invalidate or update queries via QueryClient, never mutate global state directly.

ROUTING & PROVIDERS
- One top-level <AppProviders> with: Theme (optional), QueryClientProvider, Auth/RBAC Provider, Toaster, SSEProvider, ErrorBoundary.
- Two route trees: /gpt (MainLayout), /admin (AdminLayout behind AdminGuard). Lazy-load admin.

AUTH & RBAC
- Access token in memory; Refresh via httpOnly cookie (handled by backend). No tokens in localStorage.
- Implement useAuth()/useRBAC() returning hasRole(role), hasScope(scope). Replace any isAdmin=true.

UI & STYLES
- Use components from src/shared/ui. No inline styled-components, no Tailwind.
- Choose the right primitive:
  - DropdownMenu → pure actions list
  - Popover → small interactive card (no scroll; short forms/filters)
  - Modal/Drawer → anything large (graphs, long forms, tabs)
- All interactive components must be keyboard-accessible (Esc to close, focus return, aria-*).
- CSS-modules naming: .module.css, classes in dash-case; no global CSS leaks.

API CONTRACTS
- Align endpoints/types with backend. No client-side “fake detail” via list filtering.
- All API modules in src/shared/api: auth.ts, chats.ts, rag.ts, admin.ts, etc. Barrel export from src/shared/api/index.ts.
- Errors → map to typed ApiError; surface via toast and field errors.
- Use idempotency key for POST/PUT as helper.

QUERY POLICY
- Default query options: staleTime=30_000, gcTime=5*60_000, retry=1. Mutations: optimistic update only when trivial and reversible.
- Always invalidate via factory keys. Never hardcode arrays like ['rag','list'] inline.

FILES & NAMING
- Filenames: PascalCase for components, camelCase for libs/hooks, kebab-case for CSS modules.
- Index files only for barrel exports; never hide logic in index.tsx.
- One component per file; keep component length < 250 lines; extract subviews/hooks.
- Remove dead code and legacy configs: vite.config.js, empty .storybook/* unless set up.

TESTS
- Unit: Vitest + RTL + MSW for api/client, SSE reducer/applyEvents, key hooks.
- E2E: Playwright smoke: login → upload → ingest → status ready → search → logout.
- Write tests for bugs before fixing them. Keep tests colocated next to code (*.{test,spec}.tsx?).

PERFORMANCE
- Manual chunks: vendor (react/react-dom), router; no custom UI chunk unless used. Preload critical layout chunks.
- Avoid popover-in-popover. Avoid measuring DOM in render; use ResizeObserver/effect.

DX
- Enforce ESLint + Prettier on pre-commit. Type-check in CI. Strict TS.
- All new public components in shared/ui must have minimal Storybook or MDX usage docs.

NON-COMPLIANT CODE WILL BE REJECTED.
