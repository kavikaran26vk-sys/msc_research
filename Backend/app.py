import os
import uuid
from fastapi import FastAPI, Depends, HTTPException, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uvicorn
from database import get_db, Cluster, Product
from agent import run_agent, clear_session
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="UK Laptop Recommender API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ui", StaticFiles(directory="ui"), name="ui")

class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"

@app.get("/")
def root():
    return FileResponse("ui/index.html")

@app.post("/query")
def query_agent(request: QueryRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    result = run_agent(request.query, request.session_id)
    return result

@app.post("/clear")
def clear_chat(session_id: str = "default"):
    clear_session(session_id)
    return {"status": "cleared"}

@app.get("/health")
def health():
    return {"status": "ok"}
# Run app
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)