# No dependencies to install, so the image is just Python and the source.
FROM python:3.12-slim

WORKDIR /app

COPY otto/ ./otto/
COPY README.md LICENSE pyproject.toml ./
COPY prospects.example.csv ./

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OTTO_DATA_DIR=/app/data

RUN mkdir -p /app/data

# 5555 is bound to loopback on the host, not published to the internet.
EXPOSE 5555

ENTRYPOINT ["python3", "-m", "otto"]
CMD ["run"]
