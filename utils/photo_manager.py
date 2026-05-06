"""
photo_manager.py
Guarda fotos de jugadores y genera versión sin fondo con rembg.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ASSETS_DIR = BASE_DIR / "assets"
PLAYERS_PHOTOS_DIR = ASSETS_DIR / "players"


class RemBgNoDisponibleError(RuntimeError):
    pass


def _asegurar_dirs():
    PLAYERS_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


def slugify(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    return texto.strip("-") or "jugador"


def extension_desde_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp"} else ".png"


def guardar_foto_original(nombre_jugador: str, filename: str, image_bytes: bytes) -> Path:
    _asegurar_dirs()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    ext = extension_desde_filename(filename)
    slug = slugify(nombre_jugador)
    out_path = PLAYERS_PHOTOS_DIR / f"{slug}_{stamp}_original{ext}"
    out_path.write_bytes(image_bytes)
    return out_path


def quitar_fondo_rembg(ruta_entrada: str | Path) -> Path:
    try:
        from rembg import remove
    except Exception as exc:
        raise RemBgNoDisponibleError(
            "No fue posible importar rembg. Instala 'rembg' y 'onnxruntime'."
        ) from exc

    _asegurar_dirs()
    ruta_entrada = Path(ruta_entrada)
    base = ruta_entrada.stem.replace("_original", "")
    ruta_salida = ruta_entrada.with_name(f"{base}_nobg.png")

    input_bytes = ruta_entrada.read_bytes()
    output_bytes = remove(input_bytes)
    ruta_salida.write_bytes(output_bytes)
    return ruta_salida


def ruta_relativa_a_base(ruta: str | Path) -> str:
    ruta = Path(ruta)
    try:
        return str(ruta.relative_to(BASE_DIR))
    except ValueError:
        return str(ruta)


def resolver_ruta(ruta: str) -> Path:
    p = Path(ruta)
    return p if p.is_absolute() else (BASE_DIR / p)
