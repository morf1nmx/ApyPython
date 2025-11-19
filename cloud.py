import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import cloudinary
from cloudinary import utils
import base64
import psycopg2
from dotenv import load_dotenv
from typing import Optional
from pydantic import BaseModel
import time

# Cargar variables de entorno
load_dotenv("credentials.env")  # Asegúrate de que este archivo exista con las claves

app = FastAPI()

# Permitir CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar Cloudinary con variables de entorno
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

# --- MODELOS Pydantic ---
class VisitCreate(BaseModel):
    name: str
    comment: Optional[str] = None
    image_url: Optional[str] = None
    public_id: Optional[str] = None  # Ahora opcional, se recibe del form-data

# Conexión a DB
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_IxGQ1nUAiBY8@ep-raspy-cake-ad01wc64-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

@app.post("/upload")
async def upload_image(
    name: str = Form(...),  # Requerido en form-data
    comment: str = Form(...),  # Requerido en form-data
    public_id: str = Form(...),  # Requerido en form-data (el ID que envía el cliente)
    photo: UploadFile = File(...)  # Archivo en form-data
):
    print("Petición recibida en /upload")
    
    # Validar que sea un archivo de imagen
    if not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    
    if not photo.file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    try:
        folder = "visits"
        timestamp = int(time.time())
        
        # Generar firma segura
        signature = utils.api_sign_request(
            {"folder": folder, "timestamp": timestamp},
            os.getenv("CLOUDINARY_API_SECRET")
        )
        
        # Leer el archivo y convertir a base64
        file_bytes = await photo.read()
        content_type = photo.content_type
        file_base64 = f"data:{content_type};base64,{base64.b64encode(file_bytes).decode('utf-8')}"
        
        # Subir a Cloudinary
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{os.getenv('CLOUDINARY_CLOUD_NAME')}/image/upload",
            data={
                "file": file_base64,
                "folder": folder,
                "api_key": os.getenv("CLOUDINARY_API_KEY"),
                "timestamp": timestamp,
                "signature": signature,
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Upload to Cloudinary failed")
        
        cloudinary_response = response.json()
        uploaded_url = cloudinary_response.get("url")
        # Nota: public_id se usa el del form-data, no el de Cloudinary
        
        # Insertar en PostgreSQL
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
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        finally:
            cur.close()
            conn.close()
        
        return {
            "ok": True,
            "cloudinary": cloudinary_response,
            "database": result,  # Devuelve el registro insertado
        }
    
    except Exception as error:
        print("ERROR SUBIENDO ")
        print(error)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(error)}")
    
# --- ENDPOINT PARA LISTAR ---
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
        visits = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

    return visits