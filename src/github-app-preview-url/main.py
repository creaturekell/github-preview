from fastapi import FastAPI
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GitHub App Preview URL Service")

@app.get("/")
async def root():
    return {"status": "healthy"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
