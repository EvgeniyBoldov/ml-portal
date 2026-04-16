/**
 * SandboxHomePage — home page for sandbox.
 * Shows button to create new sandbox session.
 */
import { useNavigate } from 'react-router-dom';
import Button from '@/shared/ui/Button';
import { useCreateSession } from '../hooks/useSandboxSession';
import { useToast } from '@/shared/ui/Toast';
import styles from './SandboxHomePage.module.css';

export default function SandboxHomePage() {
  const navigate = useNavigate();
  const createSession = useCreateSession();
  const { showToast } = useToast();

  const handleCreate = async () => {
    try {
      const session = await createSession.mutateAsync({});
      navigate(`/sandbox/${session.id}`);
    } catch {
      showToast('Не удалось создать сессию', 'error');
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.content}>
        <h1 className={styles.title}>Песочница</h1>
        <p className={styles.description}>
          Тестирование агентов с изменёнными конфигурациями в изолированной среде
        </p>
        
        <div className={styles.actions}>
          <Button
            onClick={handleCreate}
            disabled={createSession.isPending}
            size="md"
          >
            {createSession.isPending ? 'Создание...' : 'Создать сессию'}
          </Button>
        </div>

        <div className={styles.features}>
          <div className={styles.feature}>
            <h3>Изолированная среда</h3>
            <p>Каждая сессия работает в отдельном пространстве с собственными настройками</p>
          </div>
          <div className={styles.feature}>
            <h3>Phantom-конфигурации</h3>
            <p>Тестируйте версии инструментов и агентов без изменения основных настроек</p>
          </div>
          <div className={styles.feature}>
            <h3>Подтверждение действий</h3>
            <p>Каждая операция записи требует явного подтверждения для безопасности</p>
          </div>
        </div>
      </div>
    </div>
  );
}
