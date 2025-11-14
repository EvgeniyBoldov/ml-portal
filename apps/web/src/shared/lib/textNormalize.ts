/**
 * НЕ НОРМАЛИЗУЕМ НИЧЕГО! Возвращаем текст как есть
 * Только убираем служебные маркеры [DONE]
 */
export function normalizeText(text: string): string {
  if (!text) return '';
  // Убираем только [DONE] маркер, больше ничего не трогаем!
  return text.replace(/\[DONE\]/g, '');
}

/**
 * Cleans up streaming text - теперь просто алиас для normalizeText
 */
export function cleanStreamingText(text: string): string {
  return normalizeText(text);
}
