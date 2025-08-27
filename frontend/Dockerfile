FROM node:20-alpine

WORKDIR /app

# 1. скопировать package.json и lock, чтобы кешировалось
COPY package*.json ./

# 2. если lockfile есть → npm ci, иначе npm install
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# 3. на всякий случай доустановим нужные dev-зависимости (часто не фиксируются в package.json при ручной установке)
RUN npm install -D tailwindcss postcss autoprefixer @tailwindcss/postcss \
    && npm install react-router-dom zustand

# 4. скопировать исходники
COPY . .

EXPOSE 5173

# 5. запуск dev-сервера
CMD ["npm","run","dev","--","--host","0.0.0.0"]
