from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import urllib.parse

# Import existing logic
from youtube_research import suggest_keywords, extract_data

app = FastAPI(title="YouTube Research Web App")

# Mount static files for the frontend
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

class KeywordRequest(BaseModel):
    keyword: str

class ExtractRequest(BaseModel):
    keywords: str # comma separated

class UploadRequest(BaseModel):
    filepath: str

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")

@app.post("/api/suggest")
def api_suggest(req: KeywordRequest):
    try:
        suggestions = suggest_keywords(req.keyword)
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/extract")
def api_extract(req: ExtractRequest):
    try:
        filepath, df = extract_data(req.keywords)
        if df is None:
            raise HTTPException(status_code=404, detail="No data found")
        
        # Replace NaN with None for JSON serialization
        df = df.where(df.notnull(), None)
        records = df.to_dict(orient="records")
        return {"filepath": filepath, "data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download")
def api_download(filepath: str):
    try:
        # Prevent path traversal
        clean_path = os.path.basename(filepath)
        full_path = os.path.join("output", clean_path)
        
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
            
        return FileResponse(
            path=full_path, 
            filename=clean_path, 
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
