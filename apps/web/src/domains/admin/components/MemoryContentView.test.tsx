import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import MemoryContentView, { memoryContentPreview } from './MemoryContentView';

afterEach(cleanup);
const examples: Array<[string, Record<string, unknown>, string[]]> = [
  ['term', { definition: 'Период проведения работ' }, ['Определение', 'Период проведения работ']],
  ['description', { summary: 'Описание сервиса', details: ['Часть A', 'Часть B'] }, ['Описание', 'Подробности', 'Часть B']],
  ['relationship', { summary: 'Команда обслуживает проект' }, ['Описание', 'Команда обслуживает проект']],
  ['rule', { statement: 'Согласуйте работы', effect: 'require', conditions: ['При изменении'], required_approvals: ['Руководитель'],
    required_checks: ['Проверьте резерв'], exceptions: ['Авария'], consequences: ['Регистрация'] },
    ['Формулировка', 'Обязательно', 'Условия', 'Согласования', 'Обязательные проверки', 'Исключения', 'Последствия']],
  ['constraint', { statement: 'Не более пяти', conditions: ['Днём'], limits: ['Пять'], exceptions: ['Ночью'], consequences: ['Отказ'] },
    ['Формулировка', 'Ограничения', 'Пять', 'Исключения', 'Последствия']],
  ['decision', { decision: 'Использовать резерв', conditions: ['Сбой'], rationale: ['Надёжность'], consequences: ['Перенос'] },
    ['Решение', 'Условия', 'Обоснование', 'Последствия']],
  ['procedure', { goal: 'Обновить систему', applicability_conditions: ['Окно работ'], required_approvals: ['Заказчик'], prechecks: ['Копия готова'],
    steps: [{ order: 1, instruction: 'Обновить', expected_result: 'Новая версия', confirmation_required: true }],
    verification: ['Сервис работает'], rollback: { mode: 'steps', steps: ['Вернуть копию'] }, exceptions: ['Авария'] },
    ['Цель', 'Условия применимости', 'Предварительные проверки', 'Шаг 1', 'Обновить', 'Новая версия', 'Требуется', 'Проверка результата', 'Вернуть копию']],
];

describe('Типизированное содержание памяти', () => {
  it.each(examples)('показывает все поля типа %s', (type, content, expected) => {
    render(<MemoryContentView type={type} content={content} />);
    expected.forEach((text) => expect(screen.getByText(text)).toBeInTheDocument());
  });
  it('показывает откат без действий с причиной', () => {
    render(<MemoryContentView type="procedure" content={{ goal: 'Осмотр', prechecks: ['Доступ'],
      steps: [{ instruction: 'Осмотреть', expected_result: 'Запись', confirmation_required: false }], verification: ['Запись создана'],
      rollback: { mode: 'not_applicable', reason: 'Состояние не меняется' } }} />);
    expect(screen.getByText('Откат не применим')).toBeInTheDocument();
    expect(screen.getByText('Состояние не меняется')).toBeInTheDocument();
  });
  it('в режиме JSON показывает только канонический объект', () => {
    const content = { statement: 'Согласовать', effect: 'forbid', conditions: ['Всегда'] };
    render(<MemoryContentView type="rule" content={content} jsonMode />);
    expect(document.querySelector('pre')?.textContent).toBe(JSON.stringify(content, null, 2));
    expect(screen.queryByText('Формулировка')).not.toBeInTheDocument();
  });
  it('обзор ограничивает содержание 24 строками и отмечает продолжение', () => {
    const preview = memoryContentPreview('description', { summary: 'Длинный документ', details: Array.from({ length: 40 }, (_, i) => `Строка ${i}`) });
    expect(preview.split('\n')).toHaveLength(25);
    expect(preview.endsWith('\n…')).toBe(true);
    expect(preview).not.toContain('Строка 39');
  });
});
