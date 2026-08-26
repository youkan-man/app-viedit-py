from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from defusedxml import ElementTree as SafeET
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.services.pylabview_service import (
    CommandResult,
    ConversionError,
    PylabviewService,
)
from app.services.workspace import (
    ALLOWED_OUTPUT_EXTENSIONS,
    InvalidArchiveError,
    JobNotFoundError,
    JobPaths,
    UploadTooLargeError,
    WorkspaceError,
    WorkspaceManager,
    sanitize_filename,
    sanitize_output_filename,
    sha256_file,
    utc_now_iso,
)

BASE_DIR = Path(__file__).resolve().parent


class XmlUpdate(BaseModel):
    content: str = Field(min_length=1)


class RebuildRequest(BaseModel):
    output_filename: str | None = None
    text_encoding: str | None = None


class AppServices:
    def __init__(
        self,
        settings: Settings,
        converter: PylabviewService | None = None,
    ) -> None:
        self.settings = settings
        self.workspaces = WorkspaceManager(settings)
        self.converter = converter or PylabviewService(settings)


def _validate_encoding(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 64 or any(ch.isspace() for ch in value):
        raise WorkspaceError("Invalid text encoding name")
    try:
        "".encode(value)
    except LookupError as exc:
        raise WorkspaceError(f"Unknown text encoding: {value}") from exc
    return value


def _validate_main_xml(path: Path) -> None:
    try:
        root = SafeET.parse(path).getroot()
    except Exception as exc:  # defusedxml and ElementTree expose multiple parse errors
        raise WorkspaceError(f"Invalid or unsafe XML: {exc}") from exc
    tag = root.tag.rsplit("}", 1)[-1] if isinstance(root.tag, str) else ""
    if tag != "RSRC":
        raise WorkspaceError(
            f"The main XML root must be <RSRC>; found <{tag or 'unknown'}>"
        )


def _command_error_log(exc: ConversionError) -> str:
    command = " ".join(exc.command)
    sections = [f"$ {command}" if command else "$ <unavailable>"]
    if exc.returncode is not None:
        sections.append(f"exit: {exc.returncode}")
    sections.extend(["", "[error]", str(exc)])
    if exc.stdout:
        sections.extend(["", "[stdout]", exc.stdout.rstrip()])
    if exc.stderr:
        sections.extend(["", "[stderr]", exc.stderr.rstrip()])
    return "\n".join(sections).rstrip() + "\n"


def _write_log(paths: JobPaths, name: str, value: CommandResult | ConversionError) -> str:
    filename = sanitize_filename(name, fallback="conversion.log")
    if not filename.endswith(".log"):
        filename += ".log"
    text = value.log_text if isinstance(value, CommandResult) else _command_error_log(value)
    (paths.logs / filename).write_text(text, encoding="utf-8")
    return filename


def _public_job(services: AppServices, paths: JobPaths) -> dict[str, object]:
    meta = services.workspaces.read_meta(paths)
    meta["dataset_files"] = services.workspaces.list_dataset_files(paths)
    return meta


def _default_rebuilt_name(source_name: str | None) -> str:
    if not source_name:
        return "rebuilt.vi"
    source = Path(source_name)
    suffix = source.suffix.lower()
    if suffix not in ALLOWED_OUTPUT_EXTENSIONS:
        suffix = ".vi"
    stem = source.stem or "instrument"
    return sanitize_output_filename(f"rebuilt-{stem}{suffix}")


def _perform_rebuild(
    services: AppServices,
    paths: JobPaths,
    *,
    output_filename: str,
    text_encoding: str,
    log_name: str,
) -> tuple[Path, CommandResult]:
    meta = services.workspaces.read_meta(paths)
    main_relative = meta.get("main_xml")
    if not isinstance(main_relative, str):
        raise WorkspaceError("Job does not contain a main XML file")
    main_xml = services.workspaces.resolve_dataset_file(paths, main_relative)
    _validate_main_xml(main_xml)
    output_name = sanitize_output_filename(output_filename)
    output = paths.outputs / output_name
    try:
        result = services.converter.create(
            main_xml,
            output,
            text_encoding=_validate_encoding(text_encoding),
        )
    except ConversionError as exc:
        log_file = _write_log(paths, log_name, exc)
        services.workspaces.update_meta(
            paths,
            status="failed",
            error=str(exc),
            last_log=log_file,
        )
        raise
    log_file = _write_log(paths, log_name, result)
    output_info = {
        "name": output.name,
        "size": output.stat().st_size,
        "sha256": sha256_file(output),
        "created_at": utc_now_iso(),
    }
    existing = meta.get("outputs")
    outputs = (
        [item for item in existing if isinstance(item, dict)]
        if isinstance(existing, list)
        else []
    )
    outputs = [item for item in outputs if item.get("name") != output.name]
    outputs.append(output_info)
    services.workspaces.update_meta(
        paths,
        status="ready",
        error=None,
        outputs=outputs,
        last_log=log_file,
        text_encoding=text_encoding,
    )
    return output, result


def create_app(
    settings: Settings | None = None,
    *,
    converter: PylabviewService | None = None,
) -> FastAPI:
    services = AppServices(settings or Settings(), converter=converter)
    application = FastAPI(
        title="VI Edit",
        version="1.0.0",
        description="LabVIEW RSRC/VI ↔ pylabview XML dataset converter",
        docs_url="/api/docs",
        redoc_url=None,
    )
    application.state.services = services
    application.mount(
        "/static", StaticFiles(directory=BASE_DIR / "static"), name="static"
    )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            request_limit = max(
                services.settings.max_upload_bytes,
                services.settings.max_xml_editor_bytes,
            ) + (2 * 1024 * 1024)
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > request_limit:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "Request body exceeds the configured limit"},
                        )
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Invalid Content-Length header"},
                    )

            if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-site requests are not allowed"},
                )
            origin = request.headers.get("origin")
            host = request.headers.get("host", "")
            if origin and urlsplit(origin).netloc.lower() != host.lower():
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Request origin does not match this host"},
                )

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            )
        return response

    @application.exception_handler(JobNotFoundError)
    async def job_not_found_handler(_: Request, exc: JobNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(UploadTooLargeError)
    async def upload_too_large_handler(
        _: Request, exc: UploadTooLargeError
    ) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(exc)})

    @application.exception_handler(InvalidArchiveError)
    async def invalid_archive_handler(
        _: Request, exc: InvalidArchiveError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.exception_handler(WorkspaceError)
    async def workspace_error_handler(_: Request, exc: WorkspaceError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.exception_handler(ConversionError)
    async def conversion_error_handler(_: Request, exc: ConversionError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @application.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse((BASE_DIR / "templates" / "index.html").read_text("utf-8"))

    @application.get("/api/health")
    async def health() -> dict[str, object]:
        return {"status": "ok", "version": application.version}

    @application.get("/api/runtime")
    async def runtime() -> dict[str, object]:
        return {
            "app": {"version": application.version},
            "pylabview": await run_in_threadpool(services.converter.health),
            "limits": {
                "max_upload_bytes": services.settings.max_upload_bytes,
                "max_xml_editor_bytes": services.settings.max_xml_editor_bytes,
                "job_ttl_seconds": services.settings.job_ttl_seconds,
            },
            "default_text_encoding": services.settings.default_text_encoding,
        }

    @application.post("/api/extract", status_code=201)
    async def extract_vi(
        file: Annotated[UploadFile, File(...)],
        text_encoding: Annotated[str, Form()] = services.settings.default_text_encoding,
        raw_connectors: Annotated[bool, Form()] = False,
        verify_roundtrip: Annotated[bool, Form()] = True,
    ) -> dict[str, object]:
        encoding = _validate_encoding(text_encoding)
        paths = services.workspaces.create_job(kind="extract")
        source: Path | None = None
        try:
            source = await services.workspaces.save_upload(
                file, paths.source, fallback_name="instrument.vi"
            )
            if source.suffix.lower() not in ALLOWED_OUTPUT_EXTENSIONS:
                raise WorkspaceError(
                    "Unsupported source extension. Expected a VI/CTL/LLB/RSRC file."
                )
            services.workspaces.update_meta(
                paths,
                status="processing",
                source={
                    "name": source.name,
                    "size": source.stat().st_size,
                    "sha256": sha256_file(source),
                },
                text_encoding=encoding,
                raw_connectors=raw_connectors,
                verify_roundtrip=verify_roundtrip,
                default_output_filename=_default_rebuilt_name(source.name),
            )
            try:
                main_xml, result = await run_in_threadpool(
                    services.converter.extract,
                    source,
                    paths.dataset,
                    main_xml_name="main.xml",
                    text_encoding=encoding,
                    raw_connectors=raw_connectors,
                )
            except ConversionError as exc:
                log_file = _write_log(paths, "extract.log", exc)
                services.workspaces.update_meta(
                    paths,
                    status="failed",
                    error=str(exc),
                    last_log=log_file,
                )
                raise

            extract_log = _write_log(paths, "extract.log", result)
            _validate_main_xml(main_xml)
            bundle = await run_in_threadpool(
                services.workspaces.create_dataset_bundle, paths, main_xml
            )
            verification: dict[str, object] = {"requested": verify_roundtrip}

            if verify_roundtrip:
                roundtrip_name = sanitize_output_filename(
                    f"roundtrip-{source.stem}{source.suffix.lower()}"
                )
                roundtrip_path = paths.outputs / roundtrip_name
                try:
                    roundtrip_result = await run_in_threadpool(
                        services.converter.create,
                        main_xml,
                        roundtrip_path,
                        text_encoding=encoding,
                    )
                    roundtrip_log = _write_log(
                        paths, "roundtrip.log", roundtrip_result
                    )
                    original_hash = sha256_file(source)
                    rebuilt_hash = sha256_file(roundtrip_path)
                    verification.update(
                        {
                            "status": "identical"
                            if original_hash == rebuilt_hash
                            else "different",
                            "binary_identical": original_hash == rebuilt_hash,
                            "original_sha256": original_hash,
                            "rebuilt_sha256": rebuilt_hash,
                            "original_size": source.stat().st_size,
                            "rebuilt_size": roundtrip_path.stat().st_size,
                            "output_name": roundtrip_path.name,
                            "log": roundtrip_log,
                        }
                    )
                except ConversionError as exc:
                    roundtrip_log = _write_log(paths, "roundtrip.log", exc)
                    verification.update(
                        {"status": "failed", "error": str(exc), "log": roundtrip_log}
                    )

            services.workspaces.update_meta(
                paths,
                status="ready",
                main_xml=main_xml.relative_to(paths.dataset).as_posix(),
                bundle=bundle.name,
                extract_log=extract_log,
                verification=verification,
                error=None,
            )
            return _public_job(services, paths)
        except Exception as exc:
            meta = services.workspaces.read_meta(paths)
            if meta.get("status") != "failed":
                services.workspaces.update_meta(
                    paths,
                    status="failed",
                    error=str(exc) or exc.__class__.__name__,
                )
            raise

    @application.post("/api/import", status_code=201)
    async def import_xml_dataset(
        files: Annotated[list[UploadFile], File(...)],
        main_xml_name: Annotated[str, Form()] = "",
        output_filename: Annotated[str, Form()] = "rebuilt.vi",
        text_encoding: Annotated[str, Form()] = services.settings.default_text_encoding,
    ) -> dict[str, object]:
        if not files:
            raise WorkspaceError("Select an XML dataset or ZIP bundle")
        encoding = _validate_encoding(text_encoding)
        output_name = sanitize_output_filename(output_filename)
        paths = services.workspaces.create_job(kind="import")
        services.workspaces.update_meta(
            paths,
            status="processing",
            text_encoding=encoding,
            default_output_filename=output_name,
        )
        saved: list[Path] = []
        total = 0
        try:
            if len(files) == 1 and Path(files[0].filename or "").suffix.lower() == ".zip":
                archive = await services.workspaces.save_upload(
                    files[0], paths.source, fallback_name="dataset.zip"
                )
                await run_in_threadpool(
                    services.workspaces.extract_zip_safely, archive, paths.dataset
                )
                saved.append(archive)
            else:
                for upload in files:
                    destination = await services.workspaces.save_upload(
                        upload, paths.dataset, fallback_name="dataset-file.bin"
                    )
                    saved.append(destination)
                    total += destination.stat().st_size
                    if total > services.settings.max_upload_bytes:
                        raise UploadTooLargeError(
                            "Combined upload exceeds the configured upload limit"
                        )

            preferred = main_xml_name.strip() or None
            main_xml = await run_in_threadpool(
                services.workspaces.find_main_xml, paths.dataset, preferred
            )
            await run_in_threadpool(_validate_main_xml, main_xml)
            bundle = await run_in_threadpool(
                services.workspaces.create_dataset_bundle, paths, main_xml
            )
            services.workspaces.update_meta(
                paths,
                main_xml=main_xml.relative_to(paths.dataset).as_posix(),
                bundle=bundle.name,
            )
            output, _ = await run_in_threadpool(
                _perform_rebuild,
                services,
                paths,
                output_filename=output_name,
                text_encoding=encoding,
                log_name="rebuild.log",
            )
            services.workspaces.update_meta(
                paths,
                imported_files=[path.name for path in saved],
                rebuilt_output=output.name,
            )
            return _public_job(services, paths)
        except Exception as exc:
            meta = services.workspaces.read_meta(paths)
            if meta.get("status") != "failed":
                services.workspaces.update_meta(
                    paths,
                    status="failed",
                    error=str(exc) or exc.__class__.__name__,
                )
            raise

    @application.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, object]:
        return _public_job(services, services.workspaces.get_job(job_id))

    @application.get("/api/jobs/{job_id}/xml", response_class=PlainTextResponse)
    async def get_xml(job_id: str) -> PlainTextResponse:
        paths = services.workspaces.get_job(job_id)
        meta = services.workspaces.read_meta(paths)
        main_relative = meta.get("main_xml")
        if not isinstance(main_relative, str):
            raise JobNotFoundError("Job does not contain main XML")
        main_xml = services.workspaces.resolve_dataset_file(paths, main_relative)
        if main_xml.stat().st_size > services.settings.max_xml_editor_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Main XML is too large for the browser editor. "
                    "Download and edit the dataset bundle instead."
                ),
            )
        try:
            content = main_xml.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("Main XML is not valid UTF-8") from exc
        return PlainTextResponse(content, media_type="application/xml; charset=utf-8")

    @application.put("/api/jobs/{job_id}/xml")
    async def update_xml(job_id: str, update: XmlUpdate) -> dict[str, object]:
        encoded = update.content.encode("utf-8")
        if len(encoded) > services.settings.max_xml_editor_bytes:
            raise UploadTooLargeError("Edited XML exceeds the browser editor limit")
        paths = services.workspaces.get_job(job_id)
        meta = services.workspaces.read_meta(paths)
        main_relative = meta.get("main_xml")
        if not isinstance(main_relative, str):
            raise JobNotFoundError("Job does not contain main XML")
        main_xml = services.workspaces.resolve_dataset_file(paths, main_relative)
        backup = paths.source / "main.original.xml"
        if not backup.exists():
            shutil.copy2(main_xml, backup)
        temporary = main_xml.with_name(f".{main_xml.name}.new")
        temporary.write_bytes(encoded)
        try:
            _validate_main_xml(temporary)
            temporary.replace(main_xml)
        finally:
            temporary.unlink(missing_ok=True)
        bundle = await run_in_threadpool(
            services.workspaces.create_dataset_bundle, paths, main_xml
        )
        services.workspaces.update_meta(
            paths,
            xml_modified_at=utc_now_iso(),
            bundle=bundle.name,
            status="ready",
            error=None,
        )
        return _public_job(services, paths)

    @application.post("/api/jobs/{job_id}/rebuild")
    async def rebuild(job_id: str, request: RebuildRequest) -> dict[str, object]:
        paths = services.workspaces.get_job(job_id)
        meta = services.workspaces.read_meta(paths)
        requested_name = request.output_filename or meta.get("default_output_filename")
        output_name = sanitize_output_filename(
            requested_name if isinstance(requested_name, str) else "rebuilt.vi"
        )
        requested_encoding = request.text_encoding or meta.get("text_encoding")
        encoding = _validate_encoding(
            requested_encoding
            if isinstance(requested_encoding, str)
            else services.settings.default_text_encoding
        )
        output, _ = await run_in_threadpool(
            _perform_rebuild,
            services,
            paths,
            output_filename=output_name,
            text_encoding=encoding,
            log_name="rebuild.log",
        )
        services.workspaces.update_meta(paths, rebuilt_output=output.name)
        return _public_job(services, paths)

    @application.get("/api/jobs/{job_id}/bundle")
    async def download_bundle(job_id: str) -> FileResponse:
        paths = services.workspaces.get_job(job_id)
        meta = services.workspaces.read_meta(paths)
        main_relative = meta.get("main_xml")
        if not isinstance(main_relative, str):
            raise JobNotFoundError("Job does not contain main XML")
        main_xml = services.workspaces.resolve_dataset_file(paths, main_relative)
        bundle = await run_in_threadpool(
            services.workspaces.create_dataset_bundle, paths, main_xml
        )
        return FileResponse(
            bundle,
            media_type="application/zip",
            filename=f"{job_id}-pylabview-dataset.zip",
        )

    @application.get("/api/jobs/{job_id}/xml/download")
    async def download_main_xml(job_id: str) -> FileResponse:
        paths = services.workspaces.get_job(job_id)
        meta = services.workspaces.read_meta(paths)
        main_relative = meta.get("main_xml")
        if not isinstance(main_relative, str):
            raise JobNotFoundError("Job does not contain main XML")
        main_xml = services.workspaces.resolve_dataset_file(paths, main_relative)
        return FileResponse(main_xml, media_type="application/xml", filename=main_xml.name)

    @application.get("/api/jobs/{job_id}/dataset/{relative_path:path}")
    async def download_dataset_file(job_id: str, relative_path: str) -> FileResponse:
        paths = services.workspaces.get_job(job_id)
        target = services.workspaces.resolve_dataset_file(paths, relative_path)
        return FileResponse(target, filename=target.name)

    @application.get("/api/jobs/{job_id}/outputs/{filename}")
    async def download_output(job_id: str, filename: str) -> FileResponse:
        paths = services.workspaces.get_job(job_id)
        target = services.workspaces.resolve_output_file(paths, filename)
        return FileResponse(
            target,
            media_type="application/octet-stream",
            filename=target.name,
        )

    @application.get("/api/jobs/{job_id}/logs/{filename}")
    async def download_log(job_id: str, filename: str) -> FileResponse:
        paths = services.workspaces.get_job(job_id)
        target = services.workspaces.resolve_inside(
            paths.logs, sanitize_filename(filename, fallback="conversion.log")
        )
        if not target.is_file():
            raise JobNotFoundError("Log file not found")
        return FileResponse(target, media_type="text/plain", filename=target.name)

    return application


app = create_app()
