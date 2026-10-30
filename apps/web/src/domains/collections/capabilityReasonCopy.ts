const CAPABILITY_REASON_COPY: Record<string, string> = {
  collection_access_denied: 'У вас нет доступа к этой коллекции.',
  collection_inactive: 'Коллекция неактивна. Действие временно недоступно.',
  collection_membership_mismatch: 'Коллекция недоступна в выбранной рабочей группе.',
  editing_permission_required: 'Изменять содержимое могут администраторы и редакторы этого тенанта.',
  external_content_unavailable: 'Источник данных временно недоступен.',
  operation_not_supported: 'Операция не поддерживается для этой коллекции.',
  storage_unavailable: 'Хранилище документов временно недоступно.',
};

export function capabilityReasonCopy(reason: string | undefined, fallback: string): string {
  if (!reason) return fallback;
  const knownCopy = CAPABILITY_REASON_COPY[reason];
  if (knownCopy) return knownCopy;
  return /[^a-zA-Z0-9_-]/.test(reason) ? reason : fallback;
}
