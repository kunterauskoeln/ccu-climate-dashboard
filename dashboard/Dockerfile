# --- Build Stage ---
FROM node:26-alpine AS build
WORKDIR /app

# Dependencies first → this layer stays cached until package*.json changes.
COPY package*.json ./
RUN npm ci --no-audit --no-fund

# App source
COPY . .
RUN npm run build

# --- Production Stage ---
FROM nginx:alpine

# SPA routing + /api reverse proxy onto the compose network
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
