FROM python:3.12-slim
WORKDIR /app
# Board-view labels are rendered with a TrueType font; the slim image has none.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY xingmou/ xingmou/
RUN pip install --no-cache-dir .
ENV PORT=8080
EXPOSE 8080
CMD ["xingmou", "serve"]
