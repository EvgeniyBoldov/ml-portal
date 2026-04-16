/**
 * RbacTargetBlock - Блок для отображения информации о владельце RBAC правила
 */
import React from 'react';
import Badge from '../Badge';
import styles from './RbacTargetBlock.module.css';

export interface RbacTargetData {
  owner_user_id?: string | null;
  owner_tenant_id?: string | null;
  owner_platform: boolean;
  created_at: string;
  created_by_user_id?: string | null;
}

interface RbacTargetBlockProps {
  data: RbacTargetData;
  editable?: boolean;
}

export function RbacTargetBlock({ data, editable = false }: RbacTargetBlockProps) {
  const getOwnerInfo = (): { type: string; label: string } => {
    if (data.owner_platform) {
      return { type: 'platform', label: 'Платформа' };
    }
    if (data.owner_tenant_id) {
      return { 
        type: 'tenant', 
        label: 'Тенант',
      };
    }
    if (data.owner_user_id) {
      return { 
        type: 'user', 
        label: 'Пользователь',
      };
    }
    return { type: 'unknown', label: 'Неизвестно' };
  };

  const ownerInfo = getOwnerInfo();

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Владелец правила</h3>
      
      <div className={styles.grid}>
        {/* Тип владельца */}
        <div className={styles.field}>
          <label className={styles.label}>Тип владельца</label>
          <div className={styles.badgeWrapper}>
            <Badge tone="info">{ownerInfo.label}</Badge>
          </div>
        </div>

        {/* Дата создания */}
        <div className={styles.field}>
          <label className={styles.label}>Создано</label>
          <div className={styles.value}>
            {new Date(data.created_at).toLocaleString('ru-RU')}
          </div>
        </div>

        {/* Создатель intentionally omitted to avoid raw UUID display */}
      </div>
    </div>
  );
}
