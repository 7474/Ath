# リポジトリ根からビルドする: docker build -f deploy/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

COPY baronh/ baronh/
COPY data/lexicon.json data/ingested.json data/
COPY web/ web/
COPY index.html site.css aarth.css aarth.woff2 aarth.ttf ./
COPY ath/ ath/

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["python3", "-m", "baronh", "serve", "--host", "0.0.0.0"]
