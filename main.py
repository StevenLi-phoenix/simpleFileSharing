from os import listdir, remove, makedirs, getcwd
from os.path import join, exists, getsize
from fastapi import FastAPI, File, UploadFile, Request, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from pathlib import Path
from json import load, dump
from typing import Optional
from argparse import ArgumentParser
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
    # Return a fresh mapping from disk, without touching the global.
    if exists(join('mapping.json')):
        try:
            with open(join('mapping.json'), 'r') as f:
                return load(f)
        except Exception:
            logger.warning('Failed to load mapping.json, starting with empty mapping')
            return {}
    return {}

def clean_mapping():
    global mapping
    for orphan in set(listdir(RESOURCES)) - set(mapping):
        try:
            remove(join(RESOURCES, orphan))
        except Exception:
            logger.warning(f'Failed to delete {orphan} while {orphan} did not exist')
    for fid in list(mapping.keys()):
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

# Optional limit; configured via CLI in __main__
MAX_FILE_SIZE_BYTES: Optional[int] = None


@app.get("/")
async def root():
    def create_link(fid):
        name = escape(mapping[fid])
        return (
            '<div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">'
            '<div style="flex:1;"><a href="/download/%s" style="word-break: break-all;">%s</a></div>'
            '<button onclick="fetch(`/delete/%s`, {method:\'DELETE\'}).then(()=>location.reload())" '
            'style="background-color:red;color:white;border:none;padding:5px 10px;border-radius:5px;cursor:pointer;margin-left:10px;">Delete</button>'
            '</div>'
        ) % (fid, name, fid)
    fids = [fid for fid in listdir(RESOURCES) if fid in mapping]
    links_html = '<br>\n'.join(create_link(fid) for fid in fids)
    content = """
    <html>
        <head>
            <title>File</title>
            <meta charset="utf-8">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/water.css@2/out/water.css">
        </head>
        <body>
            <div>
                <h1>Files</h1><br>
                {links_html}
            </div>
            <div style="margin-top: 2rem;">
                <h2>Upload</h2>
                <input id="fileInput" type="file">
                <button id="uploadBtn">Upload</button>
                <div style="margin-top: 10px;">
                    <progress id="uploadProgress" value="0" max="100" style="width: 300px;"></progress>
                    <span id="uploadPct">0%</span>
                </div>
            </div>

            <script>
            const fileInput = document.getElementById('fileInput');
            const uploadBtn = document.getElementById('uploadBtn');
            const progressEl = document.getElementById('uploadProgress');
            const pctEl = document.getElementById('uploadPct');

            uploadBtn.addEventListener('click', async () => {
                const file = fileInput.files && fileInput.files[0];
                if (!file) { alert('Please choose a file'); return; }
                uploadBtn.disabled = true;
                try {
                    // 1) init upload to obtain fid
                    const initResp = await fetch('/upload_init?filename=' + encodeURIComponent(file.name), { method: 'POST' });
                    if (!initResp.ok) {
                        const t = await initResp.text();
                        throw new Error('Init failed: ' + initResp.status + ' ' + t);
                    }
                    const initJson = await initResp.json();
                    const fid = initJson.fid;
                    if (!fid) throw new Error('No fid returned from server');

                    // 2) upload in chunks via PUT with Content-Range
                    const chunkSize = 2 * 1024 * 1024; // 2MB
                    let start = 0;
                    while (start < file.size) {
                        const end = Math.min(start + chunkSize, file.size) - 1;
                        const blob = file.slice(start, end + 1);
                        const resp = await fetch('/upload/' + fid, {
                            method: 'PUT',
                            headers: {
                                'Content-Range': `bytes ${start}-${end}/${file.size}`,
                                'Content-Type': 'application/octet-stream',
                            },
                            body: blob,
                        });
                        if (!resp.ok) {
                            const t = await resp.text();
                            throw new Error('Chunk failed: ' + resp.status + ' ' + t);
                        }
                        const uploaded = end + 1;
                        const pct = Math.round((uploaded / file.size) * 100);
                        progressEl.value = pct; pctEl.textContent = pct + '%';
                        start = end + 1;
                    }
                    progressEl.value = 100; pctEl.textContent = '100%';
                    setTimeout(() => location.reload(), 300);
                } catch (e) {
                    alert(String(e));
                } finally {
                    uploadBtn.disabled = false;
                }
            });
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=content.replace("{links_html}", links_html))

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Legacy multipart upload. Now streams to disk to avoid OOM."""
    global mapping
    fid = str(uuid4())
    written = 0
    try:
        with open(join(RESOURCES, fid), "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if MAX_FILE_SIZE_BYTES is not None and written > MAX_FILE_SIZE_BYTES:
                    # Cleanup partial file and reject
                    f.flush()
                    f.close()
                    try:
                        remove(join(RESOURCES, fid))
                    except Exception:
                        pass
                    return JSONResponse(status_code=413, content={"message": "File too large"})
                f.write(chunk)
    finally:
        await file.close()
    mapping[fid] = file.filename
    save_mapping()
    return JSONResponse(content={"filename": file.filename, "fid": fid})

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
async def upload_range(fid: str, request: Request):
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
    # Accept both "bytes start-end/total" and legacy "bytes=start-end/total"
    s = cr.strip()
    if s.lower().startswith("bytes="):
        rng = s.split("=", 1)[1].strip()
    elif s.lower().startswith("bytes "):
        rng = s.split(" ", 1)[1].strip()
    else:
        return JSONResponse(status_code=400, content={"message": "Invalid Content-Range format"})
    try:
        range_part, total_part = rng.split("/", 1)
        if range_part == "*":
            return JSONResponse(status_code=400, content={"message": "Wildcard range not supported"})
        start_s, end_s = range_part.split("-", 1)
        start = int(start_s)
        end = int(end_s)
        total = int(total_part) if total_part != "*" else None
    except Exception:
        return JSONResponse(status_code=400, content={"message": "Invalid Content-Range format"})

    if start < 0 or end < start:
        return JSONResponse(status_code=400, content={"message": "Invalid byte positions"})
    expected_len = end - start + 1

    # Read raw body bytes explicitly to avoid parser issues
    body = await request.body()
    if expected_len != len(body):
        return JSONResponse(status_code=400, content={"message": "Body length does not match range"})

    # Enforce max file size when configured
    if MAX_FILE_SIZE_BYTES is not None:
        if total is not None and total > MAX_FILE_SIZE_BYTES:
            return JSONResponse(status_code=413, content={"message": "File too large"})
        if total is None and end + 1 > MAX_FILE_SIZE_BYTES:
            return JSONResponse(status_code=413, content={"message": "File too large"})

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
    parser = ArgumentParser(description="Simple File Sharing Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--max-file-size",
        dest="max_file_size",
        default=None,
        help="Maximum file size (e.g. 100M, 2G). Omit for unlimited.",
    )
    args = parser.parse_args()

    def parse_size(s: Optional[str]) -> Optional[int]:
        if not s:
            return None
        units = {"k": 1024, "m": 1024**2, "g": 1024**3}
        ls = s.strip().lower()
        try:
            if ls[-1] in units:
                return int(float(ls[:-1]) * units[ls[-1]])
            return int(ls)
        except Exception:
            logger.warning("Invalid --max-file-size value; ignoring")
            return None

    MAX_FILE_SIZE_BYTES = parse_size(args.max_file_size)
    uvicorn.run(app, host=args.host, port=args.port)
