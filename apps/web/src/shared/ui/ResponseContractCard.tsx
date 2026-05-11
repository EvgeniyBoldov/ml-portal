import type { ResponseContract } from '@/shared/api/admin';

interface ResponseContractCardProps {
  contract?: ResponseContract | null;
  rulesText?: string | null;
  outputRequirementsText?: string | null;
}

function renderContractBody(contract?: ResponseContract | null): string {
  if (!contract) return 'Контракт не задан';
  if (contract.format === 'json') return JSON.stringify(contract.schema, null, 2);
  if (contract.format === 'plain_text') return JSON.stringify(contract.plain_text, null, 2);
  return JSON.stringify(contract.markdown, null, 2);
}

interface JsonSchemaFieldRow {
  path: string;
  type: string;
  required: boolean;
  enumValues: string[];
  description: string;
  condition: string;
}
interface JsonSchemaVariantRow {
  title: string;
  kind: string;
  required: string[];
  describedRequired: string[];
  missingRequired: string[];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function normalizeType(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    const values = value.filter((item): item is string => typeof item === 'string');
    return values.join(' | ');
  }
  return 'unknown';
}

function collectSchemaRows(
  schema: Record<string, unknown>,
  basePath = '',
  parentRequired = false,
): JsonSchemaFieldRow[] {
  const properties = asRecord(schema.properties);
  const requiredSet = new Set(asStringArray(schema.required));
  const rows: JsonSchemaFieldRow[] = [];

  for (const [key, rawSubSchema] of Object.entries(properties)) {
    const subSchema = asRecord(rawSubSchema);
    const path = basePath ? `${basePath}.${key}` : key;
    const type = normalizeType(subSchema.type);
    const required = parentRequired || requiredSet.has(key);
    const enumValues = asStringArray(subSchema.enum);
    const description = typeof subSchema.description === 'string' ? subSchema.description : '';
    const condition = typeof subSchema.x_when === 'string' ? subSchema.x_when : '';

    rows.push({ path, type, required, enumValues, description, condition });

    const nestedObjectRows = collectSchemaRows(subSchema, path, required);
    if (nestedObjectRows.length > 0) rows.push(...nestedObjectRows);

    if (type.includes('array')) {
      const items = asRecord(subSchema.items);
      if (Object.keys(items).length > 0) {
        const itemType = normalizeType(items.type);
        const itemEnum = asStringArray(items.enum);
        const itemDescription = typeof items.description === 'string' ? items.description : '';
        rows.push({
          path: `${path}[]`,
          type: itemType,
          required: false,
          enumValues: itemEnum,
          description: itemDescription,
          condition: typeof items.x_when === 'string' ? items.x_when : '',
        });
        const nestedItemRows = collectSchemaRows(items, `${path}[]`, false);
        if (nestedItemRows.length > 0) rows.push(...nestedItemRows);
      }
    }
  }

  return rows;
}

function extractJsonKeys(contract?: ResponseContract | null): string[] {
  if (!contract || contract.format !== 'json') return [];
  const props = contract.schema?.properties;
  if (!props || typeof props !== 'object' || Array.isArray(props)) return [];
  return Object.keys(props);
}

function collectSchemaVariants(schema: Record<string, unknown>): JsonSchemaVariantRow[] {
  const oneOf = Array.isArray(schema.oneOf) ? schema.oneOf : [];
  return oneOf
    .map((item) => asRecord(item))
    .map((variant) => {
      const title = typeof variant.title === 'string' ? variant.title : 'variant';
      const required = asStringArray(variant.required);
      const props = asRecord(variant.properties);
      const kindSchema = asRecord(props.kind);
      let kind = '—';
      if (typeof kindSchema.const === 'string') kind = kindSchema.const;
      else {
        const kinds = asStringArray(kindSchema.enum);
        if (kinds.length > 0) kind = kinds.join(' | ');
      }
      return { title, kind, required, describedRequired: [], missingRequired: [] };
    });
}

function withVariantCoverage(
  variants: JsonSchemaVariantRow[],
  rulesText?: string | null,
  outputRequirementsText?: string | null,
): JsonSchemaVariantRow[] {
  if (variants.length === 0) return variants;
  const haystack = `${rulesText ?? ''}\n${outputRequirementsText ?? ''}`.toLowerCase();
  return variants.map((row) => {
    const requiredKeys = row.required.filter((key) => key !== 'kind' && key !== 'rationale');
    const describedRequired = requiredKeys.filter((key) => haystack.includes(key.toLowerCase()));
    const describedSet = new Set(describedRequired);
    const missingRequired = requiredKeys.filter((key) => !describedSet.has(key));
    return { ...row, describedRequired, missingRequired };
  });
}

function buildHealthSummary(
  contract?: ResponseContract | null,
  rulesText?: string | null,
  outputRequirementsText?: string | null,
): string[] {
  if (!contract) return ['contract missing'];
  if (contract.format !== 'json') return ['contract valid'];

  const issues: string[] = [];
  const coverage = buildCoverage(contract, rulesText, outputRequirementsText);
  if (coverage.missing.length > 0) issues.push(`required fields not described: ${coverage.missing.join(', ')}`);

  const schema = asRecord(contract.schema);
  const rows = collectSchemaRows(schema);
  const enumWithoutDescription = rows.filter((r) => r.enumValues.length > 0 && !r.description).map((r) => r.path);
  if (enumWithoutDescription.length > 0) {
    issues.push(`enum without description: ${enumWithoutDescription.join(', ')}`);
  }

  if (!Array.isArray(contract.examples) || contract.examples.length === 0) {
    issues.push('no examples');
  }
  if (issues.length === 0) return ['contract valid'];
  return issues;
}

