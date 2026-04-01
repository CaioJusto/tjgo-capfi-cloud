FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN npm install -g http-server
COPY --from=builder /app/dist ./dist
EXPOSE 3000
CMD ["sh", "-c", "http-server dist -p ${PORT:-3000} -a 0.0.0.0 --proxy http://0.0.0.0:${PORT:-3000}?"]
