export function hashEntityIds(ids: string[]): string {
  const sorted = [...ids].sort();
  let hash = 0;
  for (let i = 0; i < sorted.length; i++) {
    const str = sorted[i];
    for (let j = 0; j < str.length; j++) {
      const char = str.charCodeAt(j);
      hash = (hash << 5) - hash + char;
      hash = hash & hash; // Convert to 32bit integer
    }
  }
  return `ent_${Math.abs(hash).toString(36)}`;
}
