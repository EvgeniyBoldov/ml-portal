/**
 * Centralized API error mapping
 * Maps API errors to user-friendly messages
 */

export interface ErrorInfo {
  title: string;
  message: string;
  action?: string;
  retryable: boolean;
}

/**
 * Map API error to user-friendly format
 */
export function mapApiError(error: any): ErrorInfo {
  // Network errors
  if (!error.response) {
    return {
      title: 'Сетевая ошибка',
      message:
        'Не удалось подключиться к серверу. Проверьте подключение к интернету.',
      action: 'Проверьте подключение',
      retryable: true,
    };
  }

  const status = error.response?.status || error.status;

  switch (status) {
    case 400:
      return {
        title: 'Некорректный запрос',
        message: error.response?.data?.detail || 'Проверьте введенные данные',
        retryable: false,
      };
    case 401:
      return {
        title: 'Неавторизован',
        message: 'Войдите в систему для продолжения',
        action: 'Войти',
        retryable: false,
      };
    case 403:
      return {
        title: 'Доступ запрещен',
        message: 'У вас нет прав для выполнения этого действия',
        retryable: false,
      };
    case 404:
      return {
        title: 'Не найдено',
        message: 'Запрашиваемый ресурс не найден',
        retryable: false,
      };
    case 409:
      return {
        title: 'Конфликт',
        message:
          error.response?.data?.detail ||
          'Это действие уже выполняется. Попробуйте позже.',
        action: 'Понятно',
        retryable: true,
      };
    case 422:
      return {
        title: 'Ошибка валидации',
        message:
          error.response?.data?.detail || 'Проверьте правильность данных',
        retryable: false,
      };
    case 429:
      return {
        title: 'Слишком много запросов',
        message: 'Подождите немного перед повторной попыткой',
        action: 'Подождать',
        retryable: true,
      };
    case 500:
      return {
        title: 'Ошибка сервера',
        message: 'Что-то пошло не так. Мы уже работаем над этим.',
        retryable: true,
      };
    case 502:
    case 503:
    case 504:
      return {
        title: 'Сервис временно недоступен',
        message: 'Попробуйте повторить запрос через несколько секунд',
        action: 'Повторить',
        retryable: true,
      };
    default:
      return {
        title: 'Ошибка',
        message:
          error.response?.data?.detail ||
          error.message ||
          'Произошла непредвиденная ошибка',
        retryable: status >= 500,
      };
  }
}

/**
 * Check if error is retryable
 */
export function isRetryableError(error: any): boolean {
  return mapApiError(error).retryable;
}

/**
 * Get error message for toast
 */
export function getErrorMessage(error: any): string {
  const errorInfo = mapApiError(error);
  return errorInfo.message;
}
