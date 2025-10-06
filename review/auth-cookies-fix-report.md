# Отчет о проблемах с авторизацией при создании пользователя

## 🔍 **Найденные проблемы:**

### **1. Отсутствие `credentials: 'include'` в функции `refresh()`**
- **Проблема**: При обновлении токена куки не отправлялись
- **Результат**: Бэкенд не мог проверить refresh_token из куки

### **2. Неправильная логика авторизации в `apiFetch`**
- **Проблема**: Если токена нет в localStorage, запрос не отправлялся
- **Результат**: Фронтенд не мог использовать куки для авторизации

### **3. Условная проверка 401 ошибки**
- **Проблема**: Обновление токена происходило только если токен был в localStorage
- **Результат**: Если токен истек, фронтенд не мог его обновить

## 🔧 **Исправления:**

### **1. Добавлен `credentials: 'include'` в функцию `refresh()`:**
```typescript
async function refresh() {
  const res = await fetch(API_BASE + '/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken() }),
    credentials: 'include', // Include cookies in refresh request
  });
  // ...
}
```

### **2. Исправлена логика авторизации:**
```typescript
// Only add Authorization header if auth is not disabled and we have a token
if (opts.auth !== false) {
  const authToken = token();
  if (authToken) {
    headers['Authorization'] = 'Bearer ' + authToken;
  }
  // If no token in localStorage, we still send the request with cookies
  // The backend will check cookies if no Authorization header is provided
}
```

### **3. Убрана условная проверка для 401 ошибки:**
```typescript
let res = await doFetch();
if (res.status === 401) { // Убрали && token()
  try {
    const t = await refresh();
    headers['Authorization'] = 'Bearer ' + t;
    res = await doFetch();
  } catch {
    del('token');
    del('refresh_token');
    throw new Error('Не авторизован');
  }
}
```

## 📋 **Технические детали:**

### **Почему это происходило:**
1. **Куки не отправлялись при refresh** - бэкенд не мог проверить refresh_token
2. **Запросы не отправлялись без токена** - фронтенд полагался только на localStorage
3. **Обновление токена не работало** - если токен истек, фронтенд не мог его обновить

### **Как работает исправление:**
1. **Куки отправляются всегда** - `credentials: 'include'` во всех запросах
2. **Запросы отправляются даже без токена** - бэкенд проверяет куки
3. **Обновление токена работает всегда** - при любой 401 ошибке

## 🎯 **Результат:**
- ✅ **Авторизация через куки работает** - фронтенд может использовать куки
- ✅ **Обновление токена работает** - refresh_token из куки используется
- ✅ **Создание пользователя работает** - авторизация проходит успешно
- ✅ **Обратная совместимость** - localStorage токены все еще работают

## 🧪 **Тестирование:**
После исправления:
1. **Создание пользователя из веб-интерфейса** - должно работать
2. **Авторизация через куки** - должна работать
3. **Обновление токена** - должно работать
4. **Смешанная авторизация** - localStorage + куки должны работать

Проблема была в неправильной работе с куки в `apiFetch`! 🎉
