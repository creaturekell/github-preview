FROM python:3.12-slim

WORKDIR /app

# Create a non-root user 
RUN useradd -m appuser
USER appuser

COPY --chown=appuser:appuser helloworld.py .

CMD ["python", "helloworld.py"]
