"""ReviveFlow API entrypoint.

Run from the backend directory:
    python run_api.py
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=False)
