import type { ResponseContract } from '@/shared/api/admin';

export interface ContractCriteriaBlockProps {
  contract?: ResponseContract | null;
  title?: string;
}

export function ContractCriteriaBlock({
  contract,
  title = 'Формат ответа (критерии)',
}: ContractCriteriaBlockProps) {
  if (!contract) {
    return (
      <div style={{ padding: '16px', border: '1px solid var(--border-color)', borderRadius: 8 }}>
        <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 8 }}>{title}</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Контракт не задан</div>
      </div>
    );
  }

  const format = contract.format;
  const isLocked = contract.format_locked !== false;

  // Extract criteria and forbidden from plain_text contract
  const plainText = contract.plain_text || {};
  const criteria = (plainText.criteria as string[]) || [];
  const forbidden = (plainText.forbidden as string[]) || [];

  // Format switcher options
  const formatOptions = [
    { value: 'json', label: 'JSON' },
    { value: 'markdown', label: 'Markdown' },
    { value: 'plain_text', label: 'Plain text' },
  ];

  return (
    <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, overflow: 'hidden' }}>
      {/* Header with format switcher */}
      <div
        style={{
          padding: '12px 16px',
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 500 }}>{title}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>формат:</span>
          <div style={{ display: 'flex', gap: 4 }}>
            {formatOptions.map((opt) => (
              <button
                key={opt.value}
                disabled={isLocked}
                style={{
                  padding: '4px 10px',
                  fontSize: 12,
                  border: '1px solid var(--border-color)',
                  borderRadius: 4,
                  background: format === opt.value ? 'var(--primary)' : 'var(--bg-primary)',
                  color: format === opt.value ? 'white' : 'var(--text-primary)',
                  cursor: isLocked ? 'not-allowed' : 'pointer',
                  opacity: isLocked ? 0.6 : 1,
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <span
            style={{
              fontSize: 11,
              color: 'var(--text-secondary)',
              marginLeft: 8,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <span>🔒</span>
            <span>backend</span>
          </span>
        </div>
      </div>

      {/* Criteria and Forbidden lists */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
        {/* Required (criteria) */}
        <div style={{ borderRight: '1px solid var(--border-color)', padding: '16px' }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              color: 'var(--success)',
              marginBottom: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span style={{ fontSize: 14 }}>✓</span>
            <span>Должно быть</span>
          </div>

          {criteria.length > 0 ? (
            <ul
              style={{
                margin: 0,
                padding: 0,
                listStyle: 'none',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              {criteria.map((item, idx) => (
                <li
                  key={idx}
                  style={{
                    fontSize: 13,
                    lineHeight: 1.5,
                    color: 'var(--text-primary)',
                    padding: '8px 12px',
                    background: 'var(--bg-secondary)',
                    borderRadius: 6,
                    borderLeft: '3px solid var(--success)',
                  }}
                >
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
              Нет критериев
            </div>
          )}
        </div>

        {/* Forbidden */}
        <div style={{ padding: '16px' }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              color: 'var(--danger)',
              marginBottom: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span style={{ fontSize: 14 }}>✗</span>
            <span>Запрещено</span>
          </div>

          {forbidden.length > 0 ? (
            <ul
              style={{
                margin: 0,
                padding: 0,
                listStyle: 'none',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              {forbidden.map((item, idx) => (
                <li
                  key={idx}
                  style={{
                    fontSize: 13,
                    lineHeight: 1.5,
                    color: 'var(--text-primary)',
                    padding: '8px 12px',
                    background: 'var(--bg-secondary)',
                    borderRadius: 6,
                    borderLeft: '3px solid var(--danger)',
                  }}
                >
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
              Нет ограничений
            </div>
          )}
        </div>
      </div>

      {/* Failure policy */}
      {contract.failure_policy && (
        <div
          style={{
            padding: '10px 16px',
            background: 'var(--bg-tertiary)',
            borderTop: '1px solid var(--border-color)',
            fontSize: 11,
            color: 'var(--text-secondary)',
          }}
        >
          Политика при ошибке:{' '}
          <strong>{contract.failure_policy.on_invalid}</strong>
        </div>
      )}
    </div>
  );
}
