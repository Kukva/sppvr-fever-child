# Stage 1: build (с подстановкой URL API при сборке)
FROM node:20-alpine AS builder

WORKDIR /app

# зависимости
COPY package.json package-lock.json* ./
RUN npm ci

# исходники
COPY . .

# URL бэкенда при сборке (пустой = относительные пути через nginx proxy)
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# Stage 2: production — только nginx + собранный фронт
FROM nginx:alpine AS production

COPY --from=builder /app/dist/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
