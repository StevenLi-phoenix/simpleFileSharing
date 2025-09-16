# Simple File Sharing Application

This is a simple file sharing application built using FastAPI. It allows users to upload, download, and delete files through a web interface.

## Features
- Upload files
- Download files
- Delete files
 - Partial downloads via HTTP Range
 - Resumable uploads via Content-Range

## Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd simpleFileSharing
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application (dev)**
   ```bash
   uvicorn main:app --reload
   ```

   The application will be available at `http://127.0.0.1:8000`.

## Binary Releases
- Download the Ubuntu standalone binary from the GitHub Releases page: `simple-file-sharing-linux-x64`.
- Direct link to the latest binary:
  https://github.com/StevenLi-phoenix/simpleFileSharing/releases/latest/download/simple-file-sharing-linux-x64
- Make it executable and run:
  ```bash
  chmod +x simple-file-sharing-linux-x64
  ./simple-file-sharing-linux-x64 --host 0.0.0.0 --port 8000 --max-file-size 2G
  ```
- No Python runtime is required on the target machine.

## CLI Usage
You can run via the binary or directly with Python.

- Binary or Python script:
  ```bash
  ./simple-file-sharing-linux-x64 --host 0.0.0.0 --port 9000 --max-file-size 500M
  # or
  python main.py --host 0.0.0.0 --port 9000 --max-file-size 500M
  ```
- Flags:
  - `--host` (default `127.0.0.1`): bind address
  - `--port` (default `8000`): bind port
  - `--max-file-size` (optional): max upload size, supports `K/M/G` suffixes

## Build Binary (local)
```bash
pip install -r requirements.txt && pip install pyinstaller
pyinstaller --onefile \
  --hidden-import multipart \
  --hidden-import multipart.multipart \
  --name simple-file-sharing main.py
```

## Endpoints

- **GET /**: Returns the HTML page listing all files with options to upload or delete.
- **POST /upload**: Upload a new file.
- **POST /upload_init?filename=NAME**: Initialize a resumable upload, returns `fid`.
- **PUT /upload/{fid}**: Ranged upload with raw body and `Content-Range` header.
- **GET /download/{fid}**: Download a file by its ID (supports HTTP Range for partial content).
- **DELETE /delete/{fid}**: Delete a file by its ID.

## C++ Server (experimental)
An initial C++ rewrite is scaffolded alongside the Python app. It reuses the same `resources/` and `mapping.json` and aims to keep the same API shape for core endpoints.

Prerequisites
- A C++20 compiler (`clang++` or `g++`) and `make`.

Build
- Build server:
  ```bash
  make
  ```
- Makefile targets:
  - `make` or `make all`: build the server
  - `make server`: build only the server
  - `make run`: run the server binary
  - `make clean`: remove `bin/`

Enable HTTP endpoints
- The server uses the single-header `cpp-httplib` library for HTTP. Without it, the binary will start and print a short instruction message instead of serving HTTP.
- To enable HTTP, download `httplib.h` and place it at `third_party/httplib.h`:
  - Project: https://github.com/yhirose/cpp-httplib
  - Then rebuild and run:
    ```bash
    make server && ./bin/server
    ```
  - Quick vendor (example):
    ```bash
    curl -L https://raw.githubusercontent.com/yhirose/cpp-httplib/master/httplib.h -o third_party/httplib.h
    make server && ./bin/server
    ```

Run
- Default (serves on `127.0.0.1:8000`):
  ```bash
  ./bin/server
  ```
- Configure via environment variables:
  - `PORT` (default `8000`)
  - `RESOURCES_DIR` (default `resources`)
  - `MAPPING_PATH` (default `mapping.json`)
  - `MAX_FILE_SIZE` in bytes (default `0` = no limit)
  Example:
  ```bash
  PORT=9000 RESOURCES_DIR=./resources MAPPING_PATH=./mapping.json ./bin/server
  ```

Troubleshooting
- Requires a C++20-capable compiler. Check with `clang++ --version` or `g++ --version`.
- If the server prints: "Server built without HTTP library.", ensure `third_party/httplib.h` exists and rebuild.

CLI importer
- Removed. Use HTTP endpoints instead.

API parity and limitations
- Implemented: `GET /`, `POST /upload`, `GET /download/{fid}`, `DELETE /delete/{fid}`.
- Not yet implemented in C++: resumable uploads and ranged downloads (Python app supports these).
- Current download implementation reads the whole file into memory; for very large files, consider the Python server or extend the C++ server to stream.

Behavior notes
- Reuses existing `resources/` and `mapping.json`; changes persist immediately via atomic temp+rename writes.
- IDs are base62 and validated (`[A-Za-z0-9]{6,64}`).
- Filenames are lightly sanitized for headers.

Quick checks (C++)
- Upload via curl (multipart):
  ```bash
  curl -F file=@/path/to/file http://127.0.0.1:8000/upload
  ```
- Or raw body + filename param:
  ```bash
  curl --data-binary @/path/to/file 'http://127.0.0.1:8000/upload?filename=yourfile.ext'
  ```
- Download:
  ```bash
  curl -OJ http://127.0.0.1:8000/download/<fid>
  ```

## File Structure
- `main.py`: The main application file.
- `resources/`: Directory where uploaded files are stored.
- `mapping.json`: JSON file that maps file IDs to their original filenames.

## Notes
- Ensure the `resources` directory is writable by the application.
- The application uses a simple in-memory mapping for file management, which is saved to `mapping.json` on exit.
- Range download: send header like `Range: bytes=0-1023`.
- Range upload example:
   1) `curl -s "http://127.0.0.1:8000/upload_init?filename=big.bin"` -> returns `{ "fid": "..." }`.
   2) `curl -X PUT --data-binary @chunk1.bin -H "Content-Range: bytes 0-1048575/8388608" http://127.0.0.1:8000/upload/<fid>`.
   3) Continue with subsequent chunks until complete (update start-end accordingly).
 - Git: `mapping.json` and `resources/` are ignored; `mapping.json` is untracked.

## Security Warning
- Not security-hardened: no auth, no TLS, no rate limiting. Do not expose directly to the public internet. Run behind a trusted network or reverse proxy with access controls.
- No integrity verification: uploads are not checksum-validated. If integrity matters, send a client-side hash (e.g., SHA-256) and verify server-side before accepting.

## Examples
- Partial download first KB:
  ```bash
  curl -H "Range: bytes=0-1023" -OJ http://127.0.0.1:8000/download/<fid>
  ```
- Basic upload via form (non-resumable):
  ```bash
  curl -F file=@/path/to/file http://127.0.0.1:8000/upload
  ```

## License
This project is licensed under the MIT License. 
