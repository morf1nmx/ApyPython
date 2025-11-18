import os
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import base64
import requests

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


CLOUD_NAME = "drsxop82w"
UPLOAD_PRESET = "visits_preset"


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_IxGQ1nUAiBY8@ep-raspy-cake-ad01wc64-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


@app.post("/insert_data")
async def insert_data(
    name: str = Form(...),
    comment: str = Form(None),
    photo: UploadFile = File(...)
):
    print("Petición recibida en /insert_data")
    print("FILE:", photo)


    if not photo:
        raise HTTPException(status_code=400, detail="No file provided")

    try:

        file_bytes = await photo.read()
        base64_image = f"data:{photo.content_type};base64,{base64.b64encode(file_bytes).decode()}"


        url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/image/upload"

        response = requests.post(url, data={
            "file": base64_image,
            "upload_preset": UPLOAD_PRESET,
            "folder": "visits"
        })

        if response.status_code != 200:
            print("ERROR SUBIENDO A CLOUDINARY:", response.text)
            raise HTTPException(status_code=500, detail=response.text)

        cloudinary_data = response.json()
        image_url = cloudinary_data["secure_url"]
        public_id = cloudinary_data["public_id"]

    except Exception as e:
        print("ERROR SUBIENDO A CLOUDINARY:", e)
        raise HTTPException(status_code=500, detail=f"Cloudinary upload failed: {str(e)}")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    insert_query = """
        INSERT INTO visits (name, comment, image_url, public_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, comment, image_url, public_id, created_at;
    """

    try:
        cur.execute(insert_query, (name, comment, image_url, public_id))
        new_visit = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")
    finally:
        cur.close()
        conn.close()

    return {
        "ok": True,
        "cloudinary": cloudinary_data,
        "data": new_visit
    }


@app.get("/get_data")
def get_data():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("""
            SELECT id, name, comment, image_url, public_id, created_at
            FROM visits
            ORDER BY created_at DESC;
        """)
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return rows
