from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from docx_builder import build_output
from gemini_client import (
    GeminiError,
    classify_soal_or_perintah,
    suggest_quotes,
    suggest_steps,
)
from parser import parse_soal

APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")

app = FastAPI(title="Kemjar TP Helper")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/api/defaults")
def defaults() -> dict:
    return {
        "nama": os.environ.get("NAMA", ""),
        "npm": os.environ.get("NPM", ""),
        "kode_aslab": os.environ.get("KODE_ASLAB", ""),
        "tipe": os.environ.get("TIPE", "TP"),
    }


@app.post("/api/parse-soal")
async def parse_soal_endpoint(file: UploadFile) -> dict:
    content = await file.read()
    try:
        return parse_soal(content)
    except Exception as exc:  # noqa: BLE001 - surface a clear error to the UI
        raise HTTPException(status_code=400, detail=f"Gagal membaca file soal: {exc}") from exc


@app.post("/api/classify")
async def classify_endpoint(question_text: str = Form(...)) -> dict:
    """Have Gemini separate legitimate question text from any embedded
    instruction/command aimed at an AI or reader (prompt-injection defense)."""
    try:
        return classify_soal_or_perintah(question_text)
    except GeminiError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@app.post("/api/quotes")
async def quotes_endpoint(question_text: str = Form(...)) -> dict:
    try:
        return {"quotes": suggest_quotes(question_text)}
    except GeminiError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@app.post("/api/steps")
async def steps_endpoint(question_text: str = Form(...)) -> dict:
    try:
        return {"steps": suggest_steps(question_text)}
    except GeminiError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@app.post("/api/generate")
async def generate_endpoint(
    identity: str = Form(...),
    parts_answers: str = Form(...),
    template_file: Optional[UploadFile] = None,
    screenshots: list[UploadFile] | None = None,
) -> Response:
    try:
        identity_data = json.loads(identity)
        parts_answers_data = json.loads(parts_answers)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Data form tidak valid: {exc}") from exc

    images_by_item: dict[str, list[bytes]] = {}
    for upload in screenshots or []:
        # Filenames from the frontend are namespaced "part-number__originalname.ext"
        key = (upload.filename or "").split("__", 1)[0]
        images_by_item.setdefault(key, []).append(await upload.read())

    if template_file is not None and template_file.filename:
        template_bytes = await template_file.read()
    else:
        template_bytes = (APP_DIR / "assets" / "default_template.docx").read_bytes()

    try:
        docx_bytes = build_output(template_bytes, identity_data, parts_answers_data, images_by_item)
    except Exception as exc:  # noqa: BLE001 - surface a clear error to the UI
        raise HTTPException(status_code=400, detail=f"Gagal membuat dokumen: {exc}") from exc

    tipe = identity_data.get("tipe", "TP")
    kode_aslab = identity_data.get("kode_aslab", "")
    nama = identity_data.get("nama", "")
    npm = identity_data.get("npm", "")
    no_modul = identity_data.get("no_modul", "")
    filename = f"{tipe}_{kode_aslab}_{nama}_{npm}_Kemjar{no_modul}.docx"

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