function buildCoverage(
  contract?: ResponseContract | null,
  rulesText?: string | null,
  outputRequirementsText?: string | null,
): { described: string[]; missing: string[] } {
  const keys = extractJsonKeys(contract);
  if (keys.length === 0) return { described: [], missing: [] };
  const haystack = `${rulesText ?? ''}\n${outputRequirementsText ?? ''}`.toLowerCase();
  const described = keys.filter((key) => haystack.includes(key.toLowerCase()));
  const describedSet = new Set(described);
  const missing = keys.filter((key) => !describedSet.has(key));
  return { described, missing };
}

export function ResponseContractCard({ contract, rulesText, outputRequirementsText }: ResponseContractCardProps) {
  const format = contract?.format ?? '—';
  const coverage = buildCoverage(contract, rulesText, outputRequirementsText);
  const keys = extractJsonKeys(contract);
  const schemaRows =
    contract?.format === 'json'
      ? collectSchemaRows(asRecord(contract.schema))
      : [];
  const variantRows =
    contract?.format === 'json'
      ? collectSchemaVariants(asRecord(contract.schema))
      : [];
  const variantRowsWithCoverage = withVariantCoverage(variantRows, rulesText, outputRequirementsText);
  const healthSummary = buildHealthSummary(contract, rulesText, outputRequirementsText);

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
        format: <strong>{format}</strong> · source: backend
      </div>
      {contract?.format === 'json' ? (
        <div style={{ overflow: 'auto', border: '1px solid var(--border-color)', borderRadius: 8 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: 'var(--bg-secondary)' }}>
                <th style={{ textAlign: 'left', padding: '8px 10px' }}>field</th>
                <th style={{ textAlign: 'left', padding: '8px 10px' }}>type</th>
                <th style={{ textAlign: 'left', padding: '8px 10px' }}>required</th>
                <th style={{ textAlign: 'left', padding: '8px 10px' }}>enum</th>
                <th style={{ textAlign: 'left', padding: '8px 10px' }}>condition</th>
                <th style={{ textAlign: 'left', padding: '8px 10px' }}>description</th>
              </tr>
            </thead>
            <tbody>
              {schemaRows.length > 0 ? (
                schemaRows.map((row) => (
                  <tr key={row.path}>
                    <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>
                      <code>{row.path}</code>
                    </td>
                    <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>{row.type}</td>
                    <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>
                      {row.required ? 'yes' : 'no'}
                    </td>
                    <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>
                      {row.enumValues.length > 0 ? row.enumValues.join(', ') : '—'}
                    </td>
                    <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>
                      {row.condition || '—'}
                    </td>
                    <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>
                      {row.description || '—'}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} style={{ padding: '10px', borderTop: '1px solid var(--border-color)' }}>
                    No schema properties
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <details style={{ padding: 10, borderTop: '1px solid var(--border-color)' }}>
            <summary style={{ cursor: 'pointer' }}>raw schema</summary>
            <pre style={{ margin: '8px 0 0', maxHeight: 240, overflow: 'auto' }}>
              {JSON.stringify(contract.schema, null, 2)}
            </pre>
          </details>
          {variantRowsWithCoverage.length > 0 && (
            <details style={{ padding: 10, borderTop: '1px solid var(--border-color)' }}>
              <summary style={{ cursor: 'pointer' }}>response variants</summary>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, marginTop: 8 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-secondary)' }}>
                    <th style={{ textAlign: 'left', padding: '8px 10px' }}>variant</th>
                    <th style={{ textAlign: 'left', padding: '8px 10px' }}>kind</th>
                    <th style={{ textAlign: 'left', padding: '8px 10px' }}>required fields</th>
                    <th style={{ textAlign: 'left', padding: '8px 10px' }}>coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {variantRowsWithCoverage.map((row) => (
                    <tr key={`${row.title}:${row.kind}`}>
                      <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>{row.title}</td>
                      <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>
                        <code>{row.kind}</code>
                      </td>
                      <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>
                        {row.required.join(', ')}
                      </td>
                      <td style={{ padding: '8px 10px', borderTop: '1px solid var(--border-color)' }}>
                        {row.missingRequired.length === 0
                          ? 'ok'
                          : `missing: ${row.missingRequired.join(', ')}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </div>
      ) : (
        <pre style={{ margin: 0, maxHeight: 320, overflow: 'auto', background: 'var(--bg-secondary)', padding: 12, borderRadius: 8 }}>
          {renderContractBody(contract)}
        </pre>
      )}
      {contract?.format === 'json' && (
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
          <div>описано: {coverage.described.length} / {keys.length}</div>
          <div>не описано: {coverage.missing.length > 0 ? coverage.missing.join(', ') : '—'}</div>
        </div>
      )}
      <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
        <div>contract health:</div>
        {healthSummary.map((item) => (
          <div key={item}>- {item}</div>
        ))}
      </div>
    </div>
  );
}

export default ResponseContractCard;
