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
timestamp = datetime.now().strftime("%m/%d/%y|%H:%M:%S")

PATH_GRAPHING_SCRIPT = "plotData.pl"
PATH_CSV_FOLDER = f"/home/skorada/ftc-csv-grapher/log-graphs/CSV/{year}/{month}"
PATH_HTML_FOLDER = f"/home/skorada/ftc-csv-grapher/log-graphs/HTML/{year}/{month}"

os.makedirs(PATH_CSV_FOLDER, exist_ok=True)
os.makedirs(PATH_HTML_FOLDER, exist_ok=True)

@app.post("/upload")
def upload_and_sync(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file type")

    path_fileLocationCSV = os.path.join(PATH_CSV_FOLDER, file.filename)
    path_fileLocationHTML = os.path.join(PATH_HTML_FOLDER, file.filename)

    try:
        with open(path_fileLocationCSV, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with open(path_fileLocationHTML, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        subprocess.run(["perl", PATH_GRAPHING_SCRIPT, path_fileLocationHTML], check=True)

        path_homeHTML = os.path.splitext(file.filename)[0] + ".html"

        htmlFiles = glob("log-graphs/HTML/**/*.html", recursive=True)
        htmlFiles.sort(key=os.path.getmtime, reverse=True)

        list_items = []
        for filepath in htmlFiles:
            web_path = filepath.replace("\\", "/")
            filename = os.path.basename(filepath)

            if filename == path_homeHTML:
                item = f'<li class="highlight"><strong><a href="{web_path}">{filename}</a> (Newest / Just Uploaded)</strong></li>'
            else:
                item = f'<li><a href="{web_path}">{filename}</a></li>'

            list_items.append(item)

        items_rendered = "\n            ".join(list_items)

        index_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Log Graphs Index</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
h1 {{ color: #333; }}
ul {{ list-style-type: none; padding: 0; }}
li {{ margin: 8px 0; padding: 8px; border-radius: 4px; background: #f4f4f4; }}
li.highlight {{ background: #e0f7fa; border-left: 5px solid #00acc1; }}
a {{ text-decoration: none; color: #007bff; }}
a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>Generated Log Graphs</h1>
<p>Last updated: {timestamp}</p>
<ul>
        {items_rendered}
</ul>
</body>
</html>
"""

        index_file_path = "/home/skorada/ftc-csv-grapher/index.html"
        with open(index_file_path, "w", encoding="utf-8") as f:
            f.write(index_content)

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
