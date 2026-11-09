import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TraceAccessSnapshot, TraceExecutorStatistic, TraceLimitsView } from '../../../traceProjection';
import { AccessSnapshotViewer, AgentLimitsViewer } from './AccessViewers';

const headers = ['Название', 'Источник', 'Статус', 'Описание'];

function tables() {
  return screen.getAllByRole('table').map((table) => within(table));
}

describe('AccessSnapshotViewer', () => {
  it('renders separate planner agent and tool tables with system tool source', () => {
    render(<AccessSnapshotViewer snapshot={{ entityType: 'planner', agentDescription: 'Описание исполнителя по умолчанию', items: [
      { kind: 'agent', key: 'writer', label: 'Технический автор', status: 'available', description: 'Пишет документацию', children: [] },
      { kind: 'tool', key: 'memory.search', label: 'Поиск в памяти', status: 'available', sourceLabel: 'Система', description: 'Ищет по памяти', children: [] },
      { kind: 'agent', key: 'viewer', label: 'Просмотрщик', status: 'unavailable', reasonCode: 'blocked_by_rbac', reason: 'Нет доступа', children: [] },
    ] }} />);

    expect(screen.getByText('Агенты')).toBeInTheDocument();
    expect(screen.getByText('Инструменты планера')).toBeInTheDocument();
    expect(tables()).toHaveLength(2);
    const [agentTable, toolTable] = tables();
    for (const table of [agentTable, toolTable]) {
      for (const header of headers) expect(table.getByRole('columnheader', { name: header })).toBeInTheDocument();
    }
    expect(agentTable.getByText('Технический автор')).toBeInTheDocument();
    expect(agentTable.getByText('Пишет документацию')).toBeInTheDocument();
    expect(agentTable.getByText('Описание исполнителя по умолчанию')).toBeInTheDocument();
    expect(agentTable.getAllByText('—')).toHaveLength(2);
    expect(agentTable.getByText('Запрещён · RBAC')).toBeInTheDocument();
    expect(toolTable.getByText('Поиск в памяти')).toBeInTheDocument();
    expect(toolTable.getByText('Система')).toBeInTheDocument();
    expect(toolTable.getByLabelText('Источник: Система')).toHaveAttribute('data-source-tone', 'neutral');
    expect(toolTable.getByText('Поиск в памяти').closest('tr')?.lastElementChild).toHaveTextContent('Ищет по памяти');
  });

  it('renders agent source and tool tables, associating each tool with its source', () => {
    const snapshot: TraceAccessSnapshot = {
      entityType: 'agent',
      items: [
        { kind: 'source', key: 'dcbox', label: 'DCbox', status: 'available', description: 'Инвентарь сетевых устройств', children: [
          { kind: 'tool', key: 'dcbox.search', label: 'Поиск устройств', status: 'available', riskLevel: 'low', description: 'Ищет устройства по фильтрам', sourceLabel: 'DCbox API', children: [] },
        ] },
        { kind: 'source', key: 'jira', label: 'Jira', status: 'unavailable', reasonCode: 'blocked_by_rbac', children: [] },
        { kind: 'tool', key: 'file.read', label: 'Чтение файла', status: 'limited', reasonCode: 'missing_credentials', reason: 'Не настроены учётные данные', sourceLabel: 'Система', description: 'Читает приложенный файл', children: [] },
        { kind: 'tool', key: 'jira.search', label: 'Поиск задач', status: 'available', sourceLabel: 'Jira', children: [] },
      ],
    };
    render(<AccessSnapshotViewer snapshot={snapshot} />);

    expect(tables()).toHaveLength(2);
    expect(screen.getByText('Источники данных')).toBeInTheDocument();
    expect(screen.getByText('Инструменты')).toBeInTheDocument();
    const [sourceTable, toolTable] = tables();
    expect(sourceTable.getByText('DCbox')).toBeInTheDocument();
    expect(sourceTable.getByText('Инвентарь сетевых устройств')).toBeInTheDocument();
    expect(sourceTable.getByText('Jira')).toBeInTheDocument();
    expect(sourceTable.queryByText('—')).not.toBeInTheDocument();

    const searchRow = toolTable.getByText('Поиск устройств').closest('tr');
    expect(searchRow).toHaveTextContent('DCbox');
    expect(searchRow).toHaveTextContent('DCbox API');
    expect(screen.getByLabelText('Источник: DCbox API')).toHaveAttribute('data-source-tone', 'info');
    fireEvent.click(within(searchRow as HTMLElement).getByText('Описание'));
    expect(searchRow).toHaveTextContent('Ищет устройства по фильтрам');
    expect(searchRow).toHaveTextContent('Доступен');
    const systemRow = toolTable.getByText('Чтение файла').closest('tr');
    expect(systemRow).toHaveTextContent('Система');
    expect(screen.getByLabelText('Источник: Система')).toHaveAttribute('data-source-tone', 'neutral');
    expect(systemRow).toHaveTextContent('Ограничен · Preflight');
    fireEvent.click(within(systemRow as HTMLElement).getByText('Причина'));
    expect(systemRow).toHaveTextContent('Не настроены учётные данные');
    fireEvent.click(within(systemRow as HTMLElement).getByText('Описание'));
    expect(systemRow).toHaveTextContent('Читает приложенный файл');
    expect(screen.getByLabelText('Источник: Jira')).toHaveAttribute('data-source-tone', 'success');
    expect(sourceTable.queryByText('dcbox')).not.toBeInTheDocument();
  });

  it('renders preflight tools and an empty state when no snapshot was recorded', () => {
    const { rerender } = render(<AccessSnapshotViewer snapshot={{ entityType: 'preflight', items: [
      { kind: 'tool', key: 'memory.search', label: 'Поиск в памяти', status: 'unavailable', reasonCode: 'tool_unavailable', sourceLabel: 'Memory provider', description: 'Поиск фактов', children: [] },
    ] }} />);
    expect(screen.getByText('Инструменты проверки')).toBeInTheDocument();
    expect(tables()).toHaveLength(1);
    expect(screen.getByText('Поиск в памяти')).toBeInTheDocument();
    expect(screen.getByText('Недоступен · Preflight')).toBeInTheDocument();
    expect(screen.getByText('Memory provider')).toBeInTheDocument();
    expect(screen.getByLabelText('Источник: Memory provider')).toHaveAttribute('data-source-tone', 'neutral');
    expect(screen.getByText('Поиск фактов')).toBeInTheDocument();
    rerender(<AccessSnapshotViewer />);
    expect(screen.getByText('Доступ для этого запуска не записан.')).toBeInTheDocument();
  });
});

