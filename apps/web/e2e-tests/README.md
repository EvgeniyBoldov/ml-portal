# E2E Suite Rebuild

Legacy e2e scenarios were removed and this folder now starts from a clean baseline.

Rules:
- Put only Playwright tests with `*.e2e.ts` suffix here.
- Keep smoke scenarios deterministic and short.
- Grow coverage by business-critical flows first:
  1. auth login
  2. chat send/receive
  3. document upload/index/search

Run:
- `npm run test:e2e`
- `npm run test:e2e:ui`
