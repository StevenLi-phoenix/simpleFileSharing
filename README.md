# Simple File Sharing Application

This is a simple file sharing application built using FastAPI. It allows users to upload, download, and delete files through a web interface.

## Features
- Upload files
- Download files
- Delete files

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
- **GET /download/{fid}**: Download a file by its ID.
- **DELETE /delete/{fid}**: Delete a file by its ID.

## File Structure
- `main.py`: The main application file.
- `resources/`: Directory where uploaded files are stored.
- `mapping.json`: JSON file that maps file IDs to their original filenames.

## Notes
- Ensure the `resources` directory is writable by the application.
- The application uses a simple in-memory mapping for file management, which is saved to `mapping.json` on exit.

## License
This project is licensed under the MIT License. 