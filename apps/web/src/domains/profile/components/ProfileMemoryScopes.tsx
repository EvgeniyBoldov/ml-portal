import { useEffect, useState } from 'react';
import { MemoryScopeSelect } from '@/shared/ui/MemoryScopeSelect/MemoryScopeSelect';
import Button from '@shared/ui/Button';
import styles from './ProfileMemoryScopes.module.css';

export function ProfileMemoryScopes({
  scopeKeys,
  tenantScopeKeys,
  hasTenant,
  editable = false,
  onChange,
  onStartEdit,
  onCancel,
  onSave,
  isSaving = false,
}: {
  scopeKeys: string[];
  tenantScopeKeys: string[];
  hasTenant: boolean;
  editable?: boolean;
  onChange?: (scopeKeys: string[]) => void;
  onStartEdit?: () => void;
  onCancel?: () => void;
  onSave?: () => void;
  isSaving?: boolean;
}) {
  const [selected, setSelected] = useState(scopeKeys);

  useEffect(() => setSelected(scopeKeys), [scopeKeys, editable]);

  return (
    <div className={styles.content}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>Проекты для памяти чатов</h2>
          <p className={styles.hint}>
            Поиск объединяет личные настройки и настройки рабочей группы. Если оба
            списка пусты, используется «Компания».
          </p>
        </div>
        <div className={styles.actions}>
          {editable ? (
            <>
              <Button
                variant="outline"
                onClick={onCancel}
                disabled={isSaving}
              >
                Отмена
              </Button>
              <Button
                variant="primary"
                onClick={onSave}
                disabled={isSaving}
              >
                {isSaving ? 'Сохранение…' : 'Сохранить'}
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={onStartEdit}>
              Изменить
            </Button>
          )}
        </div>
      </div>

      <div className={styles.groups}>
        <section className={styles.group} aria-labelledby="profile-personal-scopes">
          <div className={styles.groupHeading}>
            <h3 id="profile-personal-scopes" className={styles.groupTitle}>
              Личные проекты
            </h3>
            <p className={styles.groupDescription}>
              Выбранные вами проекты памяти.
            </p>
          </div>
          <MemoryScopeSelect
            value={[...new Set(selected)]}
            disabled={!editable}
            onChange={keys => {
              setSelected(keys);
              onChange?.(keys);
            }}
          />
        </section>

        {hasTenant && (
          <section className={styles.group} aria-labelledby="profile-tenant-scopes">
            <div className={styles.groupHeading}>
              <h3 id="profile-tenant-scopes" className={styles.groupTitle}>
                Проекты рабочей группы
              </h3>
              <p className={styles.groupDescription}>
                Настроены параметрами рабочей группы; здесь доступны для просмотра.
              </p>
            </div>
            <MemoryScopeSelect
              value={tenantScopeKeys}
              readOnly
              onChange={() => undefined}
            />
          </section>
        )}
      </div>
    </div>
  );
}
