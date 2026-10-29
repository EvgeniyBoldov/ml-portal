import { useNavigate } from 'react-router-dom';
import type { Collection } from '@/shared/api/collections';
import Badge from '@/shared/ui/Badge';
import { Icon } from '@/shared/ui/Icon';
import styles from './ExternalCollectionOverview.module.css';

const TYPE_LABELS = {
  api: 'API',
  sql: 'SQL',
} as const;

interface ExternalCollectionOverviewProps {
  collection: Collection;
}

export default function ExternalCollectionOverview({
  collection,
}: ExternalCollectionOverviewProps) {
  const navigate = useNavigate();
  const type = collection.collection_type;
  if (type !== 'api' && type !== 'sql') return null;

  const isPublishedVersion = collection.version?.status === 'published';
  const description = isPublishedVersion ? collection.description?.trim() : '';
  const purpose = isPublishedVersion ? collection.purpose?.trim() : '';
  const count = collection.count;
  const knownCount =
    typeof count?.value === 'number' && count.kind && count.unit
      ? `${count.value.toLocaleString('ru-RU')} ${count.unit}`
      : 'Количество не указано';
  const sourceName = collection.source?.name || collection.data_instance?.name;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles['header-left']}>
          <button
            className={styles['back-button']}
            type="button"
            onClick={() => navigate('/gpt/collections')}
            aria-label="Назад к коллекциям"
          >
            <Icon name="chevron-left" size={20} />
          </button>
          <div className={styles.heading}>
            <h1 className={styles.title}>{collection.name}</h1>
            <div className={styles.subtitle}>
              <span>{collection.slug}</span>
              <Badge tone="neutral">{TYPE_LABELS[type]}</Badge>
              {sourceName && <span>{sourceName}</span>}
            </div>
          </div>
        </div>
      </header>

      <div className={styles.content}>
        <section
          className={styles.card}
          aria-labelledby="external-collection-description"
        >
          <div className={styles['card-heading']}>
            <div>
              <h2 id="external-collection-description">Описание</h2>
              {isPublishedVersion && collection.version && (
                <span className={styles.version}>
                  Версия {collection.version.number}
                </span>
              )}
            </div>
          </div>
          <p className={description ? styles.description : styles.muted}>
            {description || 'Описание не задано'}
          </p>
          {purpose && (
            <div className={styles.purpose}>
              <h3>Назначение</h3>
              <p>{purpose}</p>
            </div>
          )}
        </section>

        <section
          className={styles.card}
          aria-labelledby="external-collection-details"
        >
          <h2 id="external-collection-details">Сведения об источнике</h2>
          <dl className={styles.details}>
            <div className={styles['detail-row']}>
              <dt>Тип</dt>
              <dd>{TYPE_LABELS[type]}</dd>
            </div>
            <div className={styles['detail-row']}>
              <dt>Источник</dt>
              <dd>{sourceName || 'Источник не указан'}</dd>
            </div>
            <div className={styles['detail-row']}>
              <dt>Количество</dt>
              <dd>{knownCount}</dd>
            </div>
          </dl>
          <p className={styles.notice}>
            Просмотр содержимого внешнего источника на этой странице не
            предусмотрен.
          </p>
        </section>

      </div>
    </div>
  );
}
