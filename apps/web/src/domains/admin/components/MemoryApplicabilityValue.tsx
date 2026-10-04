import { Badge } from '@/shared/ui';
import { contentFieldLabels } from './MemoryContentView';
import styles from './MemoryApplicabilityValue.module.css';

const labels: Record<string, string> = { tags: 'Теги', domains: 'Области', systems: 'Системы', environment: 'Среда', environments: 'Среды',
  roles: 'Роли', services: 'Сервисы', teams: 'Команды', projects: 'Проекты', ...contentFieldLabels };
export const applicabilityLabel = (key: string) => labels[key] ?? key.replace(/_/g, ' ');

export default function MemoryApplicabilityValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === '') return <span>Не указано</span>;
  if (Array.isArray(value)) return <div className={styles.labels}>{value.map((item, index) => <MemoryApplicabilityValue key={index} value={item} />)}</div>;
  if (typeof value === 'object') return <dl className={styles.rows}>{Object.entries(value).map(([key, item]) => <div key={key}>
    <dt>{applicabilityLabel(key)}</dt><dd><MemoryApplicabilityValue value={item} /></dd>
  </div>)}</dl>;
  return <Badge tone="info">{typeof value === 'boolean' ? value ? 'Да' : 'Нет' : String(value)}</Badge>;
}
