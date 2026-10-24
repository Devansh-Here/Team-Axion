from fastapi import FastAPI

app = FastAPI(title="Hypnexis AI-02")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "model": "stub"}