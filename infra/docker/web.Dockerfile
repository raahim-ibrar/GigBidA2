FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
ARG API_INTERNAL_URL=http://api:8000
ARG NEXT_PUBLIC_API_URL=
ENV API_INTERNAL_URL=$API_INTERNAL_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
USER node
CMD ["node", "server.js"]
