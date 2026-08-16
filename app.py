import os
import shutil
from datetime import datetime
import subprocess
from glob import glob
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

year = datetime.now().year
month = datetime.now().month
timestamp = datetime.now().strftime("%m/%d/%y %H:%M:%S")

PATH_BASE = "/home/skorada/ftc-csv-grapher/log-graphs"
PATH_GRAPHING_SCRIPT = "plotData.pl"
PATH_CSV_FOLDER = f"/home/skorada/ftc-csv-grapher/log-graphs/CSV/{year}/{month}"
PATH_HTML_FOLDER = f"/home/skorada/ftc-csv-grapher/log-graphs/HTML/{year}/{month}"

os.makedirs(PATH_CSV_FOLDER, exist_ok=True)
os.makedirs(PATH_HTML_FOLDER, exist_ok=True)

def generateIndexHtml(baseDir=PATH_BASE):
    htmlFiles = glob(os.path.join(baseDir, "HTML/**/*.html"), recursive=True)
    groupedFiles = {}

    for filePath in htmlFiles:
        mTime = os.path.getmtime(filePath)
        fileDate = datetime.fromtimestamp(mTime).strftime("%Y-%m-%d")
        relativePath = os.path.relpath(filePath, baseDir)
        fileName = os.path.basename(filePath)

        if fileDate not in groupedFiles:
            groupedFiles[fileDate] = []
        groupedFiles[fileDate].append({
            "fileName": fileName,
            "relativePath": relativePath,
            "mTime": mTime
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
        .dateGroup { margin-bottom: 2rem; background: white; padding: 1.2rem 1.5rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .dateGroup h2 { margin-top: 0; color: #0066cc; font-size: 1.25rem; }
        ul { list-style-type: none; padding-left: 0; margin: 0; }
        li { margin: 0.5rem 0; }
        a { color: #2b6cb0; text-decoration: none; font-weight: 500; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>Log Graphs</h1>
    <a href="csv-import.html">
        Import CSV
        <br>
        <br>
    </a>
"""

    for fileDate in sortedDates:
        htmlContent += f'    <div class="dateGroup">\n        <h2>{fileDate}</h2>\n        <ul>\n'
        groupedFiles[fileDate].sort(key=lambda item: item["mTime"], reverse=True)
        for item in groupedFiles[fileDate]:
            htmlContent += f'            <li><a href="{item["relativePath"]}">{item["fileName"]}</a></li>\n'
        htmlContent += '        </ul>\n    </div>\n'

    htmlContent += """</body>
</html>"""

    indexPath = os.path.join(baseDir, "index.html")
    with open(indexPath, "w", encoding="utf-8") as htmlFile:
        htmlFile.write(htmlContent)

@app.post("/upload")
def upload_and_sync(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file type")

    path_fileLocationCSV = os.path.join(PATH_CSV_FOLDER, file.filename)
    path_fileLocationHTML = os.path.join(PATH_HTML_FOLDER, file.filename)

    try:
        with open(path_fileLocationCSV, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        shutil.copyfile(path_fileLocationCSV, path_fileLocationHTML)

        subprocess.run(["perl", PATH_GRAPHING_SCRIPT, path_fileLocationHTML], check=True)
        
        if (os.path.exists(path_fileLocationHTML)): os.remove(path_fileLocationHTML)

        generateIndexHtml()

        commitMessage = f"New files {timestamp} (Automated)"
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", commitMessage], check=True)
        subprocess.run(["git", "push"], check=True)

        return {
            "status": "success",
            "message": f"'{file.filename}' graph successfully pushed",
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
