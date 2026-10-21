import { fireEvent, render, screen } from '@testing-library/react';
import { useChatScroll } from './useChatScroll';
import type { ChatTimelineMessage } from '../types';

function Harness({ chatId = 'chat', text }: { chatId?: string; text: string }) {
  const messages: ChatTimelineMessage[] = [
    { id: 'answer', role: 'assistant', content: text, createdAt: 'now' },
  ];
  const { historyRef, contentRef, hasUnread, scrollToBottom } = useChatScroll(
    chatId,
    messages
  );
  return (
    <>
      <div ref={historyRef} data-testid="history">
        <div ref={contentRef}>{text}</div>
      </div>
      {hasUnread && <button onClick={scrollToBottom}>Новые сообщения</button>}
    </>
  );
}

it('follows streamed content with an unchanged message count, without pulling the user away from history', () => {
  const view = render(<Harness text="Начало" />);
  const container = screen.getByTestId('history');
  let height = 600;
  Object.defineProperties(container, {
    scrollHeight: { get: () => height },
    clientHeight: { value: 200 },
  });
  view.rerender(<Harness text="Более длинный ответ" />);
  expect(container.scrollTop).toBe(600);
  height = 900;
  view.rerender(<Harness text="Ответ продолжает расти" />);
  expect(container.scrollTop).toBe(900);

  container.scrollTop = 100;
  fireEvent.scroll(container);
  height = 1200;
  view.rerender(<Harness text="Следующая часть ответа" />);
  expect(container.scrollTop).toBe(100);
  fireEvent.click(screen.getByRole('button', { name: 'Новые сообщения' }));
  expect(container.scrollTop).toBe(1200);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();

  container.scrollTop = 100;
  fireEvent.scroll(container);
  view.rerender(<Harness chatId="another" text="Другой чат" />);
  expect(container.scrollTop).toBe(1200);
});
