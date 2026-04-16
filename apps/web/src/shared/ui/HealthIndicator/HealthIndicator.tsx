import { Icon } from '../Icon';
import styles from './HealthIndicator.module.css';

interface HealthIndicatorProps {
  healthStatus?: string | null;
  isActive?: boolean;
  size?: number;
  title?: string;
}

const STATUS_LABELS: Record<string, string> = {
  healthy: 'Здоров',
  unhealthy: 'Не здоров',
  unknown: 'Не определён',
};

export function HealthIndicator({
  healthStatus,
  isActive = true,
  size = 18,
  title,
}: HealthIndicatorProps) {
  const normalizedStatus = !isActive
    ? 'inactive'
    : healthStatus === 'healthy' || healthStatus === 'unhealthy' || healthStatus === 'unknown'
      ? healthStatus
      : 'unknown';

  const label = normalizedStatus === 'inactive'
    ? 'Не активен'
    : STATUS_LABELS[normalizedStatus] ?? 'Не определён';

  return (
    <span
      className={`${styles.indicator} ${styles[normalizedStatus]}`}
      title={title ?? label}
      aria-label={title ?? label}
    >
      <Icon name="heart-pulse" size={size} className={styles.icon} />
    </span>
  );
}

export default HealthIndicator;
