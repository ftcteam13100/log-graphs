import os
import json
import html
import shutil
import threading
from datetime import datetime
import subprocess
from glob import glob
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PATH_BASE = "/home/skorada/ftc-csv-grapher/log-graphs"
PATH_GRAPHING_SCRIPT = "plotData.pl"
PATH_COMMENTS = os.path.join(PATH_BASE, "comments.json")
LEGACY_COMMENT = "<Legacy>"
MAX_COMMENT_LENGTH = 500

commentsLock = threading.Lock()


def loadComments():
    try:
        with open(PATH_COMMENTS, "r", encoding="utf-8") as commentsFile:
            return json.load(commentsFile)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def saveComment(key, comment):
    with commentsLock:
        comments = loadComments()
        comments[key] = comment
        tempPath = PATH_COMMENTS + ".tmp"
        with open(tempPath, "w", encoding="utf-8") as commentsFile:
            json.dump(comments, commentsFile, indent=2, ensure_ascii=False)
        os.replace(tempPath, PATH_COMMENTS)


def generateIndexHtml(baseDir=PATH_BASE):
    htmlFiles = glob(os.path.join(baseDir, "HTML/**/*.html"), recursive=True)
    groupedFiles = {}
    comments = loadComments()

    for filePath in htmlFiles:
        mTime = os.path.getmtime(filePath)
        fileDate = datetime.fromtimestamp(mTime).strftime("%Y-%m-%d")
        relativePath = os.path.relpath(filePath, baseDir)
        fileName = os.path.basename(filePath)
        key = os.path.splitext(fileName)[0]

        # Anything without a stored comment predates comments -> Legacy
        comment = comments.get(key, LEGACY_COMMENT)

        if fileDate not in groupedFiles:
            groupedFiles[fileDate] = []
        groupedFiles[fileDate].append({
            "fileName": fileName,
            "relativePath": relativePath,
            "mTime": mTime,
            "comment": comment
        })

    sortedDates = sorted(groupedFiles.keys(), reverse=True)

    htmlContent = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log Graphs</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; background: #f8f9fa; color: #333; }
        h1 { color: #2c3e50; border-bottom: 2px solid #ccc; padding-bottom: 0.5rem; }
        .card { margin-bottom: 2rem; background: white; padding: 1.2rem 1.5rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .card h2 { margin-top: 0; color: #0066cc; font-size: 1.25rem; }
        ul { list-style-type: none; padding-left: 0; margin: 0; }
        li { margin: 0.5rem 0; }
        a { color: #2b6cb0; text-decoration: none; font-weight: 500; }
        a:hover { text-decoration: underline; }
        .comment { color: #666; font-size: 0.9rem; margin-left: 0.5rem; }
        .comment::before { content: "\\2014\\00a0"; }

        /* ---- Import CSV card ---- */
        .uploadCard { padding: 0; overflow: hidden; max-width: 460px; box-shadow: 0 4px 14px rgba(0,102,204,0.12); }
        .uploadHeader { display: flex; align-items: center; gap: 0.9rem; padding: 1.1rem 1.5rem; background: linear-gradient(135deg, #0057b8, #4a90e2); color: white; }
        .uploadIcon { width: 42px; height: 42px; flex-shrink: 0; padding: 9px; box-sizing: border-box; border-radius: 10px; background: rgba(255,255,255,0.18); }
        .card .uploadHeader h2 { margin: 0; color: white; font-size: 1.3rem; }
        .uploadHeader p { margin: 0.15rem 0 0; font-size: 0.85rem; opacity: 0.85; }
        .uploadBody { display: flex; flex-direction: column; gap: 0.9rem; padding: 1.25rem 1.5rem 1.5rem; }

        .dropZone { display: flex; flex-direction: column; align-items: center; gap: 0.35rem; padding: 1.6rem 1rem; border: 2px dashed #b9c7d8; border-radius: 10px; background: #f5f8fc; color: #5a6b7d; text-align: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
        .dropZone:hover, .dropZone.dragOver { border-color: #0066cc; background: #eaf3ff; }
        .dropZone.hasFile { border-style: solid; border-color: #2f9e63; background: #eefaf3; color: #1f6e44; }
        .dropZone strong { font-size: 0.95rem; word-break: break-all; }
        .dropZone span { font-size: 0.8rem; opacity: 0.8; }
        .dropZone svg { width: 28px; height: 28px; }
        #fileInput { display: none; }

        .field { display: flex; flex-direction: column; gap: 0.3rem; }
        .field label { font-size: 0.8rem; font-weight: 600; color: #4a5a6a; text-transform: uppercase; letter-spacing: 0.04em; }
        #commentInput { font: inherit; padding: 0.65rem 0.8rem; border: 1px solid #ccd5e0; border-radius: 8px; background: white; transition: border-color 0.15s, box-shadow 0.15s; }
        #commentInput:focus { outline: none; border-color: #0066cc; box-shadow: 0 0 0 3px rgba(0,102,204,0.15); }

        #uploadBtn { font: inherit; font-weight: 600; padding: 0.7rem 1rem; border: none; border-radius: 8px; color: white; background: linear-gradient(135deg, #0057b8, #4a90e2); cursor: pointer; transition: transform 0.1s, box-shadow 0.15s, opacity 0.15s; }
        #uploadBtn:hover:not(:disabled) { box-shadow: 0 4px 12px rgba(0,102,204,0.35); transform: translateY(-1px); }
        #uploadBtn:disabled { opacity: 0.6; cursor: wait; }
        #statusMessage { margin: 0; min-height: 1.2em; font-size: 0.9rem; }
    </style>
</head>
<body>
    <h1>Log Graphs</h1>

    <div class="card uploadCard">
        <div class="uploadHeader">
            <svg class="uploadIcon" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <div>
                <h2>Import CSV</h2>
                <p>Upload a log to generate a new graph</p>
            </div>
        </div>

        <div class="uploadBody">
            <label class="dropZone" id="dropZone" for="fileInput">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
                <strong id="dropTitle">Choose a CSV file</strong>
                <span id="dropHint">or drag and drop it here</span>
            </label>
            <input type="file" id="fileInput" accept=".csv" />

            <div class="field">
                <label for="commentInput">Comment</label>
                <input type="text" id="commentInput" placeholder="Optional note about this run" maxlength="500" />
            </div>

            <button id="uploadBtn">Upload</button>
            <p id="statusMessage"></p>
        </div>
    </div>

    <script>
        const uploadBtn = document.getElementById('uploadBtn');
        const fileInput = document.getElementById('fileInput');
        const commentInput = document.getElementById('commentInput');
        const statusMessage = document.getElementById('statusMessage');
        const dropZone = document.getElementById('dropZone');
        const dropTitle = document.getElementById('dropTitle');
        const dropHint = document.getElementById('dropHint');

        function updateDropZone() {
            const file = fileInput.files[0];
            if (file) {
                dropZone.classList.add('hasFile');
                dropTitle.textContent = file.name;
                dropHint.textContent = (file.size / 1024).toFixed(1) + ' KB \u2022 click to change';
            } else {
                dropZone.classList.remove('hasFile');
                dropTitle.textContent = 'Choose a CSV file';
                dropHint.textContent = 'or drag and drop it here';
            }
        }

        fileInput.addEventListener('change', updateDropZone);

        ['dragenter', 'dragover'].forEach(evt => {
            dropZone.addEventListener(evt, (e) => {
                e.preventDefault();
                dropZone.classList.add('dragOver');
            });
        });
        ['dragleave', 'drop'].forEach(evt => {
            dropZone.addEventListener(evt, (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragOver');
            });
        });
        dropZone.addEventListener('drop', (e) => {
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                updateDropZone();
            }
        });

        uploadBtn.addEventListener('click', async () => {
            const file = fileInput.files[0];

            if (!file) {
                statusMessage.textContent = "Please select a file first.";
                statusMessage.style.color = "red";
                return;
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('comment', commentInput.value.trim());

            statusMessage.textContent = "Uploading...";
            statusMessage.style.color = "inherit";
            uploadBtn.disabled = true;

            try {
                const response = await fetch('http://192.168.1.70:8000/upload', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (response.ok) {
                    statusMessage.textContent = result.message || "Upload successful!";
                    statusMessage.style.color = "green";
                    fileInput.value = "";
                    commentInput.value = "";
                    updateDropZone();
                } else {
                    statusMessage.textContent = result.detail || "Upload failed.";
                    statusMessage.style.color = "red";
                }
            } catch (error) {
                statusMessage.textContent = "Error connecting to backend.";
                statusMessage.style.color = "red";
                console.error("Upload error:", error);
            } finally {
                uploadBtn.disabled = false;
            }
        });
    </script>
"""

    for fileDate in sortedDates:
        htmlContent += f'    <div class="card">\n        <h2>{fileDate}</h2>\n        <ul>\n'
        groupedFiles[fileDate].sort(key=lambda item: item["mTime"], reverse=True)
        for item in groupedFiles[fileDate]:
            safeName = html.escape(item["fileName"])
            safePath = html.escape(item["relativePath"], quote=True)
            safeComment = html.escape(item["comment"]) if item["comment"] else "&nbsp;"
            htmlContent += (
                f'            <li><a href="{safePath}">{safeName}</a>'
                f'<span class="comment">{safeComment}</span></li>\n'
            )
        htmlContent += '        </ul>\n    </div>\n'

    htmlContent += """</body>
</html>"""

    indexPath = os.path.join(baseDir, "index.html")
    with open(indexPath, "w", encoding="utf-8") as htmlFile:
        htmlFile.write(htmlContent)


@app.post("/upload")
def upload_and_sync(file: UploadFile = File(...), comment: str = Form("")):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file type")

    comment = comment.strip()[:MAX_COMMENT_LENGTH]

    now = datetime.now()
    year = now.year
    month = now.month
    timestamp = now.strftime("%m/%d/%y %H:%M:%S")

    autoName = now.strftime("TeleOp_%Y%m%d_%H%M%S") + ".csv"

    csvFolder = f"{PATH_BASE}/CSV/{year}/{month}"
    htmlFolder = f"{PATH_BASE}/HTML/{year}/{month}"
    os.makedirs(csvFolder, exist_ok=True)
    os.makedirs(htmlFolder, exist_ok=True)

    path_fileLocationCSV = os.path.join(csvFolder, autoName)
    path_fileLocationHTML = os.path.join(htmlFolder, autoName)

    try:
        with open(path_fileLocationCSV, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        shutil.copyfile(path_fileLocationCSV, path_fileLocationHTML)

        subprocess.run(["perl", PATH_GRAPHING_SCRIPT, path_fileLocationHTML], check=True)

        if os.path.exists(path_fileLocationHTML):
            os.remove(path_fileLocationHTML)

        # Keyed by filename stem, e.g. "TeleOp_20260101_120000"
        saveComment(os.path.splitext(autoName)[0], comment)

        generateIndexHtml()

        commitMessage = f"New files {timestamp} (Automated)"
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", commitMessage], check=True)
        subprocess.run(["git", "push"], check=True)

        return {
            "status": "success",
            "message": f"'{file.filename}' graph successfully pushed as '{autoName}'",
            "saved_path": path_fileLocationHTML
        }

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Process failed during execution: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error: {str(e)}"
        )