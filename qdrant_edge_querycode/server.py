"""
server.py — FastAPI server connecting the Qdrant Edge QueryCode CLI backend to a sleek web interface.
"""
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel

from qdrant_edge_querycode import query_usage as query_module
from qdrant_edge_querycode import Llm_azure as llm
from qdrant_edge_querycode.config import TOP_K_DEFAULT

app = FastAPI(title="Qdrant Edge QueryCode UI")


frontend_dir = Path(__file__).parent.parent / "frontend"
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

class SearchRequest(BaseModel):
    query: str
    top_k: int = TOP_K_DEFAULT
    no_llm: bool = False

@app.post("/api/ask")
async def ask_endpoint(req: SearchRequest):
    try:

        results = query_module.search(req.query, top_k=req.top_k)
        

        extracted_results = []
        for r in results:
            payload = r["payload"]
            extracted_results.append({
                "score": r["score"],
                "file": payload.get("file"),
                "name": payload.get("name"),
                "summary": payload.get("summary"),
                "code": payload.get("code"),
                "language": payload.get("language")
            })
            
        explanation = None
        if not req.no_llm and results:
            try:
                explanation = await llm.async_answer_query(req.query, results)
            except Exception as e:
                explanation = f"**[LLM Warning]** Could not generate synthesized explanation: {e}"

        return {
            "success": True,
            "results": extracted_results,
            "explanation": explanation
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/", response_class=HTMLResponse)
async def index():
    return (frontend_dir / "index.html").read_text(encoding="utf-8")

def run(host: str = "127.0.0.1", port: int = 8000):
    print(f"Starting Qdrant Edge QueryCode UI at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    run()
