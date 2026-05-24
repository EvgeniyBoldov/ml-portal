import { useMemo, useState } from 'react';

import type { ResponseContract } from '@/shared/api/admin';
import styles from './ContractAwareEditor.module.css';

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function pretty(value: unknown): string {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function ExamplesView({
  contract,
}: {
  contract: ResponseContract | null;
}) {
  const [tab, setTab] = useState<'input' | 'output'>('output');
  const [variant, setVariant] = useState<string>('default');

  const examplesV2 = (contract?.examples_v2 ?? null) as Record<string, unknown> | null;
  const inputExample = examplesV2 ? examplesV2.input : undefined;
  const outputs = useMemo(() => {
    if (!examplesV2) return {} as Record<string, unknown>;
    return asRecord(examplesV2.outputs);
  }, [examplesV2]);
  const outputVariants = useMemo(() => Object.keys(outputs), [outputs]);
  const selectedVariant = outputVariants.includes(variant) ? variant : (outputVariants[0] ?? 'default');
  const outputExample = outputs[selectedVariant];

  if (!examplesV2) {
    return <div className={styles.examplesPlaceholder}>Примеры не заданы в контракте.</div>;
  }

  return (
    <div className={styles.examplesRoot}>
      <div className={styles.examplesTabs}>
        <button type="button" className={`${styles.examplesTab} ${tab === 'input' ? styles.examplesTabActive : ''}`} onClick={() => setTab('input')}>
          Input
        </button>
        <button type="button" className={`${styles.examplesTab} ${tab === 'output' ? styles.examplesTabActive : ''}`} onClick={() => setTab('output')}>
          Output
        </button>
      </div>

      {tab === 'output' && outputVariants.length > 1 ? (
        <div className={styles.examplesVariants}>
          {outputVariants.map((key) => (
            <button
              key={key}
              type="button"
              className={`${styles.examplesVariantChip} ${selectedVariant === key ? styles.examplesVariantChipActive : ''}`}
              onClick={() => setVariant(key)}
            >
              {key}
            </button>
          ))}
        </div>
      ) : null}

      <pre className={styles.examplesPre}>
        {tab === 'input' ? pretty(inputExample ?? {}) : pretty(outputExample ?? {})}
      </pre>
    </div>
  );
}
