FROM python:3.12-slim

WORKDIR /app

# Create a non-root user 
RUN useradd -m appuser
USER appuser

COPY --chown=appuser:appuser helloworld.py .

# Expose port 8080
EXPOSE 8080

# Set default port
ENV PORT=8080

CMD ["python", "helloworld.py"]
