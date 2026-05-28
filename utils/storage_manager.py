"""
storage_manager.py
Subida y descarga de archivos en Supabase Storage sin dependencias externas.
"""
from __future__ import annotations

import os
import mimetypes
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "liga-assets").strip() or "liga-assets"


def storage_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_STORAGE_BUCKET)


def is_http_url(value: str | None) -> bool:
    if not value:
        return False
    v = value.strip().lower()
    return v.startswith("http://") or v.startswith("https://")


def _content_type_from_name(file_name: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or fallback


def upload_bytes_to_storage(
    object_path: str,
    file_bytes: bytes,
    content_type: str | None = None,
) -> str:
    """Sube bytes a Supabase Storage y retorna URL publica.

    Lanza RuntimeError si no se pudo subir.
    """
    if not storage_enabled():
        raise RuntimeError("Supabase Storage no esta configurado")

    clean_path = object_path.strip().lstrip("/")
    if not clean_path:
        raise RuntimeError("Ruta de objeto invalida para Storage")

    if not content_type:
        content_type = _content_type_from_name(clean_path)

    encoded_path = quote(clean_path, safe="/-_.")
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{encoded_path}"

    request = Request(
        upload_url,
        data=file_bytes,
        method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Content-Type": content_type,
            "x-upsert": "true",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Storage upload fallo con status {response.status}")
    except Exception as exc:
        raise RuntimeError(f"No se pudo subir archivo a Supabase Storage: {exc}") from exc

    return public_url_for_path(clean_path)


def public_url_for_path(object_path: str) -> str:
    clean_path = object_path.strip().lstrip("/")
    encoded_path = quote(clean_path, safe="/-_.")
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{encoded_path}"


def download_url_bytes(url: str) -> bytes:
    request = Request(url, method="GET")
    with urlopen(request, timeout=30) as response:
        return response.read()


def build_storage_object_path(*parts: str, file_name: str) -> str:
    """Construye una ruta segura para objeto en Storage."""
    safe_parts = [p.strip().strip("/") for p in parts if p and p.strip().strip("/")]
    safe_name = Path(file_name).name.replace("\\", "_").replace("/", "_")
    safe_parts.append(safe_name)
    return "/".join(safe_parts)
