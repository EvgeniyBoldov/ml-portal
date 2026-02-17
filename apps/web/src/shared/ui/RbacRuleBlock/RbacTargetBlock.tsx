/**
 * RbacTargetBlock - Блок для отображения информации о владельце RBAC правила
 * На основе ContentBlock из shared/ui
 */
import React from 'react';
import { ContentBlock, type FieldDefinition, type BlockWidth } from '../ContentBlock';

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
  width?: BlockWidth;
}

export function RbacTargetBlock({ data, editable = false, width = '1/2' }: RbacTargetBlockProps) {
  
  const getOwnerInfo = (): { type: string; label: string; id?: string } => {
    if (data.owner_platform) {
      return { type: 'platform', label: 'Платформа' };
    }
    if (data.owner_tenant_id) {
      return { 
        type: 'tenant', 
        label: 'Тенант', 
        id: data.owner_tenant_id 
      };
    }
    if (data.owner_user_id) {
      return { 
        type: 'user', 
        label: 'Пользователь', 
        id: data.owner_user_id 
      };
    }
    return { type: 'unknown', label: 'Неизвестно' };
  };

  const ownerInfo = getOwnerInfo();

  const fields: FieldDefinition[] = [
    {
      key: 'owner_type',
      label: 'Тип владельца',
      type: 'badge',
      badgeTone: 'info',
      disabled: true,
    },
    {
      key: 'owner_id',
      label: 'ID владельца',
      type: 'code',
      disabled: true,
    },
    {
      key: 'created_at',
      label: 'Создано',
      type: 'date',
      disabled: true,
    },
  ];

  // Добавляем создателя если есть
  if (data.created_by_user_id) {
    fields.push({
      key: 'created_by',
      label: 'Создатель',
      type: 'code',
      disabled: true,
    });
  }

  const displayData = {
    owner_type: ownerInfo.label,
    owner_id: ownerInfo.id || '-',
    created_at: data.created_at,
    created_by: data.created_by_user_id || '-',
  };

  // Скрываем owner_id если его нет
  const filteredFields = ownerInfo.id 
    ? fields 
    : fields.filter(field => field.key !== 'owner_id');

  return (
    <ContentBlock
      title="Владелец правила"
      icon="user"
      iconVariant="primary"
      width={width}
      editable={editable}
      fields={filteredFields}
      data={displayData}
      onChange={() => {}} // Нечего редактировать
    />
  );
}
