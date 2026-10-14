import { Badge } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { executionFields } from './modelPageFields';

type ChangeHandler = (key: string, value: unknown) => void;
interface Props {
  identityFields: FieldConfig[];
  connectionFields: FieldConfig[];
  characteristicFields: FieldConfig[];
  usageFields: FieldConfig[];
  characteristicTitle: string;
  modelType: string;
  data: Record<string, unknown>;
  characteristicData: Record<string, unknown>;
  editable: boolean;
  health: string;
  onInfoChange: ChangeHandler;
  onConnectionChange: ChangeHandler;
  onParameterChange: ChangeHandler;
}

export function ModelConfigurationBlocks(props: Props) {
  return (
    <>
      <Block
        title="Основная информация"
        icon="cpu"
        iconVariant="info"
        width="1/2"
        fields={props.identityFields}
        data={props.data}
        editable={props.editable}
        onChange={props.onInfoChange}
        headerActions={
          props.health && props.health !== 'unknown' ? (
            <Badge
              tone={
                props.health === 'healthy'
                  ? 'success'
                  : props.health === 'degraded'
                    ? 'warn'
                    : 'danger'
              }
            >
              {props.health}
            </Badge>
          ) : undefined
        }
      />
      <Block
        title="Подключение"
        icon="server"
        iconVariant="primary"
        width="1/2"
        height="stretch"
        fields={props.connectionFields}
        data={props.data}
        editable={props.editable}
        onChange={props.onConnectionChange}
      />
      <Block
        title={props.characteristicTitle}
        icon="settings"
        iconVariant="warning"
        width="1/2"
        fields={props.characteristicFields}
        data={props.characteristicData}
        editable={props.editable}
        onChange={props.onParameterChange}
      />
      <Block
        title="Использование"
        icon="settings"
        width="1/2"
        fields={props.usageFields}
        data={props.data}
        editable={props.editable}
        onChange={props.onInfoChange}
      />
      <Block title="Настройки запросов" icon="settings" width="full">
        <details>
          <summary>Дополнительные настройки</summary>
          <Block
            title="Ограничения запросов"
            fields={executionFields.filter(
              field =>
                field.key !== 'max_retries' || props.modelType === 'llm_chat'
            )}
            data={props.characteristicData}
            editable={props.editable}
            onChange={props.onParameterChange}
          />
        </details>
      </Block>
    </>
  );
}
