from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
import requests
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload")
async def upload_image(photo: UploadFile = File(...)):
    if not photo.file:
        raise HTTPException(status_code=400, detail="No file provided")

    try:
        cloud_name = "drsxop82w"
        upload_preset = "visits_preset"
        file_bytes = await photo.read()
        base64_image = f"data:{photo.content_type};base64,{base64.b64encode(file_bytes).decode('utf-8')}"

        url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
        response = requests.post(url, data={
            "file": base64_image,
            "upload_preset": upload_preset,
            "folder": "visits"
        })

        if response.status_code != 200:
            try:
                error_detail = response.json().get("error", {}).get("message", response.text)
            except json.JSONDecodeError:
                error_detail = response.text
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Cloudinary Upload Failed: {error_detail}"
            )


        cloudinary_response = response.json()

        uploaded_url = cloudinary_response.get("url")

        secure_url = cloudinary_response.get("secure_url")

        return {
            "ok": True,
            "cloudinary": cloudinary_response,
            "uploaded_url": uploaded_url,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
