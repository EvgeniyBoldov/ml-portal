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
      phase: 'execution',
      kind: 'task_completed',
      description: 'Поиск',
      createdAt: 'now',
    };
    expect(
      appendRuntimeProgress([stage], {
        ...stage,
        id: 'next',
        status: 'completed',
      })
    ).toEqual([{ ...stage, status: 'completed' }]);
  });
});
