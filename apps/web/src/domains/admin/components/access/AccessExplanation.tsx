import { Link } from 'react-router-dom';
import { Block } from '@/shared/ui';
import type {
  AccessDecisionLayer,
  ExplainAccessResponse,
} from '@/shared/api/rbac';
import { RBAC_LEVEL_LABELS } from '@/domains/admin/shared/rbacLabels';
import { AccessDecisionBadge } from './AccessRuleBadges';
import { ACCESS_PATH } from './accessRules';
import styles from './AccessExplanation.module.css';

const sourceLabels = {
  user: 'Личное правило',
  tenant: 'Правило рабочей группы',
  platform: 'Правило платформы',
  default: 'Системное правило по умолчанию',
};

function layerName(layer: AccessDecisionLayer) {
  return layer.level === 'default'
    ? 'По умолчанию'
    : RBAC_LEVEL_LABELS[layer.level];
}

export function AccessExplanation({
  result,
  currentRuleId,
}: {
  result: ExplainAccessResponse;
  currentRuleId?: string;
}) {
  const source = result.layers.find(layer => layer.effect !== null);
  return (
    <Block title="Решение RBAC" icon="shield-check" iconVariant="primary">
      <div className={styles.result} aria-live="polite">
        <div className={styles.summary}>
          <AccessDecisionBadge effect={result.effect} />
          {source && <strong>{sourceLabels[source.level]}</strong>}
        </div>
        <ol className={styles.layers} aria-label="Уровни в порядке приоритета">
          {result.layers.map(layer => (
            <li
              key={layer.level}
              className={styles.layer}
              data-source={source?.level === layer.level}
            >
              <div className={styles.identity}>
                <strong>{layerName(layer)}</strong>
                {layer.owner_name && <span>{layer.owner_name}</span>}
              </div>
              <div className={styles.decision}>
                {layer.effect ? (
                  <AccessDecisionBadge effect={layer.effect} />
                ) : (
                  <span>Нет правила</span>
                )}
                {source?.level === layer.level && (
                  <span className={styles.source}>Определяет итог</span>
                )}
              </div>
              {layer.rule_id && layer.rule_id !== currentRuleId && (
                <Link to={`${ACCESS_PATH}/${layer.rule_id}`}>
                  Открыть правило
                </Link>
              )}
              {layer.rule_id && layer.rule_id === currentRuleId && (
                <span>Текущее правило</span>
              )}
            </li>
          ))}
        </ol>
      </div>
    </Block>
  );
}
