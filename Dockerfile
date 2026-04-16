FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY xingmou/ xingmou/
RUN pip install --no-cache-dir .
ENV PORT=8080
EXPOSE 8080
CMD ["xingmou", "serve"]
