import {
  getErrorMessage,
  isRetryableError,
  mapApiError,
} from '@/shared/lib/errorMapper';

describe('errorMapper', () => {
  it('maps network errors as retryable', () => {
    const mapped = mapApiError({});
    expect(mapped.title).toBe('Сетевая ошибка');
    expect(mapped.retryable).toBe(true);
  });

  it('maps 401 with login action', () => {
    const mapped = mapApiError({ response: { status: 401 } });
    expect(mapped.title).toBe('Неавторизован');
    expect(mapped.action).toBe('Войти');
    expect(mapped.retryable).toBe(false);
  });

  it('uses response detail when present', () => {
    const mapped = mapApiError({
      response: { status: 409, data: { detail: 'already running' } },
    });
    expect(mapped.message).toBe('already running');
  });

  it('handles unknown 5xx as retryable', () => {
    expect(
      isRetryableError({
        response: { status: 599, data: {} },
        message: 'edge failure',
      })
    ).toBe(true);
  });

  it('returns fallback message helper', () => {
    expect(getErrorMessage({ response: { status: 404 } })).toBe(
      'Запрашиваемый ресурс не найден'
    );
  });
});
