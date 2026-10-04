import os
import re
import json
import html
import shutil
import threading
from datetime import datetime
import subprocess
from glob import glob
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
# Serializes upload/delete so two requests never fight over files or git
operationLock = threading.Lock()


class DeleteRequest(BaseModel):
    path: str


def stemOf(fileName):
    """TeleOp_20260101_120000.csv.html / .html / .csv -> TeleOp_20260101_120000"""
    name = re.sub(r"\.html$", "", fileName)
    return re.sub(r"\.csv$", "", name)


def loadComments():
    try:
        with open(PATH_COMMENTS, "r", encoding="utf-8") as commentsFile:
            return json.load(commentsFile)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def writeComments(comments):
    tempPath = PATH_COMMENTS + ".tmp"
    with open(tempPath, "w", encoding="utf-8") as commentsFile:
        json.dump(comments, commentsFile, indent=2, ensure_ascii=False)
    os.replace(tempPath, PATH_COMMENTS)


def saveComment(key, comment):
    with commentsLock:
        comments = loadComments()
        comments[key] = comment
        writeComments(comments)


def removeComment(key):
    with commentsLock:
        comments = loadComments()
        if key in comments:
            del comments[key]
            writeComments(comments)


def parseTimestamp(fileName, fallbackMTime):
    match = re.search(r"(\d{8})_(\d{6})", fileName)
    if match:
        try:
            return datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(fallbackMTime)


def resolveGraphPath(relativePath):
    """Validate a client-supplied path: must be an existing .html file inside HTML/."""
    htmlRoot = os.path.realpath(os.path.join(PATH_BASE, "HTML"))
    fullPath = os.path.realpath(os.path.join(PATH_BASE, relativePath))

    if not fullPath.startswith(htmlRoot + os.sep) or not fullPath.endswith(".html"):
        raise HTTPException(status_code=400, detail="Invalid graph path")
    if not os.path.isfile(fullPath):
        raise HTTPException(status_code=404, detail="Graph not found")

    return htmlRoot, fullPath