describe('AgentLimitsViewer', () => {
  it('combines measured token use with configured limits without duplicate metric rows', () => {
    const limits: TraceLimitsView = { rows: [
      { key: 'llm_calls', label: 'Вызовы LLM', used: 2, limit: 3, remaining: 1, status: 'warning' },
      { key: 'tokens_total', label: 'Всего токенов', used: 120, limit: 200, remaining: 80, status: 'ok' },
      { key: 'context_window', label: 'Окно контекста', limit: 32000, status: 'neutral' },
    ] };
    const statistics: TraceExecutorStatistic[] = [
      { key: 'tokens_in', label: 'Входные токены', value: 100 },
      { key: 'tokens_out', label: 'Выходные токены', value: 50 },
      { key: 'tokens_total', label: 'Всего токенов', value: 150 },
    ];
    render(<AgentLimitsViewer limits={limits} statistics={statistics} />);

    const table = within(screen.getByRole('table'));
    expect(table.getByText('Входные токены').closest('tr')).toHaveTextContent('100');
    expect(table.getByText('Выходные токены').closest('tr')).toHaveTextContent('50');
    const totalRows = table.getAllByText('Всего токенов');
    expect(totalRows).toHaveLength(1);
    expect(totalRows[0].closest('tr')).toHaveTextContent('150');
    expect(totalRows[0].closest('tr')).toHaveTextContent('200');
    const contextRow = table.getByText('Окно контекста').closest('tr');
    expect(contextRow).toHaveTextContent(/32.?000/);
    expect(within(contextRow as HTMLElement).getAllByText('Расход не записан')).toHaveLength(1);
    expect(table.getByText('Вызовы LLM').closest('tr')).toHaveTextContent('2');
    expect(table.getByText('Близко к лимиту')).toBeVisible();
  });

  it('shows budget warnings directly without an explanatory disclosure', () => {
    render(<AgentLimitsViewer limits={{ rows: [
      { key: 'wall_time_ms', label: 'Учтено бюджетом', used: 1200, limit: 2000, remaining: 800, status: 'warning' },
    ] }} statistics={[]} />);
    const row = screen.getByText('Учтено бюджетом').closest('tr');
    expect(within(row as HTMLElement).getByText('Близко к лимиту')).toBeVisible();
    expect(within(row as HTMLElement).queryByText('Что означает учтённое время')).not.toBeInTheDocument();
    expect(row?.querySelector('details')).toBeNull();
  });

  it('shows reached/overrun state and remaining values inline without inventing use or limits', () => {
    render(<AgentLimitsViewer limits={{ rows: [
      { key: 'tokens_in', label: 'Входные токены', used: 100, limit: 100, remaining: 0, status: 'exceeded' },
      { key: 'tool_calls', label: 'Вызовы инструментов', used: 15, limit: 10, remaining: 0, status: 'exceeded' },
      { key: 'llm_calls', label: 'Вызовы LLM', used: 5, limit: 10, remaining: 5, status: 'ok' },
    ] }} statistics={[{ key: 'tokens_out', label: 'Выходные токены', value: 7 }]} />);
    const rows = screen.getAllByRole('row');
    const text = rows.map(row => row.textContent).join(' ');
    expect(text).toContain('Лимит достигнут');
    expect(text).toContain('Перерасход');
    expect(text).toContain('Перерасход: +5');
    expect(text).toContain('Остаток: 5');
    expect(screen.queryByText('В норме')).not.toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Использование лимита: Вызовы LLM' })).toHaveAttribute('data-tone', 'success');
    expect(text).toContain('Лимит не записан');
    const overrunBar = screen.getByRole('progressbar', { name: 'Использование лимита: Вызовы инструментов' });
    expect(overrunBar).toHaveAttribute('value', '100');
    expect(overrunBar).toHaveAttribute('data-tone', 'danger');
    expect(screen.queryByRole('progressbar', { name: 'Использование лимита: Выходные токены' })).not.toBeInTheDocument();
    const unboundedRow = screen.getByText('Выходные токены').closest('tr');
    expect(within(unboundedRow as HTMLElement).getAllByText('Лимит не записан')).toHaveLength(1);
    expect(within(unboundedRow as HTMLElement).queryByRole('progressbar')).not.toBeInTheDocument();
  });
});
