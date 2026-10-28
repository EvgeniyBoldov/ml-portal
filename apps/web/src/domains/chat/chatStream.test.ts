import { describe, expect, it, vi } from 'vitest';
import {
  appendRuntimeProgress,
  consumeChatStream,
  type ChatStreamEvent,
} from './chatStream';
import type { ChatRuntimeProgress } from './types';

function response(text: string) {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text));
        controller.close();
      },
    })
  );
}
function frame(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

describe('consumeChatStream', () => {
  it('treats reattach state as a snapshot, not a second run_started event', async () => {
    const events: ChatStreamEvent[] = [];
    await consumeChatStream(
      response(
        frame('state', {
          run_id: 'run', status: 'running', stage: 'executing',
          activity: { run_id: 'run', stage: 'executing', action: 'tool_call', description: 'Выполняю инструмент' },
        }) + frame('final', { message_id: 'answer', content: 'Готово', status: 'completed' })
      ),
      event => { events.push(event); }
    );
    expect(events[0]).toMatchObject({
      type: 'state', runId: 'run', status: 'running', stage: 'executing',
      activity: { action: 'tool_call', description: 'Выполняю инструмент' },
    });
    expect(events.some(event => event.type === 'run_started')).toBe(false);
    expect(events.at(-1)).toMatchObject({ type: 'final', final: { status: 'completed' } });
  });

  it('parses normalized stage activity separately from lifecycle state', async () => {
    const events: ChatStreamEvent[] = [];
    await consumeChatStream(
      response(frame('stage', { activity: {
        run_id: 'run', stage: 'planning', action: 'planner_iteration_start',
        description: 'Формирую план выполнения', outcome: null,
      } }) + frame('final', { message_id: 'id', content: 'done' })),
      event => { events.push(event); }
    );
    expect(events[0]).toMatchObject({ type: 'stage', activity: { stage: 'planning', action: 'planner_iteration_start' } });
  });

  it('accumulates deltas and uses authoritative final content and metadata', async () => {
    const events: ChatStreamEvent[] = [];
    const terminal = await consumeChatStream(
      response(
        'event: delta\ndata: черновик\n\nevent: delta\ndata: !\n\n' +
          frame('final', {
            message_id: 'answer',
            content: 'Итог',
            sources: [{ source_id: 's' }],
            attachments: [{ artifact_id: 'a' }],
          }) +
          'data: [DONE]\n\n'
      ),
      event => {
        events.push(event);
      }
    );
    expect(terminal).toBe('final');
    expect(events.slice(0, 2)).toEqual([
      { type: 'delta', content: 'черновик' },
      { type: 'delta', content: 'черновик!' },
    ]);
    expect(events[2]).toMatchObject({
      type: 'final',
      final: {
        messageId: 'answer',
        content: 'Итог',
        sources: [{ source_id: 's' }],
        attachments: [{ artifact_id: 'a' }],
      },
    });
  });

  it('accepts an empty final instead of falling back to draft text', async () => {
    const events: ChatStreamEvent[] = [];
    await consumeChatStream(
      response(
        'event: delta\ndata: draft\n\n' +
          frame('final', { message_id: 'id', content: '' })
      ),
      event => {
        events.push(event);
      }
    );
    expect(events[1]).toMatchObject({ type: 'final', final: { content: '' } });
  });

  it('accepts final-only and cached responses without deltas', async () => {
    expect(
      await consumeChatStream(
        response(frame('final', { message_id: 'id', content: 'ready' })),
        vi.fn()
      )
    ).toBe('final');
    expect(
      await consumeChatStream(response(frame('cached', {})), vi.fn())
    ).toBe('cached');
  });

  it('passes an explicit pause through and ignores malformed progress', async () => {
    const events: ChatStreamEvent[] = [];
    expect(
      await consumeChatStream(
        response(
          'event: status\ndata: bad json\n\n' +
            frame('pause', {
              run_id: 'run',
              reason: 'waiting_input',
              context: { question: 'Какой проект?' },
              action: {},
            })
        ),
        event => {
          events.push(event);
        }
      )
    ).toBe('pause');
    expect(events).toEqual([
      {
        type: 'pause',
        pause: {
          runId: 'run',
          reason: 'waiting_input',
          question: 'Какой проект?',
          message: undefined,
          action: {},
        },
      },
    ]);
  });

  it.each(['', 'data: [DONE]\n\n', 'event: delta\ndata: partial\n\n'])(
    'rejects a stream without an answer or pause: %j',
    async text => {
      await expect(consumeChatStream(response(text), vi.fn())).rejects.toThrow(
        'Соединение прервалось'
      );
    }
  );

  it('allows done-only completion explicitly for cancellation', async () => {
    expect(
      await consumeChatStream(response('data: [DONE]\n\n'), vi.fn(), {
        allowDoneOnly: true,
      })
    ).toBeNull();
  });

  it('preserves a server error code', async () => {
    await expect(
      consumeChatStream(
        response(
          frame('error', { code: 'llm_timeout', error: 'Истекло время' })
        ),
        vi.fn()
      )
    ).rejects.toThrow('llm_timeout: Истекло время');
  });
});

describe('appendRuntimeProgress', () => {
  it('updates a repeated stage with its explicit outcome, retaining its identity', () => {
    const stage: ChatRuntimeProgress = {
      id: 'first',
      runId: 'run',
      stage: 'executing',
      action: 'task_completed',
      description: 'Поиск',
      createdAt: 'now',
    };
    expect(
      appendRuntimeProgress([stage], {
        ...stage,
        id: 'next',
        outcome: 'completed',
      })
    ).toEqual([{ ...stage, outcome: 'completed' }]);
  });
});

describe('terminal event ownership', () => {
  it('does not replace final or current pause with a later obsolete pause', async () => {
    for (const first of [
      frame('final', { message_id: 'id', content: 'Готово' }),
      frame('pause', {
        run_id: 'run',
        reason: 'waiting_input',
        context: { question: 'Текущий вопрос?' },
        action: {},
      }),
    ]) {
      const observed: ChatStreamEvent[] = [];
      await consumeChatStream(
        response(
          first +
            frame('pause', {
              run_id: 'run',
              reason: 'waiting_input',
              context: { question: 'Устаревший вопрос?' },
              action: {},
            })
        ),
        event => {
          observed.push(event);
        }
      );
      expect(observed).toHaveLength(1);
      expect(JSON.stringify(observed)).not.toContain('Устаревший');
    }
  });
});
