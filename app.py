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
        .uploadForm { display: flex; flex-direction: column; gap: 0.75rem; max-width: 400px; }
        .uploadForm input, .uploadForm button { font: inherit; padding: 0.5rem; }
        #statusMessage { margin: 0; min-height: 1.2em; }
    </style>
</head>
<body>
    <h1>Log Graphs</h1>

    <div class="card">
        <h2>Import CSV</h2>
        <div class="uploadForm">
            <input type="file" id="fileInput" accept=".csv" />
            <input type="text" id="commentInput" placeholder="Comment (optional)" maxlength="500" />
            <button id="uploadBtn">Upload</button>
            <p id="statusMessage"></p>
        </div>
    </div>

    <script>
        const uploadBtn = document.getElementById('uploadBtn');
        const fileInput = document.getElementById('fileInput');
        const commentInput = document.getElementById('commentInput');
        const statusMessage = document.getElementById('statusMessage');

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