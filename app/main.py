from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .errors import AppError
from .filesystem import JobPaths, JobStore, safe_filename
from .service import COMMON_ENCODINGS, PylabviewService


LOGGER = logging.getLogger("pylabview_web")
STATIC_ROOT = Path(__file__).resolve().parent / "static"


class RebuildRequest(BaseModel):
    output_name: str | None = Field(default=None, max_length=180)
    text_encoding: str | None = Field(default=None, max_length=64)
    verbosity: int = Field(default=1, ge=0, le=3)


async def save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise AppError(
                        "アップロードサイズが上限を超えています。",
                        code="upload_too_large",
                        status_code=413,
                        details={"max_bytes": max_bytes},
                    )
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    if total == 0:
        destination.unlink(missing_ok=True)
        raise AppError("空のファイルは処理できません。", code="empty_upload", status_code=422)
    return total


def mark_failed(store: JobStore, paths: JobPaths, exc: Exception) -> None:
    try:
        metadata = store.load(paths)
        metadata["status"] = "failed"
        if isinstance(exc, AppError):
            metadata["error"] = exc.as_dict()
        else:
            metadata["error"] = {"code": "internal_error", "message": str(exc)}
        store.save(paths, metadata)
    except Exception:
        LOGGER.exception("Failed to update job state for %s", paths.job_id)


def create_app(
    settings: Settings | None = None,
    store: JobStore | None = None,
    service: PylabviewService | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    active_store = store or JobStore(active_settings)
    active_service = service or PylabviewService(active_settings, active_store)

    app = FastAPI(
        title="pylabview VI/XML Workbench",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = active_settings
    app.state.store = active_store
    app.state.service = active_service

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.as_dict()})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "入力値を確認してください。",
                    "details": {"errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled request error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "内部エラーが発生しました。コンテナログを確認してください。",
                }
            },
        )

    @app.middleware("http")
    async def request_guards(request: Request, call_next):  # type: ignore[no-untyped-def]
        content_length = request.headers.get("content-length")
        if content_length and request.url.path.startswith(("/api/convert/", "/api/jobs/")):
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            # Allow multipart and JSON framing overhead beyond the raw upload limit.
            if declared > active_settings.max_upload_bytes + 4 * 1024 * 1024:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "upload_too_large",
                            "message": "リクエストサイズが上限を超えています。",
                            "details": {"max_bytes": active_settings.max_upload_bytes},
                        }
                    },
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers[
            "Content-Security-Policy"
        ] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'"
        return response

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        probe = await asyncio.to_thread(active_service.probe)
        return {
            "status": "ok" if probe.get("available") else "degraded",
            "pylabview": probe,
            "limits": {
                "max_upload_bytes": active_settings.max_upload_bytes,
                "max_archive_bytes": active_settings.max_archive_bytes,
                "inline_xml_max_bytes": active_settings.inline_xml_max_bytes,
                "job_ttl_hours": active_settings.job_ttl_hours,
            },
            "encodings": list(COMMON_ENCODINGS),
        }

    @app.post("/api/convert/vi-to-xml")
    async def vi_to_xml(
        file: UploadFile = File(...),
        text_encoding: str = Form("shift_jis"),
        verbosity: int = Form(1),
        raw_connectors: bool = Form(False),
        verify_roundtrip: bool = Form(True),
    ) -> dict[str, Any]:
        paths = active_store.create("vi_to_xml")
        try:
            filename = safe_filename(file.filename, "input.vi")
            source_path = paths.input / filename
            await save_upload(file, source_path, active_settings.max_upload_bytes)
            return await asyncio.to_thread(
                active_service.extract_vi,
                paths,
                source_path,
                text_encoding=text_encoding,
                verbosity=verbosity,
                raw_connectors=raw_connectors,
                verify_roundtrip=verify_roundtrip,
            )
        except Exception as exc:
            mark_failed(active_store, paths, exc)
            raise

    @app.post("/api/convert/xml-to-vi")
    async def xml_to_vi(
        dataset: UploadFile = File(...),
        main_xml: str = Form(""),
        output_name: str = Form(""),
        text_encoding: str = Form("shift_jis"),
        verbosity: int = Form(1),
    ) -> dict[str, Any]:
        paths = active_store.create("xml_to_vi")
        try:
            filename = safe_filename(dataset.filename, "dataset.zip")
            upload_path = paths.input / filename
            await save_upload(dataset, upload_path, active_settings.max_upload_bytes)
            await asyncio.to_thread(
                active_service.import_dataset,
                paths,
                upload_path,
                original_name=filename,
                main_xml_hint=main_xml or None,
                text_encoding=text_encoding,
            )
            return await asyncio.to_thread(
                active_service.rebuild,
                paths,
                output_name=output_name or None,
                text_encoding=text_encoding,
                verbosity=verbosity,
            )
        except Exception as exc:
            mark_failed(active_store, paths, exc)
            raise

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        paths = active_store.get(job_id)
        return active_service.public_metadata(paths)

    @app.get("/api/jobs/{job_id}/xml")
    async def get_xml(job_id: str) -> Response:
        paths = active_store.get(job_id)
        content = await asyncio.to_thread(active_service.read_main_xml, paths)
        return Response(content=content, media_type="application/xml; charset=utf-8")

    @app.put("/api/jobs/{job_id}/xml")
    async def put_xml(job_id: str, request: Request) -> dict[str, Any]:
        paths = active_store.get(job_id)
        content = await request.body()
        return await asyncio.to_thread(active_service.update_main_xml, paths, content)

    @app.post("/api/jobs/{job_id}/rebuild")
    async def rebuild(job_id: str, payload: RebuildRequest) -> dict[str, Any]:
        paths = active_store.get(job_id)
        try:
            return await asyncio.to_thread(
                active_service.rebuild,
                paths,
                output_name=payload.output_name,
                text_encoding=payload.text_encoding,
                verbosity=payload.verbosity,
            )
        except Exception as exc:
            mark_failed(active_store, paths, exc)
            raise

    @app.get("/api/jobs/{job_id}/download/{artifact_name}")
    async def download_artifact(job_id: str, artifact_name: str) -> FileResponse:
        paths = active_store.get(job_id)
        artifact = active_service.artifact_path(paths, artifact_name)
        media_type = {
            "dataset": "application/zip",
            "main_xml": "application/xml",
        }.get(artifact_name, "application/octet-stream")
        return FileResponse(artifact, media_type=media_type, filename=artifact.name)

    @app.delete("/api/jobs/{job_id}")
    async def delete_job(job_id: str) -> dict[str, Any]:
        await asyncio.to_thread(active_store.delete, job_id)
        return {"deleted": True, "job_id": job_id}

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(STATIC_ROOT / "favicon.svg", media_type="image/svg+xml")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
    return app


app = create_app()
