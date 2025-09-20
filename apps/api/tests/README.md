This is a complete replacement tests directory tuned for your current backend layout.

- Tests are intentionally **soft** on auth-required endpoints: in your stack, many routes are protected. We assert presence and stable error codes rather than success.
- The suite validates middleware wiring (security headers, idempotency) and that API prefixes are consistent.

If you want stricter auth-enabled tests, provide a test JWT or a mock user fixture, and I can harden the assertions.
