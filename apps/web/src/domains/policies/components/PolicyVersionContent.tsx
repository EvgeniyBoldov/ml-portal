/**
 * PolicyVersionContent - Entity-specific content for policy version preview
 * 
 * Displays policy text preview and key metadata
 */
import React from 'react';
import { MetaRow } from '@/shared/ui/MetaRow';
import styles from './PolicyVersionContent.module.css';

export interface PolicyVersionContentProps {
  version: {
    version: number;
    policy_text?: string;
    policy_json?: Record<string, any>;
    hash?: string;
    notes?: string;
    [key: string]: any;
  };
}

export function PolicyVersionContent({ version }: PolicyVersionContentProps) {
  const hasPolicyText = version.policy_text && version.policy_text.trim();
  const hasPolicyJson = version.policy_json && Object.keys(version.policy_json).length > 0;

  return (
    <div className={styles.policyContent}>
      {/* Policy text preview */}
      {hasPolicyText && (
        <div className={styles.policyPreview}>
          <div className={styles.previewLabel}>Политика:</div>
          <pre className={styles.previewText}>
            {version.policy_text!.length > 150
              ? `${version.policy_text!.substring(0, 150)}...`
              : version.policy_text}
          </pre>
        </div>
      )}

      {/* Policy JSON preview */}
      {hasPolicyJson && !hasPolicyText && (
        <div className={styles.policyPreview}>
          <div className={styles.previewLabel}>Конфигурация:</div>
          <pre className={styles.previewText}>
            {JSON.stringify(version.policy_json, null, 2).substring(0, 150)}...
          </pre>
        </div>
      )}

      {/* Additional metadata */}
      <div className={styles.metadata}>
        {version.hash && (
          <MetaRow 
            label="Хеш" 
            value={
              <code className={styles.hash}>
                {version.hash.substring(0, 8)}...
              </code>
            } 
          />
        )}
        
        {version.notes && (
          <div className={styles.notesPreview}>
            <div className={styles.previewLabel}>Заметки:</div>
            <div className={styles.notesText}>
              {version.notes.length > 100
                ? `${version.notes.substring(0, 100)}...`
                : version.notes}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default PolicyVersionContent;
