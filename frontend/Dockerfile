# --- build stage: compile the Vite app to static files ---
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# `npm run build` = `tsc --noEmit && vite build`. No VITE_API_URL is set, so the
# app uses relative API paths (/api, /auth, …) which nginx proxies to the backend.
RUN npm run build

# --- serve stage: nginx serves the static app + proxies the API ---
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
