import type { ResponseContract } from '@/shared/api/admin';

export interface ContractFieldsBlockProps {
  contract?: ResponseContract | null;
  rulesText?: string;
  title?: string;
}

interface FieldInfo {
  name: string;
  type: string;
  required: boolean;
  enum?: string[];
  description?: string;
  condition?: string;
}

interface VariantInfo {
  title: string;
  kind: string;
  required: string[];
}

function extractFieldsFromSchema(schema: Record<string, unknown>): FieldInfo[] {
  const properties = schema.properties as Record<string, unknown> | undefined;
  const required = new Set((schema.required as string[]) || []);

  if (!properties) return [];

  return Object.entries(properties).map(([name, prop]) => {
    const p = prop as Record<string, unknown>;
    return {
      name,
      type: Array.isArray(p.type) ? p.type.join(' | ') : (p.type as string) || 'unknown',
      required: required.has(name),
      enum: p.enum as string[] | undefined,
      description: p.description as string | undefined,
      condition: p.x_when as string | undefined,
    };
  });
}

function extractVariants(schema: Record<string, unknown>): VariantInfo[] {
  const oneOf = schema.oneOf as Array<Record<string, unknown>> | undefined;
  if (!oneOf) return [];

  return oneOf.map((variant) => {
    const title = (variant.title as string) || 'variant';
    const required = (variant.required as string[]) || [];
    const props = variant.properties as Record<string, unknown> | undefined;
    const kindProp = props?.kind as Record<string, unknown> | undefined;

    let kind = '';
    if (kindProp?.const) {
      kind = String(kindProp.const);
    } else if (kindProp?.enum) {
      kind = (kindProp.enum as string[]).join(' | ');
    }

    return { title, kind, required };
  });
}

function isFieldMentioned(fieldName: string, rulesText: string): boolean {
  return rulesText.toLowerCase().includes(fieldName.toLowerCase());
}

export function ContractFieldsBlock({
  contract,
  rulesText = '',
  title = 'Формат ответа (контракт)',
}: ContractFieldsBlockProps) {
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

  // Format switcher (disabled when locked)
  const formatOptions = [
    { value: 'json', label: 'JSON' },
    { value: 'markdown', label: 'Markdown' },
    { value: 'plain_text', label: 'Plain text' },
  ];

  if (format === 'json' && contract.schema) {
    const schema = contract.schema as Record<string, unknown>;
    const fields = extractFieldsFromSchema(schema);
    const variants = extractVariants(schema);

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

        {/* Variants sections (for discriminated unions like planner kind) */}
        {variants.length > 0 && (
          <div style={{ borderBottom: '1px solid var(--border-color)' }}>
            {variants.map((variant) => (
              <div key={variant.title} style={{ borderBottom: '1px solid var(--border-color)' }}>
                <div
                  style={{
                    padding: '10px 16px',
                    background: 'var(--bg-tertiary)',
                    fontSize: 12,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                    color: 'var(--text-secondary)',
                  }}
                >
                  {variant.title}
                  <code
                    style={{
                      marginLeft: 8,
                      padding: '2px 6px',
                      background: 'var(--bg-secondary)',
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 400,
                    }}
                  >
                    kind={variant.kind}
                  </code>
                </div>
                <div style={{ padding: '8px 16px' }}>
                  {variant.required.length > 0 && (
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
                      Обязательные поля: {variant.required.join(', ')}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Fields list */}
        <div style={{ padding: '8px 0' }}>
          {fields.map((field) => {
            const mentioned = isFieldMentioned(field.name, rulesText);
            return (
              <div
                key={field.name}
                style={{
                  padding: '10px 16px',
                  borderBottom: '1px solid var(--border-color)',
                  display: 'grid',
                  gridTemplateColumns: '1fr auto',
                  gap: 12,
                  alignItems: 'start',
                }}
              >
                <div>
                  {/* Field name and badges */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <code
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        fontFamily: 'monospace',
                        color: mentioned ? 'var(--success)' : 'var(--warning)',
                      }}
                    >
                      {field.name}
                      {field.required && <span style={{ color: 'var(--danger)' }}>*</span>}
                    </code>

                    {/* Type badge */}
                    <span
                      style={{
                        fontSize: 11,
                        padding: '2px 6px',
                        background: 'var(--bg-secondary)',
                        borderRadius: 4,
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {field.type}
                    </span>

                    {/* Enum values */}
                    {field.enum && field.enum.length > 0 && (
                      <span
                        style={{
                          fontSize: 11,
                          padding: '2px 6px',
                          background: 'var(--bg-tertiary)',
                          borderRadius: 4,
                          color: 'var(--text-secondary)',
                          fontFamily: 'monospace',
                        }}
                      >
                        {field.enum.join(' | ')}
                      </span>
                    )}

                    {/* Condition badge */}
                    {field.condition && (
                      <span
                        style={{
                          fontSize: 10,
                          padding: '2px 6px',
                          background: 'var(--info-soft)',
                          borderRadius: 4,
                          color: 'var(--info)',
                        }}
                      >
                        when {field.condition}
                      </span>
                    )}
                  </div>

                  {/* Description */}
                  {field.description && (
                    <div
                      style={{
                        marginTop: 4,
                        fontSize: 12,
                        color: 'var(--text-secondary)',
                        lineHeight: 1.4,
                      }}
                    >
                      {field.description}
                    </div>
                  )}
                </div>

                {/* Coverage indicator */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 12,
                    color: mentioned ? 'var(--success)' : 'var(--warning)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <span>{mentioned ? '✓' : '⚠'}</span>
                  <span>{mentioned ? 'в правилах' : 'не описано'}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Summary footer */}
        <div
          style={{
            padding: '12px 16px',
            background: 'var(--bg-secondary)',
            borderTop: '1px solid var(--border-color)',
            fontSize: 12,
            color: 'var(--text-secondary)',
          }}
        >
          {(() => {
            const mentioned = fields.filter((f) => isFieldMentioned(f.name, rulesText));
            const missing = fields.filter((f) => !isFieldMentioned(f.name, rulesText));
            return (
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                <span>
                  Описано:{' '}
                  <strong style={{ color: 'var(--success)' }}>{mentioned.length}</strong> /{' '}
                  {fields.length}
                </span>
                {missing.length > 0 && (
                  <span>
                    Не описано:{' '}
                    <strong style={{ color: 'var(--warning)' }}>{missing.map((f) => f.name).join(', ')}</strong>
                  </span>
                )}
              </div>
            );
          })()}
        </div>
      </div>
    );
  }

  // Plain text / Markdown fallback
  return (
    <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, overflow: 'hidden' }}>
      <div
        style={{
          padding: '12px 16px',
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 500 }}>{title}</div>
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
          <span>🔒</span>
          <span>backend</span>
        </span>
      </div>
      <div style={{ padding: 16 }}>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>формат: {format}</div>
        <pre
          style={{
            margin: 0,
            padding: 12,
            background: 'var(--bg-secondary)',
            borderRadius: 4,
            fontSize: 12,
            maxHeight: 200,
            overflow: 'auto',
          }}
        >
          {JSON.stringify(format === 'plain_text' ? contract.plain_text : contract.markdown, null, 2)}
        </pre>
      </div>
    </div>
  );
}
