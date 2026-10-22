import { useEffect, useState } from 'react';
import { MemoryScopeSelect } from '@/shared/ui/MemoryScopeSelect/MemoryScopeSelect';
import styles from './ProfileMemoryScopes.module.css';

export function ProfileMemoryScopes({
  scopeKeys,
  tenantScopeKeys,
  hasTenant,
  editable = false,
  onChange,
}: {
  scopeKeys: string[];
  tenantScopeKeys: string[];
  hasTenant: boolean;
  editable?: boolean;
  onChange?: (scopeKeys: string[]) => void;
}) {
  const [selected, setSelected] = useState(scopeKeys);

  useEffect(() => setSelected(scopeKeys), [scopeKeys]);

  return (
    <div>
      <h2>Скоупы памяти чатов</h2>
      <p className={styles.hint}>Личные скоупы и скоупы тенанта управляются отдельно.</p>
      <label>Мои скоупы</label>
      <MemoryScopeSelect
        value={[...new Set(selected)]}
        disabled={!editable}
        onChange={keys => { setSelected(keys); onChange?.(keys); }}
      />
      {hasTenant && <>
        <label>Скоупы тенанта</label>
        <MemoryScopeSelect value={tenantScopeKeys} readOnly onChange={() => undefined} />
      </>}
    </div>
  );
}
