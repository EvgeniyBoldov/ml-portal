import { describe, expect, it } from 'vitest';
import { accessRows, normalizeLimits } from './TraceDataViews';

describe('trace inspector data views', () => {
  it('normalizes both runtime budget snapshot formats', () => {
    expect(normalizeLimits({
      snapshot: { tool_calls: { used: 3, limit: 5, remaining: 2 } },
    })).toMatchObject([{ key: 'tool_calls', used: 3, limit: 5, remaining: 2 }]);

    expect(normalizeLimits({
      own: { tokens_total: 120 }, limits: { tokens_total: 1000 },
    })).toMatchObject([{ key: 'tokens_total', used: 120, limit: 1000, remaining: 880 }]);
  });

  it('projects effective RBAC decisions and capability denials', () => {
    expect(accessRows({
      allowed: ['viewer'],
      denied_by_rbac: ['writer'],
      collection_filter: {
        allowed: ['knowledge'],
        denied_by_rbac: ['finance'],
        denied_by_capability: ['archive'],
      },
    })).toEqual([
      { kind: 'Агент', name: 'viewer', allowed: true, reason: 'Разрешён эффективной политикой' },
      { kind: 'Агент', name: 'writer', allowed: false, reason: 'Запрещён RBAC' },
      { kind: 'Коллекция', name: 'archive', allowed: false, reason: 'Не входит в capability агента' },
      { kind: 'Коллекция', name: 'finance', allowed: false, reason: 'Запрещена RBAC' },
      { kind: 'Коллекция', name: 'knowledge', allowed: true, reason: 'Доступна выбранному агенту' },
    ]);
  });
});
