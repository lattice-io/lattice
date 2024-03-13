FROM node:14 as builder
WORKDIR /app
COPY . .
RUN yarn
RUN yarn && yarn build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
