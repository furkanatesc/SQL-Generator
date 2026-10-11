# Sprint 32.0 — production frontend image: build the Vue 3/Vite SPA, serve it with
# non-root nginx. The SPA talks to the backend at http://<host>:8000 (api.ts default).

# Vite 8 requires Node >= 20.19 / 22.12.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
