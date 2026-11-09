import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TraceAgentResponseView } from '../../../traceProjection';
import { AgentResultViewer } from './AgentResultViewer';

const response = (value: Partial<TraceAgentResponseView> = {}): TraceAgentResponseView => ({
  hasStructuredData: false,
  needs: [],
  artifacts: [],
  sources: [],
  actions: [],
  diagnostics: [],
  ...value,
});

describe('AgentResultViewer', () => {
  it('shows answer with arbitrary structured values including false, zero, null and empty structures', () => {
    render(<AgentResultViewer response={response({
      answer: 'Найдены две записи.',
      hasStructuredData: true,
      structuredData: {
        enabled: false,
        attempts: 0,
        optional_value: null,
        empty_object: {},
        empty_list: [],
      },
    })} />);

    expect(screen.getByText('Найдены две записи.')).toBeInTheDocument();
    expect(screen.getByText('Структурированные данные')).toBeInTheDocument();
    expect(screen.getByText('false')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('null')).toBeInTheDocument();
    expect(screen.getByText('Пустой объект')).toBeInTheDocument();
    expect(screen.getByText('Пустой список')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть все данные' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Понятный вид' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
    expect(screen.getByRole('button', { name: 'JSON' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/"enabled": false/)).toBeInTheDocument();
  });

  it('keeps the full human view readable and provides access to deeply nested values', () => {
    render(<AgentResultViewer response={response({
      hasStructuredData: true,
      structuredData: { inventory: { network: { devices: [{ name: 'router-deep-1' }] } } },
    })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Открыть все данные' }));
    const dialog = within(screen.getByRole('dialog'));
    const nested = dialog.getByText('Показать вложенные данные · 1 полей');
    fireEvent.click(nested);
    expect(dialog.getByText('Devices')).toBeInTheDocument();
    expect(dialog.getByText('router-deep-1')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Понятный вид' })).toHaveAttribute('aria-pressed', 'true');
    expect(dialog.getByRole('button', { name: 'JSON' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('localizes known structured field names without changing recorded values', () => {
    render(<AgentResultViewer response={response({
      hasStructuredData: true,
      structuredData: {
        notes: 'SQL: select * from inventory',
        source_total: 12,
        data_completeness: 'partial',
        device_types: ['router'],
        total_devices: 8,
        count: 2,
        Type: 'router',
        'Missing types': ['switch'],
        'Data completeness': 'partial',
      },
    })} />);

    for (const label of ['Примечания', 'Всего в источнике', 'Типы устройств', 'Всего устройств', 'Количество']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getAllByText('Полнота данных')).toHaveLength(2);
    expect(screen.getByText('Тип')).toBeInTheDocument();
    expect(screen.getByText('Недостающие типы')).toBeInTheDocument();
    expect(screen.getByText('SQL: select * from inventory')).toBeInTheDocument();
    expect(screen.getAllByText('partial')).toHaveLength(2);
  });

  it('puts short scalar values first, groups complex fields next, and collapses long text full width', () => {
    const note = 'Источник вернул неполный список устройств. '.repeat(8);
    render(<AgentResultViewer response={response({
      hasStructuredData: true,
      structuredData: {
        notes: note,
        total_devices: 24,
        enabled: false,
        inventory: { status: 'partial', count: 0 },
      },
    })} />);

    const scalarLabel = screen.getByText('Всего устройств');
    const groupLabel = screen.getByText('Inventory');
    const noteSummary = screen.getByText('Примечания · Показать полный текст');
    const noteDetails = noteSummary.closest('details');
    expect(noteDetails).not.toHaveAttribute('open');
    expect(groupLabel.compareDocumentPosition(noteSummary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(scalarLabel.compareDocumentPosition(groupLabel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(noteDetails?.querySelector('p')).toHaveTextContent(note.trim());
    fireEvent.click(noteSummary);
    expect(noteDetails).toHaveAttribute('open');
  });

  it('renders record arrays as a bounded responsive table with a full data action', () => {
    const rows = Array.from({ length: 13 }, (_, index) => ({ device: `router-${index}`, active: index !== 0 }));
    render(<AgentResultViewer response={response({ hasStructuredData: true, structuredData: rows })} />);

    const table = screen.getAllByRole('table')[0];
    expect(within(table).getByRole('columnheader', { name: 'Device' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Active' })).toBeInTheDocument();
    expect(screen.getByText('router-9')).toBeInTheDocument();
    const moreRecords = screen.getByText('Показать ещё 3 записей');
    expect(moreRecords.closest('details')).not.toHaveAttribute('open');
    fireEvent.click(moreRecords);
    expect(screen.getByText('router-10')).toBeInTheDocument();
    expect(screen.getByText('router-12')).toBeInTheDocument();
  });

  it('renders nested record arrays as separate groups and discloses remaining groups', () => {
    const rows = Array.from({ length: 12 }, (_, index) => ({
      device: `router-${index + 1}`,
      details: { active: index !== 0, count: index },
    }));
    render(<AgentResultViewer response={response({ hasStructuredData: true, structuredData: rows })} />);

    expect(screen.getByText('Запись 1')).toBeInTheDocument();
    expect(screen.getAllByText('Active')).toHaveLength(12);
    const moreGroups = screen.getByText('Показать ещё 2 записей');
    expect(moreGroups.closest('details')).not.toHaveAttribute('open');
    fireEvent.click(moreGroups);
    expect(screen.getByText('Запись 12')).toBeInTheDocument();
    expect(screen.getByText('router-12')).toBeInTheDocument();
  });

  it('shows registered files and safe source links without exposing artifact identifiers', () => {
    render(<AgentResultViewer response={response({
      artifacts: [{ artifactId: 'artifact-1', fileName: 'devices.csv', contentType: 'text/csv', sizeBytes: 2048, description: 'Таблица устройств' }],
      sources: [
        { label: 'Каталог устройств', href: 'https://inventory.example/devices' },
        { label: 'Неизвестная схема', href: 'javascript:alert(1)' },
      ],
    })} />);

    expect(screen.getByRole('link', { name: 'devices.csv' })).toHaveAttribute('href', '/api/v1/files/artifact-1/download');
    expect(screen.getByText('Таблица устройств')).toBeInTheDocument();
    expect(screen.getByText(/2\.0 КБ/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Каталог устройств' })).toHaveAttribute('href', 'https://inventory.example/devices');
    expect(screen.getByText('Неизвестная схема').closest('a')).toBeNull();
    expect(screen.queryByText('artifact-1')).not.toBeInTheDocument();
  });

  it('shows needs, limitation, interaction, diagnostics, and phase sufficiency only when present', () => {
    render(<AgentResultViewer response={response({
      completion: 'needs',
      outcome: 'needs_dependency',
      sufficientForPhase: false,
      needs: [{ description: 'Выберите площадку', kind: 'decision', required: true }],
      limitation: { message: 'Доступ к системе не настроен.', actionLabel: 'Запросить доступ' },
      interaction: { kind: 'confirmation', question: 'Разрешить изменение?', responseTypeLabel: 'Да или нет', options: ['Да', 'Нет'] },
      actions: [{ label: 'netbox.device.list', retrieval: true, inlineComplete: false }],
      diagnostics: [{
        label: 'Данные отличаются от рекомендованного формата',
        count: 2,
        details: ['Некоторые поля не совпали с рекомендуемым описанием. Значения сохранены в результате.'],
      }],
      failureMessage: 'Один из вызовов завершился с ошибкой.',
    })} />);

    expect(screen.getByText('Выберите площадку')).toBeInTheDocument();
    expect(screen.getByText(/Обязательно/)).toBeInTheDocument();
    expect(screen.getByText('Доступ к системе не настроен.')).toBeInTheDocument();
    expect(screen.getByText('Запросить доступ')).toBeInTheDocument();
    expect(screen.getByText('Разрешить изменение?')).toBeInTheDocument();
    expect(screen.getByText('Формат ответа: Да или нет')).toBeInTheDocument();
    expect(screen.getByText('Да')).toBeInTheDocument();
    expect(screen.getByText('Нет')).toBeInTheDocument();
    expect(screen.queryByText('netbox.device.list')).not.toBeInTheDocument();
    expect(screen.queryByText(/Обработка была частичной/)).not.toBeInTheDocument();
    expect(screen.getByText('Данные отличаются от рекомендованного формата')).toBeInTheDocument();
    expect(screen.getByText('Что это значит')).toBeInTheDocument();
    expect(screen.getByText(/Значения сохранены в результате/)).toBeInTheDocument();
    expect(screen.getByText('Записанного результата недостаточно для следующего этапа.')).toBeInTheDocument();
    expect(screen.getByText('Один из вызовов завершился с ошибкой.')).toBeInTheDocument();
    expect(screen.queryByText('fulfilled')).not.toBeInTheDocument();
    expect(screen.queryByText('needs_dependency')).not.toBeInTheDocument();
  });

  it('does not repeat tool actions in the result when they are already shown in the trace', () => {
    render(<AgentResultViewer response={response({ actions: [
      { label: 'netbox.device.list', retrieval: true, inlineComplete: false },
    ] })} />);
    expect(screen.getByText('Исполнитель не записал содержательный результат.')).toBeInTheDocument();
    expect(screen.queryByText('netbox.device.list')).not.toBeInTheDocument();
    expect(screen.queryByText(/Как получен результат/)).not.toBeInTheDocument();
  });

  it('orders contract sections and keeps needs prominent with kind and required badges', () => {
    render(<AgentResultViewer response={response({
      answer: 'Найдены устройства.',
      needs: [{ description: 'Укажите площадку', kind: 'decision', required: true }],
      hasStructuredData: true,
      structuredData: { count: 0 },
      artifacts: [{ artifactId: 'artifact-2', fileName: 'devices.csv', contentType: 'text/csv', sizeBytes: 10 }],
      sources: [{ label: 'Инвентарь', href: 'https://inventory.example' }],
      diagnostics: [{ label: 'Нужно проверить формат', count: 1, details: ['Результат доступен в исходном виде.'] }],
    })} />);

    expect(screen.getByText('Решение')).toBeInTheDocument();
    expect(screen.getByText('Обязательно')).toBeInTheDocument();
    const headings = screen.getAllByRole('heading', { level: 4 }).map((heading) => heading.textContent);
    const expectedOrder = ['Ответ', 'Для продолжения нужно', 'Структурированные данные', 'Файлы', 'Источники', 'Замечания к формату'];
    expect(expectedOrder.map((title) => headings.indexOf(title))).toEqual([...expectedOrder.keys()].map((index) => index));
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('shows ten interaction choices first and discloses every remaining choice on demand', () => {
    const options = Array.from({ length: 15 }, (_, index) => `Вариант ${index + 1}`);
    render(<AgentResultViewer response={response({
      interaction: { kind: 'input', question: 'Выберите вариант', options },
    })} />);

    expect(screen.getByText('Вариант 1')).toBeInTheDocument();
    expect(screen.getByText('Вариант 10')).toBeInTheDocument();
    expect(screen.getByText('Показать ещё 5').closest('details')).not.toHaveAttribute('open');
    fireEvent.click(screen.getByText('Показать ещё 5'));
    expect(screen.getByText('Вариант 11')).toBeInTheDocument();
    expect(screen.getByText('Вариант 15')).toBeInTheDocument();
  });

  it('does not render empty default sections or repeat ordinary completed status', () => {
    render(<AgentResultViewer response={response({ completion: 'fulfilled', outcome: 'completed' })} />);

    expect(screen.getByText('Исполнитель не записал содержательный результат.')).toBeInTheDocument();
    expect(screen.queryByText('Выполненные действия')).not.toBeInTheDocument();
    expect(screen.queryByText('Источники')).not.toBeInTheDocument();
    expect(screen.queryByText('completed')).not.toBeInTheDocument();
    expect(screen.queryByText('fulfilled')).not.toBeInTheDocument();
  });
});
