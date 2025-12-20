import { describe, it, expect } from 'vitest';
import {
  mapApiError,
  isRetryableError,
  getErrorMessage,
  type ErrorInfo,
} from '@shared/lib/errorMapper';

describe('errorMapper', () => {
  describe('mapApiError()', () => {
    describe('network errors', () => {
      it('should handle network error (no response)', () => {
        const error = { message: 'Network Error' };
        const result = mapApiError(error);

        expect(result.title).toBe('Сетевая ошибка');
        expect(result.message).toContain('подключиться к серверу');
        expect(result.retryable).toBe(true);
      });
    });

    describe('HTTP status codes', () => {
      it('should handle 400 Bad Request', () => {
        const error = {
          response: { status: 400, data: { detail: 'Invalid input' } },
        };
        const result = mapApiError(error);

        expect(result.title).toBe('Некорректный запрос');
        expect(result.message).toBe('Invalid input');
        expect(result.retryable).toBe(false);
      });

      it('should handle 400 without detail', () => {
        const error = { response: { status: 400 } };
        const result = mapApiError(error);

        expect(result.message).toContain('Проверьте введенные данные');
      });

      it('should handle 401 Unauthorized', () => {
        const error = { response: { status: 401 } };
        const result = mapApiError(error);

        expect(result.title).toBe('Неавторизован');
        expect(result.message).toContain('Войдите в систему');
        expect(result.action).toBe('Войти');
        expect(result.retryable).toBe(false);
      });

      it('should handle 403 Forbidden', () => {
        const error = { response: { status: 403 } };
        const result = mapApiError(error);

        expect(result.title).toBe('Доступ запрещен');
        expect(result.message).toContain('нет прав');
        expect(result.retryable).toBe(false);
      });

      it('should handle 404 Not Found', () => {
        const error = { response: { status: 404 } };
        const result = mapApiError(error);

        expect(result.title).toBe('Не найдено');
        expect(result.message).toContain('не найден');
        expect(result.retryable).toBe(false);
      });

      it('should handle 409 Conflict', () => {
        const error = {
          response: { status: 409, data: { detail: 'Already processing' } },
        };
        const result = mapApiError(error);

        expect(result.title).toBe('Конфликт');
        expect(result.message).toBe('Already processing');
        expect(result.retryable).toBe(true);
      });

      it('should handle 422 Validation Error', () => {
        const error = {
          response: { status: 422, data: { detail: 'Email is invalid' } },
        };
        const result = mapApiError(error);

        expect(result.title).toBe('Ошибка валидации');
        expect(result.message).toBe('Email is invalid');
        expect(result.retryable).toBe(false);
      });

      it('should handle 429 Too Many Requests', () => {
        const error = { response: { status: 429 } };
        const result = mapApiError(error);

        expect(result.title).toBe('Слишком много запросов');
        expect(result.action).toBe('Подождать');
        expect(result.retryable).toBe(true);
      });

      it('should handle 500 Internal Server Error', () => {
        const error = { response: { status: 500 } };
        const result = mapApiError(error);

        expect(result.title).toBe('Ошибка сервера');
        expect(result.message).toContain('пошло не так');
        expect(result.retryable).toBe(true);
      });

      it('should handle 502 Bad Gateway', () => {
        const error = { response: { status: 502 } };
        const result = mapApiError(error);

        expect(result.title).toBe('Сервис временно недоступен');
        expect(result.action).toBe('Повторить');
        expect(result.retryable).toBe(true);
      });

      it('should handle 503 Service Unavailable', () => {
        const error = { response: { status: 503 } };
        const result = mapApiError(error);

        expect(result.title).toBe('Сервис временно недоступен');
        expect(result.retryable).toBe(true);
      });

      it('should handle 504 Gateway Timeout', () => {
        const error = { response: { status: 504 } };
        const result = mapApiError(error);

        expect(result.title).toBe('Сервис временно недоступен');
        expect(result.retryable).toBe(true);
      });
    });

    describe('unknown errors', () => {
      it('should handle unknown status code', () => {
        const error = {
          response: { status: 418, data: { detail: "I'm a teapot" } },
        };
        const result = mapApiError(error);

        expect(result.title).toBe('Ошибка');
        expect(result.message).toBe("I'm a teapot");
        expect(result.retryable).toBe(false); // 4xx is not retryable
      });

      it('should handle 5xx unknown as retryable', () => {
        const error = { response: { status: 599 } };
        const result = mapApiError(error);

        expect(result.retryable).toBe(true);
      });

      it('should use error.message as fallback', () => {
        const error = {
          response: { status: 418 },
          message: 'Custom error message',
        };
        const result = mapApiError(error);

        expect(result.message).toBe('Custom error message');
      });

      it('should use status from error directly', () => {
        const error = { status: 401 };
        const result = mapApiError(error);

        expect(result.title).toBe('Неавторизован');
      });
    });
  });

  describe('isRetryableError()', () => {
    it('should return true for network errors', () => {
      expect(isRetryableError({ message: 'Network Error' })).toBe(true);
    });

    it('should return true for 5xx errors', () => {
      expect(isRetryableError({ response: { status: 500 } })).toBe(true);
      expect(isRetryableError({ response: { status: 502 } })).toBe(true);
      expect(isRetryableError({ response: { status: 503 } })).toBe(true);
    });

    it('should return true for 409 and 429', () => {
      expect(isRetryableError({ response: { status: 409 } })).toBe(true);
      expect(isRetryableError({ response: { status: 429 } })).toBe(true);
    });

    it('should return false for 4xx client errors', () => {
      expect(isRetryableError({ response: { status: 400 } })).toBe(false);
      expect(isRetryableError({ response: { status: 401 } })).toBe(false);
      expect(isRetryableError({ response: { status: 403 } })).toBe(false);
      expect(isRetryableError({ response: { status: 404 } })).toBe(false);
      expect(isRetryableError({ response: { status: 422 } })).toBe(false);
    });
  });

  describe('getErrorMessage()', () => {
    it('should return message from mapped error', () => {
      const error = { response: { status: 401 } };
      const message = getErrorMessage(error);

      expect(message).toContain('Войдите в систему');
    });

    it('should return detail from response', () => {
      const error = {
        response: { status: 400, data: { detail: 'Custom detail' } },
      };
      const message = getErrorMessage(error);

      expect(message).toBe('Custom detail');
    });

    it('should return network error message', () => {
      const error = { message: 'Network Error' };
      const message = getErrorMessage(error);

      expect(message).toContain('подключиться к серверу');
    });
  });
});
