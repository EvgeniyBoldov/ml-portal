import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ChatAnswerCard from './ChatAnswerCard';

describe('ChatAnswerCard', () => {
  it('shows a completed answer and run failure as separate information', () => {
    render(
      <ChatAnswerCard
        text="Частичный ответ готов."
        isRunning={false}
        error="Планировщик завершился с ошибкой."
      />
    );

    expect(screen.getByText('Частичный ответ готов.')).toBeInTheDocument();
    expect(screen.getByText('Планировщик завершился с ошибкой.')).toBeInTheDocument();
  });
});
