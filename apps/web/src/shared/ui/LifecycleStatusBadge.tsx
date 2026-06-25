import Badge from './Badge';

type Props = {
  lifecycleStatus?: string | null;
  deprecatedAt?: string | null;
  retentionDays?: number | null;
};

function getDaysUntilDeletion(deprecatedAt?: string | null, retentionDays?: number | null): number | null {
  if (!deprecatedAt || retentionDays == null) return null;
  const deprecatedTime = new Date(deprecatedAt).getTime();
  if (Number.isNaN(deprecatedTime)) return null;
  const expiresAt = deprecatedTime + retentionDays * 24 * 60 * 60 * 1000;
  const remainingMs = expiresAt - Date.now();
  return Math.max(0, Math.ceil(remainingMs / (24 * 60 * 60 * 1000)));
}

export default function LifecycleStatusBadge({
  lifecycleStatus,
  deprecatedAt,
  retentionDays,
}: Props) {
  if (lifecycleStatus === 'deleted') {
    return <Badge tone="danger">Deleted</Badge>;
  }

  if (lifecycleStatus === 'deprecated') {
    const daysLeft = getDaysUntilDeletion(deprecatedAt, retentionDays);
    return (
      <Badge tone="warn">
        {daysLeft == null ? 'Deprecated' : `Deprecated ${daysLeft}d`}
      </Badge>
    );
  }

  return <Badge tone="success">Active</Badge>;
}
