/**
 * CollectionsListPage - List of available collections for data management
 */
import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { Icon } from '@shared/ui/Icon';
import { collectionsApi, type Collection } from '@shared/api/collections';
import styles from './CollectionsListPage.module.css';

export default function CollectionsListPage() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['collections', 'list'],
    queryFn: () => collectionsApi.list(true),
  });

  const collections = data?.items ?? [];

  const filteredCollections = useMemo(() => {
    if (!searchQuery.trim()) return collections;
    const q = searchQuery.toLowerCase();
    return collections.filter(
      c =>
        c.name.toLowerCase().includes(q) ||
        c.slug.toLowerCase().includes(q) ||
        c.description?.toLowerCase().includes(q)
    );
  }, [collections, searchQuery]);

  const handleCardClick = (collection: Collection) => {
    navigate(`/gpt/collections/${collection.slug}`);
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>Коллекции данных</h1>
          <p className={styles.subtitle}>
            Управление структурированными данными для AI агентов
          </p>
        </div>
        <div>
          <Input
            placeholder="Поиск коллекций..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={styles.search}
          />
        </div>
      </header>

      <div className={styles.content}>
        {isLoading ? (
          <div className={styles.grid}>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className={styles.card}>
                <Skeleton width="60%" height={24} />
                <Skeleton width="40%" height={16} />
                <Skeleton width="100%" height={40} />
                <Skeleton width="80%" height={20} />
              </div>
            ))}
          </div>
        ) : filteredCollections.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>
              <Icon name="database" size={48} />
            </div>
            <div className={styles.emptyTitle}>
              {searchQuery ? 'Ничего не найдено' : 'Нет доступных коллекций'}
            </div>
            <p className={styles.emptyText}>
              {searchQuery
                ? 'Попробуйте изменить поисковый запрос'
                : 'Коллекции создаются администратором в панели управления'}
            </p>
          </div>
        ) : (
          <div className={styles.grid}>
            {filteredCollections.map(collection => (
              <div
                key={collection.id}
                className={styles.card}
                onClick={() => handleCardClick(collection)}
              >
                <div className={styles.cardHeader}>
                  <div>
                    <h3 className={styles.cardTitle}>{collection.name}</h3>
                    <div className={styles.cardSlug}>{collection.slug}</div>
                  </div>
                  <Badge
                    tone={collection.type === 'sql' ? 'info' : 'warning'}
                    size="small"
                  >
                    {collection.type.toUpperCase()}
                  </Badge>
                </div>

                {collection.description && (
                  <p className={styles.cardDescription}>
                    {collection.description}
                  </p>
                )}

                <div className={styles.fieldsList}>
                  {Array.isArray(collection.fields) && collection.fields.slice(0, 4).map(f => (
                    <Badge key={f.name} tone="neutral" size="small">
                      {f.name}
                    </Badge>
                  ))}
                  {Array.isArray(collection.fields) && collection.fields.length > 4 && (
                    <Badge tone="neutral" size="small">
                      +{collection.fields.length - 4}
                    </Badge>
                  )}
                </div>

                <div className={styles.cardMeta}>
                  <div className={styles.metaItem}>
                    <Icon name="file-text" size={14} />
                    <span className={styles.metaValue}>
                      {collection.row_count.toLocaleString()}
                    </span>
                    записей
                  </div>
                  <div className={styles.metaItem}>
                    <Icon name="settings" size={14} />
                    <span className={styles.metaValue}>
                      {collection.fields.length}
                    </span>
                    полей
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
