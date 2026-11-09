import {
  InspectorFieldGroup,
  InspectorFieldRow,
  InspectorJsonBlock,
  InspectorScalar,
  InspectorTextBlock,
} from '@/shared/ui/Inspector';
import type { PlanTaskViewModel } from '@domains/sandbox/planInspection';
import { InspectorEmptyState } from '../InspectorPrimitives';
import styles from './TaskViewer.module.css';

const list = (value: string[]): string => value.join('\n');

function isEmptyObject(value: unknown): boolean {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    Object.keys(value).length === 0
  );
}

export function TaskViewer({
  task,
  variant = 'standard',
}: {
  task?: PlanTaskViewModel;
  variant?: 'standard' | 'agent';
}) {
  if (!task)
    return (
      <InspectorEmptyState message="Описание задачи для этого исполнителя не записано в журнал." />
    );
  const goal =
    variant === 'agent'
      ? [task.objective, task.instructions, task.intent, task.title]
          .map(value => value?.trim())
          .find(value => Boolean(value) && value !== task.taskId)
      : (task.objective ?? task.instructions ?? task.intent);
  if (variant === 'agent') {
    const modeLabels = new Set([
      'Свободный ответ',
      'Текстовый ответ',
      'Структурированный ответ; схема рекомендательная',
      'Обязательный файл',
    ]);
    const expectedOutputs = task.responseFormat
      ? (task.expectedResultDescriptions ??
        task.expectedOutputs.filter(output => !modeLabels.has(output)))
      : task.expectedOutputs;
    const instructionText =
      task.instructions?.trim() !== goal?.trim()
        ? task.instructions
        : undefined;
    return (
      <InspectorFieldGroup>
        {goal ? (
          <InspectorFieldRow label="Цель">
            <p className={styles.goal}>{goal}</p>
          </InspectorFieldRow>
        ) : (
          <InspectorFieldRow label="Цель">Не записана</InspectorFieldRow>
        )}
        {instructionText ? (
          <InspectorFieldRow label="Действия">
            {instructionText.length > 220 ? (
              <details className={styles.instructions}>
                <summary>Показать инструкции</summary>
                <p>{instructionText}</p>
              </details>
            ) : (
              <p className={styles.goal}>{instructionText}</p>
            )}
          </InspectorFieldRow>
        ) : null}
        {task.inputs !== undefined ? (
          <InspectorFieldRow label="Дополнительные параметры">
            {isEmptyObject(task.inputs) ? (
              <InspectorScalar value="Дополнительных параметров нет" />
            ) : (
              <InspectorJsonBlock value={task.inputs} />
            )}
          </InspectorFieldRow>
        ) : null}
        {task.responseFormat ? (
          <InspectorFieldRow label="Формат ответа">
            <InspectorScalar value={task.responseFormat} />
          </InspectorFieldRow>
        ) : null}
        {task.dependencies.length ? (
          <InspectorFieldRow label="Результаты предыдущих задач">
            <p className={styles.goal}>{list(task.dependencies)}</p>
          </InspectorFieldRow>
        ) : null}
        {expectedOutputs.length ? (
          <InspectorFieldRow label="Ожидаемый результат">
            <p className={styles.goal}>{list(expectedOutputs)}</p>
          </InspectorFieldRow>
        ) : null}
      </InspectorFieldGroup>
    );
  }

  return (
    <InspectorFieldGroup>
      {goal ? (
        <InspectorFieldRow label="Цель">
          <InspectorTextBlock text={goal} />
        </InspectorFieldRow>
      ) : null}
      {task.intent ? (
        <InspectorFieldRow label="Назначение">
          <InspectorScalar value={task.intent} />
        </InspectorFieldRow>
      ) : null}
      {task.instructions && task.instructions !== goal ? (
        <InspectorFieldRow label="Инструкции">
          <InspectorTextBlock text={task.instructions} />
        </InspectorFieldRow>
      ) : null}
      {task.inputs !== undefined ? (
        <InspectorFieldRow label="Входные данные">
          <InspectorJsonBlock value={task.inputs} />
        </InspectorFieldRow>
      ) : null}
      {task.dependencies.length ? (
        <InspectorFieldRow label="Зависимости">
          <InspectorTextBlock text={list(task.dependencies)} />
        </InspectorFieldRow>
      ) : null}
      {task.expectedOutputs.length ? (
        <InspectorFieldRow label="Ожидаемый результат">
          <InspectorTextBlock text={list(task.expectedOutputs)} />
        </InspectorFieldRow>
      ) : null}
      {task.status ? (
        <InspectorFieldRow label="Статус задачи">
          <InspectorScalar value={task.status} />
        </InspectorFieldRow>
      ) : null}
    </InspectorFieldGroup>
  );
}
