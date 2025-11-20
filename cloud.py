import os
import time
import base64
from dotenv import load_dotenv

import requests
import psycopg2
import cloudinary
from cloudinary import utils

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi import Request
import httpx

# ============================
#  CARGA VARIABLES DE ENTORNO
# ============================
load_dotenv("credentials.env")

# ============================
#  CONFIGURACIÓN CLOUDINARY
# ============================
CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUD_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUD_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

if not all([CLOUD_NAME, CLOUD_API_KEY, CLOUD_API_SECRET]):
    raise RuntimeError("Faltan variables de entorno de Cloudinary")

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=CLOUD_API_KEY,
    api_secret=CLOUD_API_SECRET,
)

# ============================
#  CONFIGURACIÓN DB (NEON)
# ============================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta variable de entorno DATABASE_URL")

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        # Error crítico de conexión a base de datos
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")


# ============================
#  APP FASTAPI
# ============================
app = FastAPI()



from fastapi import Request
import httpx

WORKER_URL = "https://gentle-breeze-d28f.jonasanchez1993.workers.dev/track"

@app.middleware("http")
async def track_middleware(request: Request, call_next):
    endpoint = request.url.path  # Ej: "/upload" o "/get_data"

    # Evitar tracking de docs o rutas internas
    if endpoint not in ["/docs", "/openapi.json"] and not endpoint.startswith("/internal"):
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                await client.post(WORKER_URL, json={
                    "tipo": "backend/",                      # prefijo profesional
                    "ruta": endpoint.replace("/", "")        # "/upload" → "upload"
                })
        except:
            pass  # Nunca rompe tu backend si Cloudflare falla

    response = await call_next(request)
    return response


# CORS: ajusta los orígenes permitidos según tu frontend
# (por ejemplo: Vercel + localhost para desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://infraestructure-cloud.vercel.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
#  ENDPOINT: SUBIR IMAGEN Y GUARDAR VISITA
# ============================
@app.post("/upload")
async def upload_image(
    name: str = Form(...),        # campo form-data
    comment: str = Form(...),     # campo form-data
    public_id: str = Form(...),   # ID que envía el cliente (no el de Cloudinary)
    photo: UploadFile = File(...) # archivo en form-data
):
    print("📥 Petición recibida en /upload")

    # Validar tipo de archivo
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    # Leer archivo
    file_bytes = await photo.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="No file provided")

    # ==========================
    #  SUBIR A CLOUDINARY
    # ==========================
    folder = "visits"
    timestamp = int(time.time())

    try:
        # Firmar la petición
        signature = utils.api_sign_request(
            {"folder": folder, "timestamp": timestamp},
            CLOUD_API_SECRET
        )

        # Convertir a base64
        content_type = photo.content_type
        file_base64 = (
            f"data:{content_type};base64,"
            f"{base64.b64encode(file_bytes).decode('utf-8')}"
        )

        # Petición a Cloudinary
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/image/upload",
            data={
                "file": file_base64,
                "folder": folder,
                "api_key": CLOUD_API_KEY,
                "timestamp": timestamp,
                "signature": signature,
            },
            timeout=30,
        )

        if response.status_code != 200:
            print("❌ Error al subir a Cloudinary:", response.text)
            raise HTTPException(
                status_code=response.status_code,
                detail="Upload to Cloudinary failed",
            )

        cloudinary_response = response.json()
        uploaded_url = cloudinary_response.get("url") or cloudinary_response.get("secure_url")

        if not uploaded_url:
            raise HTTPException(status_code=500, detail="Cloudinary did not return an image URL")

    except HTTPException:
        # ya se lanzó un error manejado
        raise
    except Exception as error:
        print("❌ ERROR SUBIENDO A CLOUDINARY:", error)
        raise HTTPException(status_code=500, detail=f"Upload to Cloudinary failed: {str(error)}")

    # ==========================
    #  INSERTAR EN POSTGRES
    # ==========================
    conn = get_db_connection()
    cur = conn.cursor()

    insert_query = """
        INSERT INTO visits (name, comment, image_url, public_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, comment, image_url, public_id, created_at;
    """

    try:
        cur.execute(insert_query, (name, comment, uploaded_url, public_id))
        result = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("❌ ERROR EN DB:", e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()

    return {
        "ok": True,
        "cloudinary": cloudinary_response,
        "database": jsonable_encoder(result),
    }


# ============================
#  ENDPOINT: LISTAR VISITAS
# ============================
@app.get("/get_data")
def list_visits():
    conn = get_db_connection()
    cur = conn.cursor()

    select_query = """
        SELECT id, name, comment, image_url, public_id, created_at
        FROM visits
        ORDER BY created_at DESC;
    """

    try:
        cur.execute(select_query)
        rows = cur.fetchall()

        # nombres de columnas
        col_names = [desc[0] for desc in cur.description]

        # lista de dicts
        visits = [dict(zip(col_names, row)) for row in rows]

        # asegurar que todo sea serializable (fechas, etc.)
        visits = jsonable_encoder(visits)

    except Exception as e:
        print("❌ ERROR LISTANDO VISITAS:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

    # Mantengo el formato que ya usabas: lista directa
    return visits