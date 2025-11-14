import { useRef, useCallback } from 'react';

/**
 * Хук для throttling функций
 * @param callback - функция для throttling
 * @param delay - задержка в миллисекундах
 * @returns throttled функция
 */
export function useThrottle<T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): T {
  const lastRun = useRef(Date.now());
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  return useCallback(
    ((...args: Parameters<T>) => {
      const now = Date.now();

      if (now - lastRun.current >= delay) {
        lastRun.current = now;
        callback(...args);
      } else {
        // Отменяем предыдущий timeout если он есть
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
        }

        // Устанавливаем новый timeout для последнего вызова
        timeoutRef.current = setTimeout(
          () => {
            lastRun.current = Date.now();
            callback(...args);
          },
          delay - (now - lastRun.current)
        );
      }
    }) as T,
    [callback, delay]
  );
}
