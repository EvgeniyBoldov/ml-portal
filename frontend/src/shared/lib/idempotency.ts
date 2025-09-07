export function idempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return (crypto as any).randomUUID();
  return "idem_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}
