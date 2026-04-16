import styles from './ConfigTabs.module.css';

export interface ConfigTabItem {
  id: string;
  label: string;
}

interface Props {
  items: ConfigTabItem[];
  activeId: string;
  onChange: (id: string) => void;
}

export default function ConfigTabs({ items, activeId, onChange }: Props) {
  if (items.length <= 1) {
    return null;
  }

  return (
    <div className={styles['tabs-shell']}>
      <div className={styles.tabs} role="tablist" aria-label="Конфигурационные вкладки">
        {items.map((item) => {
          const isActive = item.id === activeId;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`${styles.tab} ${isActive ? styles['tab-active'] : ''}`}
              onClick={() => onChange(item.id)}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
