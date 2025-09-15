from os import listdir, remove, makedirs, getcwd
from os.path import join, exists, getsize
from fastapi import FastAPI, File, UploadFile, Request, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
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
    return JSONResponse(content={"filename": file.filename})

def _parse_range(range_header: str, file_size: int):
    try:
        unit, ranges = range_header.split("=", 1)
        if unit.strip().lower() != "bytes":
            return None
        start_str, end_str = ranges.split("-", 1)
        if start_str == "":
            length = int(end_str)
            if length <= 0:
                return None
            start = max(0, file_size - length)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
        if start > end or start < 0 or end >= file_size:
            return None
        return start, end
    except Exception:
        return None

@app.get("/download/{fid}")
async def download(fid: str, request: Request):
    if fid not in mapping:
        return JSONResponse(status_code=404, content={"message": "File not found", "fid": fid})
    fp = join(RESOURCES, fid)
    if not exists(fp):
        return JSONResponse(status_code=404, content={"message": "File not found", "fid": fid})

    range_header = request.headers.get("Range")
    file_size = getsize(fp)
    filename = mapping[fid]

    if not range_header:
        return FileResponse(fp, filename=filename, media_type="application/octet-stream", content_disposition_type="attachment")

    byte_range = _parse_range(range_header, file_size)
    if byte_range is None:
        return JSONResponse(status_code=416, content={"message": "Invalid Range"})
    start, end = byte_range

    def file_iterator(path, start, end, chunk_size=1024 * 64):
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"attachment; filename=\"{filename}\"",
    }
    return StreamingResponse(
        file_iterator(fp, start, end),
        status_code=206,
        media_type="application/octet-stream",
        headers=headers,
    )

@app.delete("/delete/{fid}")
async def delete(fid: str):
    global mapping
    if fid not in mapping or not exists(join(RESOURCES, fid)):
        return JSONResponse(status_code=404, content={"message": "File not found", "fid": fid})
    try:
        remove(join(RESOURCES, fid))
        del mapping[fid]
        save_mapping()
        return JSONResponse(content={"message": "File deleted successfully", "fid": fid})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e), "fid": fid})


@app.post("/upload_init")
async def upload_init(filename: str):
    """Initialize a resumable upload and return fid."""
    global mapping
    fid = str(uuid4())
    with open(join(RESOURCES, fid), "wb") as _:
        pass
    mapping[fid] = filename
    save_mapping()
    return JSONResponse(content={"fid": fid, "filename": filename})


@app.put("/upload/{fid}")
async def upload_range(fid: str, request: Request, body: bytes = Body(...)):
    """Upload a byte range with Content-Range header (PUT raw bytes)."""
    if fid not in mapping:
        return JSONResponse(status_code=404, content={"message": "Unknown fid", "fid": fid})
    fp = join(RESOURCES, fid)
    if not exists(fp):
        with open(fp, "wb") as _:
            pass

    cr = request.headers.get("Content-Range")
    if not cr:
        return JSONResponse(status_code=400, content={"message": "Missing Content-Range header"})
    try:
        unit, rng = cr.split("=", 1)
        if unit.strip().lower() != "bytes":
            raise ValueError
        range_part, total_part = rng.split("/")
        start_s, end_s = range_part.split("-")
        start = int(start_s)
        end = int(end_s)
        total = int(total_part) if total_part != "*" else None
    except Exception:
        return JSONResponse(status_code=400, content={"message": "Invalid Content-Range format"})

    if start < 0 or end < start:
        return JSONResponse(status_code=400, content={"message": "Invalid byte positions"})
    expected_len = end - start + 1
    if expected_len != len(body):
        return JSONResponse(status_code=400, content={"message": "Body length does not match range"})

    try:
        with open(fp, "r+b") as f:
            f.seek(start)
            f.write(body)
        completed = total is not None and end + 1 == total
        return JSONResponse(content={"message": "Chunk accepted", "fid": fid, "received": expected_len, "complete": completed})
    except FileNotFoundError:
        with open(fp, "wb") as f:
            f.seek(start)
            f.write(body)
        completed = total is not None and end + 1 == total
        return JSONResponse(content={"message": "Chunk accepted (created)", "fid": fid, "received": expected_len, "complete": completed})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
