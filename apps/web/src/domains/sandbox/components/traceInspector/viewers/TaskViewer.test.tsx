import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PlanTaskViewModel } from '@domains/sandbox/planInspection';
import { TaskViewer } from './TaskViewer';

const task: PlanTaskViewModel = {
  taskId: 'opaque-task-id',
  kind: 'agent',
  title: 'opaque-task-id',
  intent: 'Получить данные',
  objective: 'Получить данные о сервисе',
  instructions: 'Получить данные о сервисе',
  executor: 'inventory.netbox',
  status: 'Готово',
  dependencies: [],
  expectedOutputs: ['Структурированный ответ; схема рекомендательная'],
};

describe('TaskViewer', () => {
  it('shows a concise agent task without duplicate intent or lifecycle status', () => {
    render(<TaskViewer task={task} variant="agent" />);

    expect(screen.getByText('Цель')).toBeInTheDocument();
    expect(screen.getByText('Получить данные о сервисе')).toBeInTheDocument();
    expect(screen.queryByText('Назначение')).not.toBeInTheDocument();
    expect(screen.queryByText('Статус задачи')).not.toBeInTheDocument();
    expect(screen.queryByText('Готово')).not.toBeInTheDocument();
    expect(screen.queryByText('opaque-task-id')).not.toBeInTheDocument();
    expect(screen.getByText('Ожидаемый результат')).toBeInTheDocument();
  });

  it('falls back from an empty objective to instructions without repeating them', () => {
    render(
      <TaskViewer
        task={{
          ...task,
          objective: '',
          instructions: 'Собрать актуальные данные',
          intent: 'Собрать актуальные данные',
          title: 'Обновление инвентаря',
        }}
        variant="agent"
      />
    );

    expect(screen.getByText('Собрать актуальные данные')).toBeInTheDocument();
    expect(screen.getByText('Цель')).toBeInTheDocument();
    expect(screen.queryByText('Действия')).not.toBeInTheDocument();
  });

  it('explains that an explicitly empty input has no extra parameters', () => {
    const { rerender } = render(
      <TaskViewer task={{ ...task, inputs: {} }} variant="agent" />
    );
    expect(
      screen.getByText('Дополнительных параметров нет')
    ).toBeInTheDocument();

    rerender(<TaskViewer task={task} variant="agent" />);
    expect(
      screen.queryByText('Дополнительных параметров нет')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('Дополнительные параметры')
    ).not.toBeInTheDocument();
  });

  it('shows the requested response format separately from expected work', () => {
    render(
      <TaskViewer
        task={{
          ...task,
          responseFormat: 'Структурированные данные',
          expectedOutputs: ['Структурированный ответ; схема рекомендательная'],
          expectedResultDescriptions: ['Найти и сохранить устройства'],
        }}
        variant="agent"
      />
    );

    expect(screen.getByText('Формат ответа')).toBeInTheDocument();
    expect(screen.getByText('Структурированные данные')).toBeInTheDocument();
    expect(screen.getByText('Ожидаемый результат')).toBeInTheDocument();
    expect(
      screen.getByText('Найти и сохранить устройства')
    ).toBeInTheDocument();
  });

  it('renders the agent goal as readable text and expands long instructions in place', () => {
    const instructions = `Шаг 1. Получить перечень устройств.\n${'Подробно проверить состояние каждого устройства. '.repeat(8)}`;
    render(
      <TaskViewer
        task={{
          ...task,
          objective: 'Проверить устройства в сети',
          instructions,
        }}
        variant="agent"
      />
    );

    expect(screen.getByText('Проверить устройства в сети').tagName).toBe('P');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    const disclosure = screen
      .getByText('Показать инструкции')
      .closest('details');
    expect(disclosure).not.toHaveAttribute('open');
    expect(disclosure?.querySelector('p')).not.toBeVisible();
    fireEvent.click(screen.getByText('Показать инструкции'));
    expect(disclosure?.querySelector('p')).toBeVisible();
  });

  it('keeps zero and false values in recorded parameters', () => {
    render(
      <TaskViewer
        task={{ ...task, inputs: { retries: 0, enabled: false } }}
        variant="agent"
      />
    );

    expect(screen.getByText(/retries/i)).toBeInTheDocument();
    expect(screen.getByText('false')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('keeps standard task presentation for special executors', () => {
    render(<TaskViewer task={task} />);

    expect(screen.getByText('Назначение')).toBeInTheDocument();
    expect(screen.getByText('Статус задачи')).toBeInTheDocument();
    expect(screen.getByText('Готово')).toBeInTheDocument();
  });
});
