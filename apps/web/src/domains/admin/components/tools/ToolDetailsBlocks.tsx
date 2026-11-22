import { Link } from 'react-router-dom';

import type {
  DiscoveredToolDetail,
  ToolResultDelivery,
  ToolRisk,
} from '@/shared/api/discoveredTools';
import { Badge, Block, JSONDisplay, Select, Toggle } from '@/shared/ui';
import {
  deliveryLabels,
  providerKind,
  providerName,
  riskEditOptions,
  toolRisk,
  toolSourceLabels,
} from '@/domains/admin/shared/toolCatalog';
import styles from './ToolDetailsBlocks.module.css';

export type ToolSettings = {
  risk_level: ToolRisk | null;
  result_delivery: ToolResultDelivery;
};

export function ToolSchemas({ tool }: { tool: DiscoveredToolDetail }) {
  const schemas = [
    {
      title: 'Входные параметры',
      value: tool.input_schema,
      description: 'Параметры, объявленные провайдером для вызова инструмента.',
      empty: 'Провайдер не объявил схему входных параметров.',
    },
    {
      title: 'Объявленная схема ответа',
      value: tool.output_schema,
      description: 'Формат ответа по контракту провайдера.',
      empty: 'Провайдер не объявил схему ответа.',
    },
    {
      title: 'Наблюдаемая структура ответа',
      value: tool.observed_data_schema,
      description:
        'Поля и типы из первого зафиксированного ответа. Значения полей не сохраняются в реестре.',
      empty: 'Структура ответа ещё не зафиксирована.',
    },
  ];

  return schemas.map(({ title, value, description, empty }) => (
    <Block key={title} title={title} icon="file">
      <div className={styles.stack}>
        <p className={styles.hint}>{value ? description : empty}</p>
        {value && <JSONDisplay value={JSON.stringify(value, null, 2)} />}
      </div>
    </Block>
  ));
}

export function ToolOrigin({ tool }: { tool: DiscoveredToolDetail }) {
  const sourceTypes = toolSourceLabels(tool);
  return (
    <Block
      title="Происхождение"
      icon="server"
      width="1/2"
      headerLabels={
        tool.runtime_managed ? (
          <Badge tone="info">Системный</Badge>
        ) : (
          !tool.is_active && <Badge tone="warn">Не обнаружен</Badge>
        )
      }
    >
      <div className={styles.stack}>
        {tool.description && (
          <p className={styles.description}>{tool.description}</p>
        )}
        <dl className={styles.meta}>
          <div>
            <dt>Провайдер</dt>
            <dd>
              {tool.provider_instance_id ? (
                <Link to={`/admin/connectors/${tool.provider_instance_id}`}>
                  {providerName(tool)}
                </Link>
              ) : (
                providerName(tool)
              )}
              <span className={styles.hint}> · {providerKind(tool)}</span>
            </dd>
          </div>
          <div>
            <dt>Типы данных</dt>
            <dd className={styles.sourceTypes}>
              {sourceTypes.length > 0
                ? sourceTypes.map(type => <Badge key={type}>{type}</Badge>)
                : 'Связанные типы не определены'}
            </dd>
          </div>
          {!tool.runtime_managed && (
            <div>
              <dt>Последний раз обнаружен</dt>
              <dd>
                {tool.last_seen_at ? (
                  <time dateTime={tool.last_seen_at}>
                    {new Date(tool.last_seen_at).toLocaleString('ru-RU')}
                  </time>
                ) : (
                  'Нет данных'
                )}
              </dd>
            </div>
          )}
        </dl>
        {tool.source === 'mcp' && (
          <p className={styles.hint}>
            Типы данных берутся из активных коннекторов, связанных с этим
            провайдером.
          </p>
        )}
      </div>
    </Block>
  );
}

interface ToolSettingsBlockProps {
  tool: DiscoveredToolDetail;
  changes?: ToolSettings;
  saving: boolean;
  onRiskChange: (risk: ToolRisk | null) => void;
  onDeliveryChange: (delivery: ToolResultDelivery) => void;
}

export function ToolSettingsBlock({
  tool,
  changes,
  saving,
  onRiskChange,
  onDeliveryChange,
}: ToolSettingsBlockProps) {
  if (tool.runtime_managed) {
    return (
      <Block title="Доступность" icon="settings" width="1/2">
        <p className={styles.hint}>
          Runtime предоставляет операцию агенту, когда в рабочем пространстве
          есть подходящие данные.
        </p>
      </Block>
    );
  }
  const displayedRisk = toolRisk(tool);
  return (
    <Block title="Настройки выполнения" icon="settings" width="1/2">
      <div className={styles.stack}>
        <div className={styles.field}>
          {changes ? (
            <>
              <label htmlFor="tool-risk">Классификация риска</label>
              <Select
                id="tool-risk"
                value={changes.risk_level ?? ''}
                options={[
                  {
                    value: '',
                    label:
                      tool.source === 'mcp'
                        ? 'Требует классификации'
                        : 'По умолчанию',
                  },
                  ...riskEditOptions,
                ]}
                onChange={value =>
                  onRiskChange(
                    value === 'safe' || value === 'risky' ? value : null
                  )
                }
                disabled={saving}
              />
            </>
          ) : (
            <>
              <strong>Классификация риска</strong>
              <div>
                <Badge tone={displayedRisk.tone}>{displayedRisk.label}</Badge>
              </div>
            </>
          )}
          {tool.source === 'mcp' && (
            <p className={styles.hint}>
              Операции без классификации не предлагаются агентам. Рискованные
              операции требуют подтверждения.
            </p>
          )}
          {tool.source === 'local' && (
            <p className={styles.hint}>
              По умолчанию применяется классификация из описания встроенного
              инструмента.
            </p>
          )}
        </div>
        <div className={styles.field}>
          {changes ? (
            <Toggle
              label="Сохранять ответ как набор данных"
              checked={changes.result_delivery === 'store'}
              disabled={saving}
              onChange={checked =>
                onDeliveryChange(checked ? 'store' : 'direct')
              }
            />
          ) : (
            <>
              <strong>Доставка ответа</strong>
              <div>
                <Badge
                  tone={tool.result_delivery === 'store' ? 'info' : 'neutral'}
                >
                  {deliveryLabels[tool.result_delivery]}
                </Badge>
              </div>
            </>
          )}
          <p className={styles.hint}>
            Набор данных сохраняется для конкретного запуска и доступен в его
            инспекторе. При выключенной настройке ответ обычно передаётся в
            контекст вызова.
          </p>
        </div>
      </div>
    </Block>
  );
}
