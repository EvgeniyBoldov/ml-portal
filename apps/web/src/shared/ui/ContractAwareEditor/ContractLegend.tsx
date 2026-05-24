import { useState, useMemo } from 'react';
import { ExamplesView } from './ExamplesView';
import { SchemaTreeRenderer, PlainTextContractLegend, ResponseContractSchemaSummary } from './SchemaTreeRenderer';
import type { ResponseContract } from '@/shared/api/admin';
import styles from './ContractAwareEditor.module.css';

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function hasSchemaShape(value: Record<string, unknown> | null): boolean {
  if (!value) return false;
  return Boolean(value.properties) || Boolean(value.items) || Boolean(value.oneOf);
}

function extractInputFields(schema: Record<string, unknown> | null): Array<{ name: string; type: string; description: string; required: boolean }> {
  if (!schema) return [];
  const properties = asRecord(schema.properties);
  const requiredSet = new Set(asStringArray(schema.required));
  return Object.entries(properties).map(([name, raw]) => {
    const prop = asRecord(raw);
    const typeVal = prop.type;
    const typeStr = typeof typeVal === 'string' ? typeVal : Array.isArray(typeVal) ? (typeVal as string[]).filter(v => v !== 'null').join('|') : '';
    return {
      name,
      type: typeStr,
      description: typeof prop.description === 'string' ? prop.description : '',
      required: requiredSet.has(name),
    };
  });
}

export function ContractLegend({
  outputContract,
  inputContract,
  coverageMap,
  coveredCount,
  totalRequired,
  uncoveredFields,
  onInsert,
  onHoverField,
  activeField,
}: {
  outputContract: ResponseContract | null;
  inputContract: Record<string, unknown> | null;
  coverageMap: Map<string, boolean>;
  coveredCount: number;
  totalRequired: number;
  uncoveredFields: string[];
  onInsert?: (token: string) => void;
  onHoverField?: (fieldName: string | null) => void;
  activeField?: string | null;
}) {
  const [outputTab, setOutputTab] = useState<'schema' | 'example'>('schema');
  const [inputTab, setInputTab] = useState<'fields' | 'example'>('fields');

  const examplesV2 = useMemo(() => {
    const raw = (outputContract as Record<string, unknown> | null)?.examples_v2;
    return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw as Record<string, unknown> : null;
  }, [outputContract]);
  const inputExample = examplesV2?.input;

  const showOutputSchema =
    outputContract?.format === 'json' &&
    outputContract.schema &&
    typeof outputContract.schema === 'object';
  const showPlainText =
    outputContract?.format === 'plain_text' || outputContract?.format === 'markdown';
  const inputSchema =
    inputContract && typeof inputContract === 'object' ? inputContract : null;
  const inputFields = useMemo(() => extractInputFields(inputSchema), [inputSchema]);

  if (!outputContract && !inputSchema) return null;

  const allCovered = totalRequired > 0 && coveredCount >= totalRequired;
  const showCoverage = showOutputSchema && totalRequired > 0;

  return (
    <div className={styles.legendThreeZone}>

      {/* ── Zone 1: Input (1/4 height) ────────────────────── */}
      {inputFields.length > 0 && (
        <div className={styles.legendZoneInput}>
          <div className={styles.legendZoneHeader}>
            <div className={styles.legendZoneLabel}>Входные данные</div>
            <div className={styles.outputTabBar}>
              <button
                type="button"
                className={`${styles.outputTab} ${inputTab === 'fields' ? styles.outputTabActive : ''}`}
                onClick={() => setInputTab('fields')}
              >
                Поля
              </button>
              <button
                type="button"
                className={`${styles.outputTab} ${inputTab === 'example' ? styles.outputTabActive : ''}`}
                onClick={() => setInputTab('example')}
              >
                Пример
              </button>
            </div>
          </div>

          <div className={styles.inputPanel}>
            {inputTab === 'fields' && (
              <div className={styles.inputFieldList}>
                {inputFields.map((field) => (
                  <button
                    key={field.name}
                    type="button"
                    className={`${styles.inputFieldRow} ${activeField === field.name ? styles.inputFieldRowActive : ''}`}
                    onClick={() => onInsert?.('`' + field.name + '`')}
                    onMouseEnter={() => onHoverField?.(field.name)}
                    onMouseLeave={() => onHoverField?.(null)}
                  >
                    <span className={styles.inputFieldName}>{field.name}</span>
                    {field.type ? <span className={styles.inputChipType}>{field.type}</span> : null}
                    {field.required ? <span className={styles.inputFieldRequired}>*</span> : null}
                    {field.description ? <span className={styles.inputFieldDesc}>{field.description}</span> : null}
                  </button>
                ))}
              </div>
            )}
            {inputTab === 'example' && (
              inputExample
                ? <pre className={styles.examplesPre}>{typeof inputExample === 'string' ? inputExample : JSON.stringify(inputExample, null, 2)}</pre>
                : <div className={styles.examplesPlaceholder}>Пример не задан в контракте.</div>
            )}
          </div>
        </div>
      )}

      {/* ── Zone 2: Output (flex:1, tabs Структура / Пример) */}
      {(showOutputSchema || showPlainText) && (
        <div className={styles.legendZoneOutput}>
          <div className={styles.legendZoneHeader}>
            <div className={styles.legendZoneLabel}>LLM должна вернуть</div>
            <div className={styles.outputTabBar}>
              <button
                type="button"
                className={`${styles.outputTab} ${outputTab === 'schema' ? styles.outputTabActive : ''}`}
                onClick={() => setOutputTab('schema')}
              >
                Структура
              </button>
              <button
                type="button"
                className={`${styles.outputTab} ${outputTab === 'example' ? styles.outputTabActive : ''}`}
                onClick={() => setOutputTab('example')}
              >
                Пример
              </button>
            </div>
          </div>

          <div className={styles.outputTabContent}>
            {outputTab === 'schema' && showOutputSchema && (
              <ResponseContractSchemaSummary
                contract={outputContract}
                coverageMap={coverageMap}
                onInsert={onInsert}
                onHoverField={onHoverField}
                activeField={activeField}
              />
            )}
            {outputTab === 'schema' && showPlainText && (
              <>
                <PlainTextContractLegend contract={outputContract} />
              </>
            )}
            {outputTab === 'example' && (
              <ExamplesView contract={outputContract} />
            )}
          </div>
        </div>
      )}

      {/* ── Zone 3: Coverage footer (1/6 height) ─────────── */}
      {showCoverage && (
        <div className={styles.legendZoneCoverage}>
          <span className={allCovered ? styles.legendFooterCovered : styles.legendFooterSummary}>
            {allCovered ? '✓' : '⚠'} {coveredCount}/{totalRequired} полей описано
          </span>
          {uncoveredFields.length > 0 && (
            <div className={styles.legendMissing}>
              {uncoveredFields.map((field) => (
                <span key={field} className={styles.legendMissingChip}>{field}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
