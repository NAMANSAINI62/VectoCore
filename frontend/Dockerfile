FROM node:20-alpine

WORKDIR /app

# Copy dependency files
COPY package.json package-lock.json* ./

# Install dependencies cleanly
RUN npm ci

# Copy application files
COPY . .

# Build Next.js application
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

EXPOSE 4317

ENV PORT=4317
ENV HOSTNAME="0.0.0.0"

CMD ["sh", "-c", "npx next start -H 0.0.0.0 -p ${PORT:-4317}"]
