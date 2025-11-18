import os
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Permitir CORS (útil para frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_IxGQ1nUAiBY8@ep-raspy-cake-ad01wc64-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


# --- MODELOS Pydantic ---
class VisitCreate(BaseModel):
    name: str
    comment: Optional[str] = None
    image_url: Optional[str] = None
    public_id: str


# --- ENDPOINT PARA INSERTAR ---
@app.post("/insert_data")
def create_visit(data: VisitCreate):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    insert_query = """
        INSERT INTO visits (name, comment, image_url, public_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, comment, image_url, public_id, created_at;
    """

    try:
        cur.execute(insert_query, (data.name, data.comment, data.image_url, data.public_id))
        new_visit = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

    return new_visit


# --- ENDPOINT PARA LISTAR ---
@app.get("/get_data")
def list_visits():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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