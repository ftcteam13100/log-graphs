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

        shutil.copyfile(path_fileLocationCSV, path_fileLocationHTML)

        subprocess.run(["perl", PATH_GRAPHING_SCRIPT, path_fileLocationHTML], check=True)
        
        if (os.path.exists(path_fileLocationHTML)): os.remove(path_fileLocationHTML)

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