def generateIndexHtml(baseDir=PATH_BASE):
    htmlFiles = glob(os.path.join(baseDir, "HTML/**/*.html"), recursive=True)
    groupedFiles = {}
    comments = loadComments()

    for filePath in htmlFiles:
        fileName = os.path.basename(filePath)
        stamp = parseTimestamp(fileName, os.path.getmtime(filePath))
        fileDate = stamp.strftime("%Y-%m-%d")
        relativePath = os.path.relpath(filePath, baseDir)
        key = stemOf(fileName)

        # Anything without a stored comment predates comments -> Legacy
        comment = comments.get(key, LEGACY_COMMENT)

        if fileDate not in groupedFiles:
            groupedFiles[fileDate] = []
        groupedFiles[fileDate].append({
            "fileName": fileName,
            "relativePath": relativePath,
            "stamp": stamp,
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
        * { box-sizing: border-box; }
        body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #111; background: #fff; }

        .layout { display: grid; grid-template-columns: 1fr 320px; gap: 4rem; max-width: 1100px; margin: 0 auto; padding: 3rem 2rem; align-items: start; }

        h1 { margin: 0 0 2.5rem; font-size: 1.5rem; font-weight: 600; letter-spacing: -0.01em; }

        .date { margin-bottom: 2rem; }
        .date h2 { margin: 0 0 0.5rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e5e5e5; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #777; }
        ul { margin: 0; padding: 0; list-style: none; }
        li { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding: 0.55rem 0; }
        .entry { display: flex; flex-direction: column; flex: 1; min-width: 0; }
        .fileName { margin-top: 0.1rem; font-size: 0.75rem; font-style: italic; color: #999; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        li a { color: inherit; text-decoration: none; font-weight: 500; }
        li a:hover { text-decoration: underline; }
        .comment { color: #777; font-size: 0.9rem; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .del { font: inherit; font-size: 0.8rem; padding: 0.25rem 0.4rem; border: none; background: none; color: #999; cursor: pointer; }
        .del:hover:not(:disabled) { color: #111; text-decoration: underline; }
        .del:disabled { cursor: wait; }

        aside { position: sticky; top: 3rem; display: flex; flex-direction: column; gap: 1rem; padding: 1.5rem; border: 1px solid #e5e5e5; border-radius: 12px; }
        aside h2 { margin: 0; font-size: 1rem; font-weight: 600; }
        aside input[type="text"], aside input[type="file"] { width: 100%; font: inherit; font-size: 0.9rem; color: inherit; }
        aside input[type="text"] { padding: 0.6rem 0.75rem; border: 1px solid #ddd; border-radius: 8px; background: #fff; }
        aside input[type="text"]:focus { outline: none; border-color: #111; }
        aside input[type="file"]::file-selector-button { font: inherit; font-size: 0.85rem; margin-right: 0.75rem; padding: 0.45rem 0.8rem; border: 1px solid #ddd; border-radius: 8px; background: #fff; color: inherit; cursor: pointer; }
        aside input[type="file"]::file-selector-button:hover { background: #f4f4f4; }
        #uploadBtn { font: inherit; font-weight: 500; padding: 0.65rem 1rem; border: none; border-radius: 8px; background: #111; color: #fff; cursor: pointer; }
        #uploadBtn:hover:not(:disabled) { background: #333; }
        #uploadBtn:disabled { opacity: 0.5; cursor: wait; }
        #statusMessage { margin: 0; font-size: 0.85rem; min-height: 1.2em; }

        @media (max-width: 800px) {
            .layout { grid-template-columns: 1fr; gap: 2rem; padding: 1.5rem 1rem; }
            aside { position: static; order: -1; }
        }
    </style>
</head>
<body>
<div class="layout">
<main>
    <h1>Log Graphs</h1>
"""

    for fileDate in sortedDates:
        htmlContent += f'    <section class="date">\n        <h2>{fileDate}</h2>\n        <ul>\n'
        groupedFiles[fileDate].sort(key=lambda item: item["stamp"], reverse=True)
        for item in groupedFiles[fileDate]:
            safeName = html.escape(item["fileName"])
            safePath = html.escape(item["relativePath"], quote=True)
            safeComment = html.escape(item["comment"])
            label = item["stamp"].strftime("%I:%M:%S %p").lstrip("0")
            htmlContent += (
                f'            <li>\n'
                f'                <div class="entry"><a href="{safePath}">{label}</a>'
                f'<em class="fileName">{safeName}</em></div>\n'
                f'                <span class="comment">{safeComment}</span>\n'
                f'                <button class="del" data-path="{safePath}">Delete</button>\n'
                f'            </li>\n'
            )
        htmlContent += '        </ul>\n    </section>\n'

    htmlContent += """</main>

<aside>
    <h2>Import CSV</h2>
    <input type="file" id="fileInput" accept=".csv" />
    <input type="text" id="commentInput" placeholder="Comment" maxlength="500" />
    <button id="uploadBtn">Upload</button>
    <p id="statusMessage"></p>
</aside>
</div>

<script>
    const API = 'http://192.168.1.70:8000';

    const uploadBtn = document.getElementById('uploadBtn');
    const fileInput = document.getElementById('fileInput');
    const commentInput = document.getElementById('commentInput');
    const statusMessage = document.getElementById('statusMessage');

    uploadBtn.addEventListener('click', async () => {
        const file = fileInput.files[0];

        if (!file) {
            statusMessage.textContent = "Select a file first.";
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('comment', commentInput.value.trim());

        statusMessage.textContent = "Uploading...";
        uploadBtn.disabled = true;

        try {
            const response = await fetch(API + '/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok) {
                statusMessage.textContent = result.message || "Uploaded.";
                fileInput.value = "";
                commentInput.value = "";
            } else {
                statusMessage.textContent = result.detail || "Upload failed.";
            }
        } catch (error) {
            statusMessage.textContent = "Error connecting to backend.";
            console.error("Upload error:", error);
        } finally {
            uploadBtn.disabled = false;
        }
    });

    document.querySelector('main').addEventListener('click', async (e) => {
        const btn = e.target.closest('.del');
        if (!btn) return;

        const row = btn.closest('li');
        const name = row.querySelector('.fileName').textContent;

        if (!confirm('Delete ' + name + '?\\nThis removes the graph and its CSV.')) return;

        btn.disabled = true;
        btn.textContent = 'Deleting...';

        try {
            const response = await fetch(API + '/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: btn.dataset.path })
            });

            const result = await response.json();

            if (response.ok) {
                const section = row.closest('.date');
                row.remove();
                if (!section.querySelector('li')) section.remove();
                statusMessage.textContent = result.message || "Deleted.";
            } else {
                statusMessage.textContent = result.detail || "Delete failed.";
                btn.disabled = false;
                btn.textContent = 'Delete';
            }
        } catch (error) {
            statusMessage.textContent = "Error connecting to backend.";
            console.error("Delete error:", error);
            btn.disabled = false;
            btn.textContent = 'Delete';
        }
    });
</script>
</body>
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
        with operationLock:
            with open(path_fileLocationCSV, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            shutil.copyfile(path_fileLocationCSV, path_fileLocationHTML)

            subprocess.run(["perl", PATH_GRAPHING_SCRIPT, path_fileLocationHTML], check=True)

            if os.path.exists(path_fileLocationHTML):
                os.remove(path_fileLocationHTML)

            saveComment(stemOf(autoName), comment)

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


@app.post("/delete")
def delete_graph(request: DeleteRequest):
    htmlRoot, graphPath = resolveGraphPath(request.path)

    fileName = os.path.basename(graphPath)
    stem = stemOf(fileName)

    # HTML/2026/10/<name> -> CSV/2026/10/<stem>.csv
    subDir = os.path.dirname(os.path.relpath(graphPath, htmlRoot))
    csvPath = os.path.join(PATH_BASE, "CSV", subDir, stem + ".csv")

    timestamp = datetime.now().strftime("%m/%d/%y %H:%M:%S")

    try:
        with operationLock:
            os.remove(graphPath)

            if os.path.isfile(csvPath):
                os.remove(csvPath)

            removeComment(stem)

            generateIndexHtml()

            commitMessage = f"Deleted {stem} {timestamp} (Automated)"
            subprocess.run(["git", "add", "-A"], check=True)
            subprocess.run(["git", "commit", "-m", commitMessage], check=True)
            subprocess.run(["git", "push"], check=True)

        return {
            "status": "success",
            "message": f"Deleted '{fileName}'"
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

generateIndexHtml()