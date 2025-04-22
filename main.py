from os import listdir, remove, makedirs, getcwd
from os.path import join, exists
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pathlib import Path
from json import load, dump
from uuid import uuid4
from contextlib import asynccontextmanager
from html import escape
from atexit import register as atexit_register
from logging import getLogger, basicConfig, INFO
from threading import Lock

basicConfig(level=INFO)
logger = getLogger(__name__)

mapping = {}
flock = Lock()
def load_mapping():
    if exists(join('mapping.json')):
        with open(join('mapping.json'), 'r') as f:
            mapping = load(f)
    return mapping

def clean_mapping():
    global mapping
    for orphan in set(listdir(RESOURCES)) - set(mapping):
        try:
            remove(join(RESOURCES, orphan))
        except:
            logger.warn(f'Failed to delete {orphan} while {orphan} did not exist')
    for fid in mapping:
        if not exists(join(RESOURCES, fid)):
            del mapping[fid]

@atexit_register
def save_mapping():
    with flock:
        with open(join('mapping.json'), 'w') as f:
            dump(mapping, f, indent=2)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global mapping # share changes
    mapping = load_mapping()
    clean_mapping()
    yield
    save_mapping()

app = FastAPI(lifespan=lifespan)
RESOURCES = Path('resources')
makedirs(RESOURCES, exist_ok=True)


@app.get("/")
async def root():
    def create_link(fid):
        return f'<div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;"><div style="flex:1;"><a href="/download/{fid}" style="word-break: break-all;">{escape(mapping[fid])}</a></div><button onclick="fetch(\'/delete/{fid}\', {{method:\'DELETE\'}}).then(()=>location.reload())" style="background-color:red;color:white;border:none;padding:5px 10px;border-radius:5px;cursor:pointer;margin-left:10px;">Delete</button></div>'
    fids = [fid for fid in listdir(RESOURCES) if fid in mapping]
    return HTMLResponse(content=f"""
    <html>
        <head>
            <title>File</title>
            <meta charset="utf-8">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/water.css@2/out/water.css">
        </head>
        <body>
            <div>
                <h1>Files</h1><br>
                {'<br>\n'.join(create_link(fid) for fid in fids)}
            </div>
            <div>
                <input type="file" onchange="let d=new FormData();d.append('file',this.files[0]);fetch('/upload',{{method:'POST',body:d}}).then(()=>location.reload())">
            </div>
        </body>
    </html>
    """)

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global mapping
    fid = str(uuid4())
    with open(join(RESOURCES, fid), "wb") as f:
        f.write(await file.read())
    mapping[fid] = file.filename
    save_mapping()
    return {"filename": file.filename}

@app.get("/download/{fid}")
async def download(fid: str):
    if fid not in mapping:
        return {"message": "File not found", "fid": fid}
    return FileResponse(join(RESOURCES, fid), filename=mapping[fid], media_type="application/octet-stream", content_disposition_type="attachment")

@app.delete("/delete/{fid}")
async def delete(fid: str):
    global mapping
    try:
        remove(join(RESOURCES, fid))
        del mapping[fid]
        save_mapping()
        return {"message": "File deleted successfully", "fid": fid}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e), "fid": fid})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
