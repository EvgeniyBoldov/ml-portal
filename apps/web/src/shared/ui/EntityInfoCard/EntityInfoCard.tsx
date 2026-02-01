/**
 * EntityInfoCard - Reusable card for entity basic info
 * 
 * Layout:
 * Row 1: Name (input) + Active (switch)
 * Row 2: Slug (input)
 * Row 3: Description (textarea)
 * 
 * Supports widths: 1/2, 2/3, full
 */
import React from 'react';
import FormField from '../FormField';
import styles from './EntityInfoCard.module.css';

export type EntityInfoCardWidth = '1/2' | '2/3' | 'full';

export interface EntityInfoCardProps {
  /** Entity name */
  name: string;
  /** Entity slug */
  slug: string;
  /** Entity description */
  description?: string;
  /** Is entity active (for switch) */
  isActive?: boolean;
  /** Show active switch */
  showActiveSwitch?: boolean;
  /** Active switch label */
  activeSwitchLabel?: string;
  /** Active switch description */
  activeSwitchDescription?: string;
  /** Is form editable */
  editable?: boolean;
  /** Is slug editable (usually only on create) */
  slugEditable?: boolean;
  /** Card width */
  width?: EntityInfoCardWidth;
  /** Name placeholder */
  namePlaceholder?: string;
  /** Slug placeholder */
  slugPlaceholder?: string;
  /** Description placeholder */
  descriptionPlaceholder?: string;
  /** Slug description text */
  slugDescription?: string;
  /** On name change */
  onNameChange?: (value: string) => void;
  /** On slug change */
  onSlugChange?: (value: string) => void;
  /** On description change */
  onDescriptionChange?: (value: string) => void;
  /** On active change */
  onActiveChange?: (value: boolean) => void;
}

export function EntityInfoCard({
  name,
  slug,
  description = '',
  isActive = true,
  showActiveSwitch = true,
  activeSwitchLabel = 'Активно',
  activeSwitchDescription,
  editable = false,
  slugEditable = false,
  width = 'full',
  namePlaceholder = 'Название',
  slugPlaceholder = 'slug',
  descriptionPlaceholder = 'Описание...',
  slugDescription = 'Уникальный идентификатор',
  onNameChange,
  onSlugChange,
  onDescriptionChange,
  onActiveChange,
}: EntityInfoCardProps) {
  const widthClass = width === '1/2' ? styles.half : width === '2/3' ? styles.twoThirds : styles.full;

  return (
    <div className={`${styles.card} ${widthClass}`}>
      <div className={styles.content}>
        {/* Row 1: Name + Active Switch */}
        <div className={styles.row}>
          <div className={styles.nameField}>
            <FormField
              label="Название"
              value={name}
              editable={editable}
              required
              placeholder={namePlaceholder}
              onChange={onNameChange}
            />
          </div>
          {showActiveSwitch && (
            <div className={styles.switchField}>
              <FormField
                label={activeSwitchLabel}
                value={isActive}
                type="switch"
                editable={editable}
                description={activeSwitchDescription}
                onChange={onActiveChange}
              />
            </div>
          )}
        </div>

        {/* Row 2: Slug */}
        <FormField
          label="Slug"
          value={slug}
          editable={slugEditable}
          required
          placeholder={slugPlaceholder}
          description={slugDescription}
          onChange={onSlugChange}
        />

        {/* Row 3: Description */}
        <FormField
          label="Описание"
          value={description}
          type="textarea"
          editable={editable}
          placeholder={descriptionPlaceholder}
          onChange={onDescriptionChange}
        />
      </div>
    </div>
  );
}

export default EntityInfoCard;
