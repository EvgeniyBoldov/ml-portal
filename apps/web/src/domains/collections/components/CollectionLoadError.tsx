import { Button } from '@/shared/ui';

export function CollectionLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert">
      <p>
        Не удалось загрузить данные. Проверьте соединение и повторите попытку.
      </p>
      <Button variant="outline" onClick={onRetry}>
        Повторить
      </Button>
    </div>
  );
}
