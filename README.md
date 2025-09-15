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

4. **Run the application**
   ```bash
   uvicorn main:app --reload
   ```

   The application will be available at `http://127.0.0.1:8000`.

## Endpoints

- **GET /**: Returns the HTML page listing all files with options to upload or delete.
- **POST /upload**: Upload a new file.
- **POST /upload_init?filename=NAME**: Initialize a resumable upload, returns `fid`.
- **PUT /upload/{fid}**: Ranged upload with raw body and `Content-Range` header.
- **GET /download/{fid}**: Download a file by its ID (supports HTTP Range for partial content).
- **DELETE /delete/{fid}**: Delete a file by its ID.

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
