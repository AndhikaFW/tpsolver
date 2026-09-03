from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from docx_builder import build_output
from gemini_client import (
    GeminiError,
    classify_soal_or_perintah,
    classify_soal_or_perintah_batch,
    suggest_quotes,
    suggest_quotes_batch,
    suggest_steps,
    suggest_steps_batch,
)
from parser import parse_soal


def _parse_items_form(items: str) -> list[str]:
    try:
        item_texts = json.loads(items)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Data items tidak valid: {exc}") from exc
    if not isinstance(item_texts, list) or not all(isinstance(x, str) for x in item_texts):
        raise HTTPException(status_code=400, detail="items harus berupa array string")
    return item_texts

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
        return await run_in_threadpool(classify_soal_or_perintah, question_text)
    except GeminiError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@app.post("/api/classify-batch")
async def classify_batch_endpoint(items: str = Form(...)) -> dict:
    """Same as /api/classify but for the whole soal's items in one Gemini call,
    used for the auto-classify pass that runs right after parsing so it
    doesn't fire one request per item."""
    item_texts = _parse_items_form(items)
    try:
        return {"results": await run_in_threadpool(classify_soal_or_perintah_batch, item_texts)}
    except GeminiError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@app.post("/api/quotes-batch")
async def quotes_batch_endpoint(items: str = Form(...)) -> dict:
    """Same as /api/quotes but for every Part 1 item in one Gemini call, used
    for the auto-fill pass that runs right after parsing/classifying."""
    item_texts = _parse_items_form(items)
    try:
        return {"results": await run_in_threadpool(suggest_quotes_batch, item_texts)}
    except GeminiError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@app.post("/api/steps-batch")
async def steps_batch_endpoint(items: str = Form(...)) -> dict:
    """Same as /api/steps but for every Part 2 item in one Gemini call, used
    for the auto-fill pass that runs right after parsing/classifying."""
    item_texts = _parse_items_form(items)
    try:
        return {"results": await run_in_threadpool(suggest_steps_batch, item_texts)}
    except GeminiError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@app.post("/api/quotes")
async def quotes_endpoint(question_text: str = Form(...)) -> dict:
    try:
        return {"quotes": await run_in_threadpool(suggest_quotes, question_text)}
    except GeminiError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@app.post("/api/steps")
async def steps_endpoint(question_text: str = Form(...)) -> dict:
    try:
        return {"steps": await run_in_threadpool(suggest_steps, question_text)}
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
