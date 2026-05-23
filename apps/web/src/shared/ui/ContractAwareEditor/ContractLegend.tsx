import Badge from '../Badge';
import { SchemaTreeRenderer, PlainTextContractLegend, ResponseContractSchemaSummary } from './SchemaTreeRenderer';
import type { ResponseContract } from '@/shared/api/admin';
import styles from './ContractAwareEditor.module.css';

function hasSchemaShape(value: Record<string, unknown> | null): boolean {
  if (!value) return false;
  return Boolean(value.properties) || Boolean(value.items) || Boolean(value.oneOf);
}

export function ContractLegend({
  outputContract,
  inputContract,
  coverageMap,
  coveredCount,
  totalRequired,
  uncoveredFields,
  onFieldClick,
}: {
  outputContract: ResponseContract | null;
  inputContract: Record<string, unknown> | null;
  coverageMap: Map<string, boolean>;
  coveredCount: number;
  totalRequired: number;
  uncoveredFields: string[];
  onFieldClick?: (fieldName: string) => void;
}) {
  const showOutputSchema = outputContract?.format === 'json' && outputContract.schema && typeof outputContract.schema === 'object';
  const showPlainText = outputContract?.format === 'plain_text' || outputContract?.format === 'markdown';
  const inputSchema = inputContract && typeof inputContract === 'object' ? inputContract : null;

  if (!outputContract && !inputSchema) return null;

  return (
    <div className={styles.legendRoot}>
      {showOutputSchema && (
        <section className={styles.legendSection}>
          <div className={styles.legendSectionTitle}>Выходной контракт</div>
          <ResponseContractSchemaSummary
            contract={outputContract}
            coverageMap={coverageMap}
            onFieldClick={onFieldClick}
          />
        </section>
      )}

      {showPlainText && (
        <section className={styles.legendSection}>
          <div className={styles.legendSectionTitle}>Выходной формат</div>
          <PlainTextContractLegend contract={outputContract} />
        </section>
      )}

      {inputSchema && (
        <section className={styles.legendSection}>
          <div className={styles.legendSectionTitle}>Входные данные</div>
          {hasSchemaShape(inputSchema) ? (
            <SchemaTreeRenderer
              schema={inputSchema}
              onFieldClick={onFieldClick}
            />
          ) : (
            <pre className={styles.rawSchema}>{JSON.stringify(inputSchema, null, 2)}</pre>
          )}
        </section>
      )}

      {showOutputSchema && (
        <section className={styles.legendFooter}>
          <div className={styles.legendFooterSummary}>
            <Badge tone={coveredCount >= totalRequired ? 'success' : 'warn'} size="small">
              {coveredCount}/{totalRequired} описано
            </Badge>
          </div>
          {uncoveredFields.length > 0 && (
            <div className={styles.legendMissing}>
              {uncoveredFields.map((field) => (
                <Badge key={field} tone="warn" size="small" className={styles.legendMissingBadge}>
                  {field}
                </Badge>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
