"""
app.py  -  Liga APJ
App de gestión de liga de pádel americano.
Ejecutar: streamlit run app.py
"""
import tempfile
import os
import io
import time
import uuid
from urllib.parse import urlencode
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image as _PILImage
from PIL import ImageDraw as _PILDraw
from PIL import ImageFont as _PILFont

@st.cache_data(show_spinner=False)
def _img_preview_bytes(path_str: str, mtime_ns: int = 0, max_px: int = 1400) -> bytes:
    """Genera una versión reducida para imágenes gigantes solo cuando hace falta."""
    limite_original = _PILImage.MAX_IMAGE_PIXELS
    try:
        _PILImage.MAX_IMAGE_PIXELS = None
        with _PILImage.open(path_str) as img:
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.thumbnail((max_px, max_px), _PILImage.LANCZOS)
            buff = io.BytesIO()
            if img.mode == "RGBA":
                img.save(buff, format="PNG", optimize=True)
            else:
                img.save(buff, format="JPEG", quality=85, optimize=True)
            return buff.getvalue()
    finally:
        _PILImage.MAX_IMAGE_PIXELS = limite_original


@st.cache_data(show_spinner=False)
def _img_raw_bytes(path_str: str, mtime_ns: int = 0) -> bytes:
    # mtime_ns se incluye para invalidar caché cuando el archivo se reemplaza
    return Path(path_str).read_bytes()


def _mostrar_imagen(path: Path, **kwargs):
    """Muestra imagen rápida; si PIL detecta bomba de descompresión, usa preview seguro."""
    try:
        mtime_ns = path.stat().st_mtime_ns
        st.image(_img_raw_bytes(str(path), mtime_ns), **kwargs)
    except Exception as exc:
        if "DecompressionBombError" not in str(exc):
            raise
        mtime_ns = path.stat().st_mtime_ns
        st.image(_img_preview_bytes(str(path), mtime_ns), **kwargs)


def _mostrar_imagen_ref(path_or_url: str, **kwargs) -> bool:
    """Muestra una imagen desde URL o ruta local. Retorna True si se pudo mostrar."""
    if not path_or_url:
        return False
    ref = str(path_or_url).strip()
    if not ref:
        return False

    if is_http_url(ref):
        st.image(ref, **kwargs)
        return True

    ruta = resolver_ruta(ref)
    if ruta.exists():
        _mostrar_imagen(ruta, **kwargs)
        return True
    return False


def _guardar_upload_persistente(uploaded_file, *, folder: str, fallback_dir: Path) -> str:
    """Guarda archivo en Supabase Storage si esta configurado; fallback a disco local."""
    if not uploaded_file:
        return ""

    ext = extension_desde_filename(uploaded_file.name)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    token = uuid.uuid4().hex[:8]
    stem = slugify(Path(uploaded_file.name).stem)
    out_name = f"{stem}_{stamp}_{token}{ext}"
    payload = uploaded_file.getvalue()

    if storage_enabled():
        object_path = build_storage_object_path(folder, file_name=out_name)
        try:
            return upload_bytes_to_storage(
                object_path,
                payload,
                uploaded_file.type or None,
            )
        except Exception as exc:
            st.warning(f"No se pudo subir a Storage, se guarda local: {exc}")

    fallback_dir.mkdir(parents=True, exist_ok=True)
    out_path = fallback_dir / out_name
    out_path.write_bytes(payload)
    return ruta_relativa_a_base(out_path)


def _migrar_ref_local_a_storage(path_ref: str, *, object_path: str) -> str:
    """Convierte una referencia local a URL publica de Storage si es posible."""
    if not path_ref:
        return ""
    if is_http_url(path_ref):
        return path_ref
    if not storage_enabled():
        return path_ref

    ruta_local = resolver_ruta(path_ref)
    if not ruta_local.exists() or not ruta_local.is_file():
        return path_ref

    try:
        content = ruta_local.read_bytes()
        return upload_bytes_to_storage(object_path, content, None)
    except Exception:
        return path_ref


@st.cache_data(show_spinner=False)
def _logo_tile_bytes(path_str: str, canvas_w: int = 380, canvas_h: int = 130, padding: int = 14) -> bytes:
    """Normaliza logos a un lienzo blanco uniforme manteniendo proporción."""
    limite_original = _PILImage.MAX_IMAGE_PIXELS
    try:
        _PILImage.MAX_IMAGE_PIXELS = None
        with _PILImage.open(path_str) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            max_w = max(1, canvas_w - (padding * 2))
            max_h = max(1, canvas_h - (padding * 2))
            img.thumbnail((max_w, max_h), _PILImage.LANCZOS)

            tile = _PILImage.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
            x = (canvas_w - img.width) // 2
            y = (canvas_h - img.height) // 2
            tile.paste(img, (x, y), img)

            buff = io.BytesIO()
            tile.save(buff, format="PNG", optimize=True)
            return buff.getvalue()
    finally:
        _PILImage.MAX_IMAGE_PIXELS = limite_original


@st.cache_data(show_spinner=False)
def _sponsor_strip_bytes(path_list: tuple[str | None, ...], cell_w: int = 320, cell_h: int = 210, padding: int = 2) -> bytes:
    """Crea una tira única de logos (sin espacios entre celdas) sobre fondo blanco."""
    limite_original = _PILImage.MAX_IMAGE_PIXELS
    try:
        _PILImage.MAX_IMAGE_PIXELS = None
        total_w = max(1, cell_w * max(1, len(path_list)))
        strip = _PILImage.new("RGBA", (total_w, cell_h), (255, 255, 255, 255))

        for idx, path_str in enumerate(path_list):
            if not path_str:
                continue
            p = Path(path_str)
            if not p.exists():
                continue
            with _PILImage.open(path_str) as img:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                max_w = max(1, cell_w - (padding * 2))
                max_h = max(1, cell_h - (padding * 2))
                img.thumbnail((max_w, max_h), _PILImage.LANCZOS)

                x0 = idx * cell_w
                x = x0 + ((cell_w - img.width) // 2)
                y = (cell_h - img.height) // 2
                strip.paste(img, (x, y), img)

        buff = io.BytesIO()
        strip.save(buff, format="PNG", optimize=True)
        return buff.getvalue()
    finally:
        _PILImage.MAX_IMAGE_PIXELS = limite_original


@st.cache_data(show_spinner=False)
def _top_header_strip_bytes(
    left_path: str | None,
    right_path: str | None,
    center_text: str,
    cell_w: int = 350,
    cell_h: int = 66,
    padding: int = 6,
) -> bytes:
    """Tira superior con 3 celdas: logo izq, nombre torneo centrado, logo der."""
    limite_original = _PILImage.MAX_IMAGE_PIXELS
    try:
        _PILImage.MAX_IMAGE_PIXELS = None
        strip = _PILImage.new("RGBA", (cell_w * 3, cell_h), (255, 255, 255, 255))

        def _paste_logo(path_str: str | None, col_idx: int, top_offset: int = 0, max_h_scale: float = 1.0):
            if not path_str:
                return
            p = Path(path_str)
            if not p.exists():
                return
            with _PILImage.open(path_str) as img:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                max_w = max(1, cell_w - (padding * 2))
                max_h = max(1, int((cell_h - (padding * 2)) * max_h_scale))
                img.thumbnail((max_w, max_h), _PILImage.LANCZOS)
                x0 = col_idx * cell_w
                x = x0 + ((cell_w - img.width) // 2)
                y = top_offset + ((max_h - img.height) // 2)
                y = max(0, y)
                strip.paste(img, (x, y), img)

        _paste_logo(left_path, 0)
        _paste_logo(right_path, 2)

        draw = _PILDraw.Draw(strip)
        text = (center_text or "").strip().upper()
        font = _PILFont.load_default()

        max_text_w = cell_w - 16
        text_x0 = cell_w
        text_y_top = 0
        text_h_available = max(1, cell_h - text_y_top)

        # Intento de tipografias mas deportivas/tecnologicas; fallback a Arial/default.
        font_candidates = [
            "bahnschrift.ttf",
            "Bahnschrift.ttf",
            "segoeuib.ttf",
            "arialbd.ttf",
            "arial.ttf",
        ]
        for size in [30, 28, 26, 24, 22, 20, 18, 16, 14]:
            try:
                f = None
                for fam in font_candidates:
                    try:
                        f = _PILFont.truetype(fam, size=size)
                        break
                    except Exception:
                        continue
                if f is None:
                    f = font
            except Exception:
                f = font

            # Espaciado de letras para look mas "tech".
            letter_space = max(1, size // 14)
            tw = 0
            for ch in text:
                cb = draw.textbbox((0, 0), ch, font=f)
                tw += (cb[2] - cb[0]) + letter_space
            tw = max(0, tw - letter_space)
            bbox = draw.textbbox((0, 0), "Ag", font=f)
            th = bbox[3] - bbox[1]
            if tw <= max_text_w and th <= text_h_available:
                font = f
                break

        letter_space = max(1, getattr(font, "size", 16) // 14)
        tw = 0
        for ch in text:
            cb = draw.textbbox((0, 0), ch, font=font)
            tw += (cb[2] - cb[0]) + letter_space
        tw = max(0, tw - letter_space)
        bbox = draw.textbbox((0, 0), "Ag", font=font)
        th = bbox[3] - bbox[1]

        tx = text_x0 + ((cell_w - tw) // 2)
        ty = text_y_top + max(0, (text_h_available - th) // 2)

        # Dibujo caracter por caracter para aplicar tracking y un leve borde/sombra.
        x_cur = tx
        for ch in text:
            cb = draw.textbbox((0, 0), ch, font=font)
            cw = cb[2] - cb[0]
            draw.text((x_cur + 1, ty + 1), ch, fill=(120, 120, 120, 255), font=font)
            draw.text((x_cur, ty), ch, fill=(18, 18, 18, 255), font=font)
            x_cur += cw + letter_space

        buff = io.BytesIO()
        strip.save(buff, format="PNG", optimize=True)
        return buff.getvalue()
    finally:
        _PILImage.MAX_IMAGE_PIXELS = limite_original


from utils.database import (
    USE_POSTGRES,
    init_db,
    crear_torneo, listar_torneos, obtener_torneo, actualizar_torneo, eliminar_torneo,
    crear_horarios, listar_horarios,
    crear_jugador, listar_jugadores, actualizar_jugador, eliminar_jugador,
    listar_jornadas, marcar_jornada_completada, eliminar_jornada,
    actualizar_horario_cancha, actualizar_cancha_fisica_cancha_jornada,
    obtener_canchas_jornada, guardar_asignaciones_jornada,
    guardar_resultado, guardar_ausencias_jornada, obtener_ausencias_jornada,
    guardar_asistencia_jornada, obtener_asistencia_jornada,
    calcular_ranking,
)
from utils.liga_engine import (
    calcular_puntos_cancha,
    generar_canchas,
    generar_canchas_por_movimiento,
    guardar_jornada_en_db,
)
from utils.photo_manager import (
    RemBgNoDisponibleError,
    extension_desde_filename,
    quitar_fondo_rembg,
    resolver_ruta,
    ruta_relativa_a_base,
    slugify,
)
from utils.storage_manager import (
    build_storage_object_path,
    download_url_bytes,
    is_http_url,
    storage_enabled,
    upload_bytes_to_storage,
)
from utils.pdf_generator import (
    generar_pdf_jornada,
    generar_pdf_ranking,
    generar_pdf_planilla_jornada,
)

BASE_DIR = Path(__file__).parent

# Inicializar DB al arrancar
init_db()

# ─────────────────────────────────────────────
# Configuración de página
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Liga APJ",
    page_icon="🏓",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not USE_POSTGRES:
    st.warning(
        "DATABASE_URL no esta configurada. Se usa SQLite local y datos/imagenes pueden perderse al reiniciar el hosting.",
        icon="⚠️",
    )

st.markdown("""
<style>
.metric-card {
    background: linear-gradient(135deg, #1e50a0 0%, #2e70d0 100%);
    border-radius: 12px; padding: 16px 20px; color: white; margin-bottom: 8px;
}
.metric-card .pos  { font-size: 1.4em; font-weight: bold; }
.metric-card .nombre { font-size: 1.0em; margin: 4px 0; }
.metric-card .pts  { font-size: 1.3em; font-weight: bold; color: #90d4ff; }
.cancha-header {
    background: #1e50a0; color: white; padding: 8px 16px;
    border-radius: 8px 8px 0 0; font-weight: bold; font-size: 1.1em;
}
</style>
""", unsafe_allow_html=True)


def _parse_tv_short_token(token: str) -> tuple[int | None, int | None]:
    raw = str(token or "").strip()
    if not raw:
        return None, None
    parts = raw.split("-", 1)
    if len(parts) != 2:
        return None, None
    try:
        tid = int(parts[0])
        jid = int(parts[1])
        if tid <= 0 or jid <= 0:
            return None, None
        return tid, jid
    except (TypeError, ValueError):
        return None, None

# ─────────────────────────────────────────────
# Estado de sesión
# ─────────────────────────────────────────────
if "torneo_id" not in st.session_state:
    st.session_state.torneo_id = None
    # Si la URL trae torneo_id (ej: link TV compartido), lo auto-seleccionamos
    _qp_tid = st.query_params.get("torneo_id")
    _tv_short_tid, _tv_short_jid = _parse_tv_short_token(st.query_params.get("tv"))
    if _qp_tid:
        try:
            st.session_state.torneo_id = int(str(_qp_tid))
        except (ValueError, TypeError):
            pass
    elif _tv_short_tid:
        st.session_state.torneo_id = _tv_short_tid
# _torneo_cache guarda el dict del torneo activo para evitar hit a DB en cada rerún
if "_torneo_cache" not in st.session_state:
    st.session_state._torneo_cache = None


def torneo_activo() -> dict | None:
    tid = st.session_state.torneo_id
    if not tid:
        st.session_state._torneo_cache = None
        return None
    cached = st.session_state._torneo_cache
    if cached and cached.get("id") == tid:
        return cached
    t = obtener_torneo(tid)
    st.session_state._torneo_cache = t
    return t


def invalidar_cache_torneo():
    """Llamar después de actualizar datos del torneo."""
    st.session_state._torneo_cache = None


# ─────────────────────────────────────────────
# Utilidades UI
# ─────────────────────────────────────────────
MEDALLAS = ["🥇", "🥈", "🥉", "4°"]


def pts_str(n) -> str:
    try:
        n = int(n)
        return f"+{n}" if n > 0 else str(n)
    except (TypeError, ValueError):
        return str(n)


def color_pts(n) -> str:
    try:
        n = int(n)
        return "green" if n > 0 else ("red" if n < 0 else "gray")
    except Exception:
        return "gray"


def cancha_virtual_label(numero: int) -> str:
    """Convierte 1->A, 2->B, ..., 26->Z, 27->AA, etc."""
    try:
        n = int(numero)
    except (TypeError, ValueError):
        return str(numero)
    if n <= 0:
        return str(numero)

    letras = ""
    while n > 0:
        n -= 1
        letras = chr(ord("A") + (n % 26)) + letras
        n //= 26
    return letras


def mostrar_foto(foto_sin_fondo: str, foto_original: str, size: int = 60):
    for ruta_rel in [foto_sin_fondo, foto_original]:
        if ruta_rel and _mostrar_imagen_ref(ruta_rel, width=size):
            return
    st.markdown(
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:#1e50a0;display:flex;align-items:center;justify-content:center;'
        f'color:white;font-size:{size//3}px;">👤</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
torneo = torneo_activo()

with st.sidebar:
    if torneo:
        logo_left = torneo.get("logo_left_path") or torneo.get("logo_path", "")
        pighead_sidebar_right = BASE_DIR / "assets" / "pighead_white.png"
        if logo_left or pighead_sidebar_right.exists():
            col_logo_1, col_logo_2 = st.columns(2)
            if logo_left:
                with col_logo_1:
                    _mostrar_imagen_ref(logo_left, width=90)
            if pighead_sidebar_right.exists():
                with col_logo_2:
                    _mostrar_imagen(pighead_sidebar_right, width=90)

    st.title("🏓 Liga APJ")
    st.caption("Powered by Pighead")

    if torneo:
        st.success(f"**{torneo['nombre']}**")
        st.caption(f"Temporada {torneo['temporada']}")
        if st.button("Cambiar torneo", use_container_width=True):
            st.session_state.torneo_id = None
            st.rerun()
    else:
        st.warning("Sin torneo seleccionado")

    st.divider()

    PAGINAS = [
        "🏠  Inicio",
        "🏆  Mi Liga",
        "👥  Jugadores",
        "📅  Jornadas",
        "🏓  Resultados",
        "📊  Ranking",
        "📄  Exportar PDF",
        "📺  Pantalla TV",
        "⚙️  Configuración",
    ]
    query_view = str(st.query_params.get("view", "")).strip().lower()
    if not query_view and st.query_params.get("tv"):
        query_view = "tv"
    pagina_default = "📺  Pantalla TV" if query_view == "tv" else "🏠  Inicio"
    pagina = st.radio("Navegación", PAGINAS, index=PAGINAS.index(pagina_default), label_visibility="collapsed")

    if torneo:
        jornadas_sidebar = listar_jornadas(torneo["id"])
        st.session_state["_jornadas_sidebar"] = jornadas_sidebar
        completadas_sidebar = sum(1 for j in jornadas_sidebar if j["completada"])
        st.divider()
        c1, c2 = st.columns(2)
        c1.metric("Jornadas", len(jornadas_sidebar))
        c2.metric("Completas", completadas_sidebar)


# ═══════════════════════════════════════════════════════════════
# PÁGINA: INICIO
# ═══════════════════════════════════════════════════════════════
if pagina == "🏠  Inicio":
    if not torneo:
        st.title("🏓 Bienvenido a Liga APJ")
        st.info("Selecciona o crea un torneo desde **🏆 Mi Liga** para comenzar.")
        st.stop()

    st.title(f"🏓 {torneo['nombre']}")
    st.markdown(f"### Temporada {torneo['temporada']} — Dashboard")
    st.divider()

    ranking   = calcular_ranking(torneo["id"])
    jornadas  = jornadas_sidebar  # ya obtenido en sidebar, evita doble llamada a DB
    jugadores = listar_jugadores(torneo["id"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Jugadores", len(jugadores))
    m2.metric("Jornadas", len(jornadas))
    m3.metric("Líder", ranking[0]["nombre"].split()[0] if ranking else "—")

    st.divider()
    col_rank, col_jornd = st.columns([1, 1], gap="large")

    with col_rank:
        st.subheader("🏆 Top 5")
        if not ranking:
            st.info("Sin datos todavía.")
        else:
            for r in ranking[:5]:
                med = MEDALLAS[r["posicion"] - 1] if r["posicion"] <= 4 else f"{r['posicion']}°"
                cf, ct = st.columns([1, 5])
                with cf:
                    mostrar_foto(r.get("foto_sin_fondo", ""), r.get("foto_original", ""), size=48)
                with ct:
                    st.markdown(
                        f"""<div class="metric-card" style="padding:10px 14px">
                        <span class="pos">{med}</span>
                        <div class="nombre">{r['nombre']}</div>
                        <span class="pts">{pts_str(r['total_pts'])} pts</span>
                        </div>""",
                        unsafe_allow_html=True,
                    )

    with col_jornd:
        completadas = [j for j in jornadas if j["completada"]]
        st.subheader("📋 Última Jornada")
        if not completadas:
            st.info("Ninguna jornada completada todavía.")
        else:
            ultima = completadas[-1]
            canchas = obtener_canchas_jornada(ultima["id"])
            st.markdown(f"**Jornada {ultima['numero']}**  —  Líderes por cancha")
            for c in canchas:
                if c["resultado"] and c["jugadores"]:
                    r = c["resultado"]
                    pts = calcular_puntos_cancha(
                        r["set1_a"], r["set1_b"],
                        r["set2_a"], r["set2_b"],
                        r["set3_a"], r["set3_b"],
                    )
                    lider_idx = pts.index(max(pts))
                    lider = c["jugadores"][lider_idx] if lider_idx < len(c["jugadores"]) else c["jugadores"][0]
                    p_lider = pts[lider_idx]
                    cc, cn, cp = st.columns([1, 4, 2])
                    cc.markdown(f"**Cancha {cancha_virtual_label(c['numero_cancha'])}**")
                    cn.write(lider["nombre"])
                    cp.markdown(f":{color_pts(p_lider)}[**{pts_str(p_lider)}**]")

    st.divider()
    st.subheader("📊 Clasificación General")
    if ranking:
        nums_j_inicio = sorted({n for r in ranking for n in r["pts_por_jornada"].keys()} |
                               {n for r in ranking for n in r["pen_por_jornada"].keys()})
        df_data = []
        for r in ranking:
            med = MEDALLAS[r["posicion"] - 1] if r["posicion"] <= 4 else ""
            fila = {
                "Pos": f"{med} {r['posicion']}°".strip(),
                "Jugador": r["nombre"],
            }
            for n in nums_j_inicio:
                if n in r["pts_por_jornada"]:
                    fila[f"J{n}"] = pts_str(r["pts_por_jornada"][n])
                elif n in r["pen_por_jornada"]:
                    fila[f"J{n}"] = f"✗ {r['pen_por_jornada'][n]}"
                else:
                    fila[f"J{n}"] = "—"
            fila["Pen"] = pts_str(r["total_pen"]) if r["total_pen"] else "0"
            fila["Total"] = pts_str(r["total_pts"])
            df_data.append(fila)
        st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# PÁGINA: MI LIGA
# ═══════════════════════════════════════════════════════════════
elif pagina == "🏆  Mi Liga":
    st.title("🏆 Mi Liga")
    st.divider()

    tab_sel, tab_nuevo = st.tabs(["Seleccionar torneo", "Crear nuevo torneo"])

    with tab_sel:
        torneos = listar_torneos()
        if not torneos:
            st.info("No hay torneos. Crea uno en **Crear nuevo torneo**.")
        else:
            for t in torneos:
                jj = listar_jornadas(t["id"])
                pj = listar_jugadores(t["id"])
                c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                c1.markdown(f"**{t['nombre']}**  ·  Temporada {t['temporada']}")
                c2.caption(f"{len(pj)} jugadores")
                c3.caption(f"{len(jj)} jornadas")
                if c4.button("Seleccionar", key=f"sel_{t['id']}", use_container_width=True):
                    st.session_state.torneo_id = t["id"]
                    st.rerun()
                st.divider()

    with tab_nuevo:
        st.markdown("### Nuevo torneo")
        with st.form("form_nuevo_torneo", clear_on_submit=True):
            nombre      = st.text_input("Nombre de la liga *", placeholder="Liga APJ Primavera")
            temporada   = st.text_input("Temporada *", placeholder="2026")
            num_canchas = st.number_input("Número de canchas", min_value=1, max_value=20, value=5)

            st.markdown("**Horarios de juego**")
            st.caption("Un horario por línea. Si hay más canchas que horarios, se repite el último.")
            horarios_txt = st.text_area(
                "Horarios",
                value="18:00 HS\n19:30 HS",
                height=100,
            )

            st.markdown("**Logos (opcionales)**")
            logo_left_file = st.file_uploader("Logo izquierdo", type=["png", "jpg", "jpeg"], key="nuevo_logo_left")
            logo_right_file = st.file_uploader("Logo derecho (solo PDF)", type=["png", "jpg", "jpeg"], key="nuevo_logo_right")

            submitted = st.form_submit_button("✅ Crear torneo", type="primary")
            if submitted:
                if not nombre or not temporada:
                    st.error("Nombre y temporada son obligatorios.")
                else:
                    assets_dir = BASE_DIR / "assets"
                    assets_dir.mkdir(exist_ok=True)

                    logo_left_path = _guardar_upload_persistente(
                        logo_left_file,
                        folder=f"torneos/{slugify(nombre)}/logos",
                        fallback_dir=assets_dir,
                    ) if logo_left_file else ""

                    logo_right_path = _guardar_upload_persistente(
                        logo_right_file,
                        folder=f"torneos/{slugify(nombre)}/logos",
                        fallback_dir=assets_dir,
                    ) if logo_right_file else ""

                    tid = crear_torneo(
                        nombre,
                        temporada,
                        int(num_canchas),
                        logo_path=logo_left_path,
                        logo_left_path=logo_left_path,
                        logo_right_path=logo_right_path,
                    )
                    horarios = [h for h in horarios_txt.splitlines() if h.strip()]
                    crear_horarios(tid, horarios)

                    st.session_state.torneo_id = tid
                    st.success(f"✅ Torneo **{nombre}** creado.")
                    st.rerun()


# ═══════════════════════════════════════════════════════════════
# Páginas que requieren torneo activo
# ═══════════════════════════════════════════════════════════════
if pagina not in ("🏠  Inicio", "🏆  Mi Liga") and not torneo:
    st.warning("⚠️ Selecciona un torneo desde **🏆 Mi Liga** primero.")
    st.stop()


# ═══════════════════════════════════════════════════════════════
# PÁGINA: JUGADORES
# ═══════════════════════════════════════════════════════════════
if pagina == "👥  Jugadores":
    st.title("👥 Jugadores")
    st.divider()

    tid = torneo["id"]
    tab_lista, tab_nuevo, tab_foto = st.tabs(["Lista", "Agregar jugadores", "Fotos de perfil"])

    with tab_lista:
        jugadores = sorted(listar_jugadores(tid), key=lambda j: j["nombre"])
        if not jugadores:
            st.info("No hay jugadores. Usa **Agregar jugadores**.")
        else:
            busqueda = st.text_input("🔍 Buscar jugador", placeholder="Escribi un nombre...", label_visibility="collapsed", key="busq_jugador")
            filtrados = [j for j in jugadores if busqueda.lower() in j["nombre"].lower()] if busqueda else jugadores
            st.markdown(f"**{len(filtrados)} jugadores**")
            for j in filtrados:
                c_foto, c_nom, c_estado, c_edit, c_del = st.columns([1, 4, 2, 1, 1])
                with c_foto:
                    mostrar_foto(j["foto_sin_fondo"], j["foto_original"], size=42)
                c_nom.markdown(f"**{j['nombre']}**")
                activo = bool(j["activo"])
                nuevo_estado = c_estado.checkbox("Activo", value=activo, key=f"activo_{j['id']}")
                if nuevo_estado != activo:
                    actualizar_jugador(j["id"], activo=1 if nuevo_estado else 0)
                    st.rerun()
                if c_edit.button("✏️", key=f"edit_j_{j['id']}", help="Editar nombre"):
                    st.session_state[f"editando_{j['id']}"] = True
                if c_del.button("🗑️", key=f"del_j_{j['id']}", help="Eliminar"):
                    eliminar_jugador(j["id"])
                    st.rerun()
                if st.session_state.get(f"editando_{j['id']}"):
                    with st.form(key=f"form_edit_{j['id']}"):
                        nuevo_nombre = st.text_input("Nuevo nombre", value=j["nombre"], key=f"input_edit_{j['id']}")
                        col_ok, col_cancel = st.columns(2)
                        if col_ok.form_submit_button("💾 Guardar", type="primary"):
                            nuevo_nombre = nuevo_nombre.strip().upper()
                            if nuevo_nombre and nuevo_nombre != j["nombre"]:
                                actualizar_jugador(j["id"], nombre=nuevo_nombre)
                            st.session_state.pop(f"editando_{j['id']}", None)
                            st.rerun()
                        if col_cancel.form_submit_button("Cancelar"):
                            st.session_state.pop(f"editando_{j['id']}", None)
                            st.rerun()
                st.divider()

    with tab_nuevo:
        st.markdown("### Agregar jugadores")
        st.caption("Puedes agregar varios a la vez, un nombre por línea.")
        with st.form("form_jugadores", clear_on_submit=True):
            nombres_txt = st.text_area(
                "Nombres",
                height=200,
                placeholder="MAURICIO BAUTISTA\nMARIANO GOMEZ\nIKER NORIEGA\n...",
            )
            submitted = st.form_submit_button("➕ Agregar", type="primary")
            if submitted:
                nombres = [n.strip().upper() for n in nombres_txt.splitlines() if n.strip()]
                if not nombres:
                    st.warning("Escribe al menos un nombre.")
                else:
                    existentes = {j["nombre"] for j in listar_jugadores(tid)}
                    nuevos = [n for n in nombres if n not in existentes]
                    duplicados = [n for n in nombres if n in existentes]
                    for n in nuevos:
                        crear_jugador(tid, n)
                    if nuevos:
                        st.success(f"✅ {len(nuevos)} jugador(es) agregado(s).")
                    if duplicados:
                        st.warning(f"Ya existían: {', '.join(duplicados)}")
                    if nuevos:
                        st.rerun()

    with tab_foto:
        st.markdown("### Foto de jugador")
        jugadores = listar_jugadores(tid)
        if not jugadores:
            st.info("Agrega jugadores primero.")
        else:
            nombres_map = {j["nombre"]: j for j in jugadores}
            nombre_sel = st.selectbox("Jugador", list(nombres_map.keys()))
            jug = nombres_map[nombre_sel]

            col_a, col_b = st.columns(2, gap="large")
            with col_a:
                st.markdown("**Foto original**")
                if jug["foto_original"]:
                    if not _mostrar_imagen_ref(jug["foto_original"], use_container_width=True):
                        st.caption("Archivo no encontrado.")
                else:
                    st.info("Sin foto cargada.")

            with col_b:
                st.markdown("**Foto sin fondo**")
                if jug["foto_sin_fondo"]:
                    if not _mostrar_imagen_ref(jug["foto_sin_fondo"], use_container_width=True):
                        st.caption("Archivo no encontrado.")
                else:
                    st.info("Sin versión sin fondo.")

            st.divider()
            foto_file = st.file_uploader("Sube una foto", type=["png", "jpg", "jpeg", "webp"], key="foto_up")
            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("💾 Guardar foto", type="primary", use_container_width=True):
                    if not foto_file:
                        st.warning("Sube una imagen primero.")
                    else:
                        foto_original_ref = _guardar_upload_persistente(
                            foto_file,
                            folder=f"torneos/{tid}/jugadores/{jug['id']}/original",
                            fallback_dir=BASE_DIR / "assets" / "players",
                        )
                        actualizar_jugador(jug["id"], foto_original=foto_original_ref)
                        st.success("Foto guardada.")
                        st.rerun()
            with bc2:
                if st.button("✨ Quitar fondo (rembg)", use_container_width=True):
                    if not jug["foto_original"]:
                        st.warning("Primero guarda la foto original.")
                    else:
                        ruta_abs = None
                        temporal = None
                        try:
                            if is_http_url(jug["foto_original"]):
                                img_bytes = download_url_bytes(jug["foto_original"])
                                suffix = extension_desde_filename(jug["foto_original"])
                                temporal = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                                temporal.write(img_bytes)
                                temporal.flush()
                                ruta_abs = Path(temporal.name)
                            else:
                                ruta_abs = resolver_ruta(jug["foto_original"])

                            if not ruta_abs or not ruta_abs.exists():
                                st.error("Archivo original no encontrado.")
                            else:
                                with st.spinner("Procesando con rembg..."):
                                    ruta_nobg = quitar_fondo_rembg(ruta_abs)

                                foto_nobg_ref = ""
                                if storage_enabled():
                                    with open(ruta_nobg, "rb") as fh:
                                        foto_nobg_ref = upload_bytes_to_storage(
                                            build_storage_object_path(
                                                f"torneos/{tid}/jugadores/{jug['id']}/nobg",
                                                file_name=f"{slugify(nombre_sel)}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png",
                                            ),
                                            fh.read(),
                                            "image/png",
                                        )
                                if not foto_nobg_ref:
                                    foto_nobg_ref = ruta_relativa_a_base(ruta_nobg)

                                actualizar_jugador(jug["id"], foto_sin_fondo=foto_nobg_ref)
                                st.success("¡Fondo eliminado!")
                                st.rerun()
                        except RemBgNoDisponibleError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"Error: {e}")
                        finally:
                            if temporal is not None:
                                try:
                                    Path(temporal.name).unlink(missing_ok=True)
                                except Exception:
                                    pass


# ═══════════════════════════════════════════════════════════════
# PÁGINA: JORNADAS
# ═══════════════════════════════════════════════════════════════
elif pagina == "📅  Jornadas":
    st.title("📅 Jornadas")
    st.divider()

    tid = torneo["id"]
    jornadas = listar_jornadas(tid)
    tab_nueva, tab_ver = st.tabs(["Generar nueva jornada", "Ver jornadas"])

    with tab_nueva:
        st.markdown("### Generar nueva jornada")
        jugadores_todos = listar_jugadores(tid, solo_activos=True)
        if len(jugadores_todos) < 4:
            st.warning("Necesitas al menos 4 jugadores activos registrados.")
        else:
            num_canchas_cfg = torneo["num_canchas"]
            horarios_cfg = [h["nombre"] for h in listar_horarios(tid)]
            fecha_jornada = st.date_input("Fecha de la jornada", value=date.today())
            es_primera_jornada = len(jornadas) == 0

            ultima_j = jornadas[-1] if jornadas else None
            if ultima_j and not ultima_j["completada"]:
                st.warning(
                    f"⚠️ La **Jornada {ultima_j['numero']}** aún no está completada. "
                    "Márcala como completada en la pestaña **Ver jornadas** antes de crear una nueva."
                )
            elif es_primera_jornada:
                st.info("Jornada 1 manual: eliges jugador por cancha y al final el horario de cada cancha.")
                max_canchas_posibles = max(1, min(num_canchas_cfg, len(jugadores_todos) // 4))
                canchas_a_usar = st.number_input(
                    "Canchas a usar en esta jornada",
                    min_value=1,
                    max_value=max_canchas_posibles,
                    value=max_canchas_posibles,
                )

                opciones = [(j["nombre"], j["id"]) for j in jugadores_todos]
                nombre_por_id = {j["id"]: j["nombre"] for j in jugadores_todos}
                seleccionados: list[int] = []
                canchas_gen: list[list[dict]] = []

                for cancha_n in range(1, int(canchas_a_usar) + 1):
                    st.markdown(f"#### Cancha {cancha_virtual_label(cancha_n)}")
                    grupo_ids = []
                    cols = st.columns(4)
                    for pos in range(1, 5):
                        usados = set(seleccionados + grupo_ids)
                        disponibles = [opt for opt in opciones if opt[1] not in usados]
                        if not disponibles:
                            break
                        etiqueta = f"P{pos}"
                        elegido = cols[pos - 1].selectbox(
                            etiqueta,
                            options=[opt[0] for opt in disponibles],
                            key=f"j1_c{cancha_n}_p{pos}",
                        )
                        elegido_id = next(opt[1] for opt in disponibles if opt[0] == elegido)
                        grupo_ids.append(elegido_id)

                    if len(grupo_ids) == 4:
                        seleccionados.extend(grupo_ids)
                        canchas_gen.append(
                            [
                                {"id": gid, "nombre": nombre_por_id[gid]}
                                for gid in grupo_ids
                            ]
                        )

                if canchas_gen:
                    st.markdown("#### Horarios por cancha")
                horarios_jornada: list[str] = []
                for i in range(len(canchas_gen)):
                    if horarios_cfg:
                        default_h = horarios_cfg[i] if i < len(horarios_cfg) else horarios_cfg[-1]
                        h = st.selectbox(
                            f"Horario Cancha {cancha_virtual_label(i+1)}",
                            options=horarios_cfg,
                            index=horarios_cfg.index(default_h),
                            key=f"j1_horario_{i+1}",
                        )
                    else:
                        h = st.text_input(f"Horario Cancha {cancha_virtual_label(i+1)}", key=f"j1_horario_txt_{i+1}")
                    horarios_jornada.append(h)

                if st.button("✅ Crear Jornada 1 manual", type="primary", disabled=(len(canchas_gen) == 0)):
                    guardar_jornada_en_db(tid, canchas_gen, horarios_jornada, fecha=str(fecha_jornada))
                    st.success("✅ Jornada 1 creada manualmente.")
                    st.balloons()
                    st.rerun()
            else:
                st.info("Jornadas siguientes automáticas por movimiento entre canchas.")
                st.caption("Elige si se mueve 1 o 2 jugadores por frontera de canchas.")
                movimiento = st.radio(
                    "Al generar jornada, ¿cuántos se mueven?",
                    options=[1, 2],
                    horizontal=True,
                    format_func=lambda x: (
                        "1 jugador: sube 1 y baja 1"
                        if x == 1
                        else "2 jugadores: suben 2 y bajan 2"
                    ),
                )

                st.caption("Las ausencias y penalizaciones se cargan luego en Resultados.")
                jornada_base = max(jornadas, key=lambda j: j["numero"])
                canchas_base = obtener_canchas_jornada(jornada_base["id"])
                ranking_previo = calcular_ranking(tid)
                try:
                    canchas_gen = generar_canchas_por_movimiento(
                        canchas_base,
                        int(movimiento),
                        ranking_previo=ranking_previo,
                    )
                except ValueError:
                    # Fallback para casos especiales (sin resultados completos, etc.).
                    canchas_gen = generar_canchas(jugadores_todos, num_canchas_cfg, ranking_previo)
                    st.warning(
                        "No se pudo aplicar sube/baja en todas las canchas (faltan resultados o hay canchas incompletas). "
                        "Se generó por ranking general."
                    )

                if canchas_gen:
                    st.markdown("#### Horarios por cancha")
                horarios_jornada: list[str] = []
                for i in range(len(canchas_gen)):
                    if horarios_cfg:
                        default_h = horarios_cfg[i] if i < len(horarios_cfg) else horarios_cfg[-1]
                        h = st.selectbox(
                            f"Horario Cancha {cancha_virtual_label(i+1)}",
                            options=horarios_cfg,
                            index=horarios_cfg.index(default_h),
                            key=f"auto_horario_{i+1}",
                        )
                    else:
                        h = st.text_input(f"Horario Cancha {cancha_virtual_label(i+1)}", key=f"auto_horario_txt_{i+1}")
                    horarios_jornada.append(h)

                if st.button("⚡ Generar jornada automática", type="primary", disabled=(len(canchas_gen) == 0)):
                    guardar_jornada_en_db(tid, canchas_gen, horarios_jornada, fecha=str(fecha_jornada))
                    st.success("✅ Jornada generada exitosamente.")
                    st.balloons()
                    st.rerun()

    with tab_ver:
        if not jornadas:
            st.info("No hay jornadas generadas todavía.")
        else:
            for jornada in reversed(jornadas):
                estado = "✅ Completada" if jornada["completada"] else "🕐 En curso"
                with st.expander(
                    f"Jornada {jornada['numero']}  |  {jornada['fecha']}  |  {estado}",
                    expanded=not jornada["completada"],
                ):
                    canchas = obtener_canchas_jornada(jornada["id"])
                    canchas_fisicas_cfg = [
                        x.strip() for x in str(torneo.get("canchas_fisicas_txt", "")).splitlines() if x.strip()
                    ]
                    asistencia_actual = obtener_asistencia_jornada(jornada["id"])
                    for c in canchas:
                        ctop1, ctop2 = st.columns([2, 1])
                        cancha_fisica_label = f" · {c.get('cancha_fisica', '').strip()}" if c.get("cancha_fisica") else ""
                        _cv_label = cancha_virtual_label(c["numero_cancha"])
                        ctop1.markdown(f"**Cancha {_cv_label}{cancha_fisica_label}**")
                        nuevo_horario = ctop2.text_input(
                            "Horario",
                            value=c["horario"] or "",
                            key=f"edit_horario_{c['id']}",
                            label_visibility="collapsed",
                            placeholder="Horario",
                        )
                        if nuevo_horario != (c["horario"] or ""):
                            try:
                                actualizar_horario_cancha(c["id"], nuevo_horario.strip())
                                st.success(f"Horario actualizado en Cancha {_cv_label}")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

                        if canchas_fisicas_cfg:
                            opciones_fisicas = ["(Sin asignar)"] + canchas_fisicas_cfg
                            actual_fisica = (c.get("cancha_fisica") or "").strip()
                            idx_fisica = opciones_fisicas.index(actual_fisica) if actual_fisica in opciones_fisicas else 0
                            nueva_fisica = ctop2.selectbox(
                                "Cancha física",
                                options=opciones_fisicas,
                                index=idx_fisica,
                                key=f"edit_fisica_{c['id']}",
                                label_visibility="collapsed",
                            )
                            nueva_fisica_val = "" if nueva_fisica == "(Sin asignar)" else nueva_fisica
                            if nueva_fisica_val != actual_fisica:
                                try:
                                    actualizar_cancha_fisica_cancha_jornada(c["id"], nueva_fisica_val)
                                    st.success(f"Cancha física actualizada en Cancha {_cv_label}")
                                    st.rerun()
                                except ValueError as e:
                                    st.error(str(e))

                        nombres_c = [j["nombre"] for j in sorted(c["jugadores"], key=lambda x: x["posicion"])]
                        if c["resultado"]:
                            r = c["resultado"]
                            pts = calcular_puntos_cancha(
                                r["set1_a"], r["set1_b"],
                                r["set2_a"], r["set2_b"],
                                r["set3_a"], r["set3_b"],
                            )
                            resumen_pts = "  ".join(
                                f"{n.split()[0]}: **{pts_str(p)}**"
                                for n, p in zip(nombres_c, pts)
                            )
                            st.markdown(
                                f"**Cancha {cancha_virtual_label(c['numero_cancha'])}** {c['horario']}  ·  "
                                f"{resumen_pts}  ·  "
                                f"_{r['set1_a']}-{r['set1_b']} / {r['set2_a']}-{r['set2_b']} / {r['set3_a']}-{r['set3_b']}_"
                            )
                        else:
                            st.caption(f"Cancha {cancha_virtual_label(c['numero_cancha'])}: sin resultado cargado aún.")

                    st.markdown("#### 🔀 Ajuste manual de canchas")
                    if jornada["completada"]:
                        st.info("Esta jornada está completada. Para evitar inconsistencias en ranking, el orden manual está bloqueado.")
                    else:
                        jugadores_slots = []
                        for c in sorted(canchas, key=lambda x: x["numero_cancha"]):
                            for jg in sorted(c.get("jugadores", []), key=lambda x: x.get("posicion", 99)):
                                jugadores_slots.append(
                                    {
                                        "cancha_jornada_id": int(c["id"]),
                                        "cancha_num": int(c["numero_cancha"]),
                                        "posicion": int(jg.get("posicion", 0) or 0),
                                        "jugador_id": int(jg.get("jugador_id", 0) or 0),
                                    }
                                )

                        if not jugadores_slots:
                            st.caption("No hay jugadores asignados para reordenar.")
                        else:
                            by_id = {
                                int(j["jugador_id"]): j["nombre"]
                                for c in canchas
                                for j in c.get("jugadores", [])
                                if int(j.get("jugador_id", 0) or 0)
                            }
                            option_labels = {
                                jid: f"{nombre}"
                                for jid, nombre in sorted(by_id.items(), key=lambda x: x[1])
                            }
                            labels = [option_labels[jid] for jid in option_labels.keys()]
                            label_to_id = {v: k for k, v in option_labels.items()}

                            st.caption("Elige manualmente quién va en cada cancha/posición y guarda cambios.")
                            col_a, col_b = st.columns(2)
                            for idx, slot in enumerate(jugadores_slots):
                                _col = col_a if idx % 2 == 0 else col_b
                                current_label = option_labels.get(slot["jugador_id"], "")
                                _cv = cancha_virtual_label(slot["cancha_num"])
                                chosen = _col.selectbox(
                                    f"Cancha {_cv} · P{slot['posicion']}",
                                    options=labels,
                                    index=labels.index(current_label) if current_label in labels else 0,
                                    key=f"manual_slot_{jornada['id']}_{slot['cancha_jornada_id']}_{slot['posicion']}",
                                )
                                slot["jugador_id"] = int(label_to_id[chosen])

                            if st.button("💾 Guardar orden manual", key=f"save_manual_order_{jornada['id']}", use_container_width=True):
                                ids_sel = [s["jugador_id"] for s in jugadores_slots]
                                if len(set(ids_sel)) != len(ids_sel):
                                    st.error("Hay jugadores repetidos. Cada jugador solo puede estar una vez.")
                                else:
                                    try:
                                        guardar_asignaciones_jornada(jornada["id"], jugadores_slots)
                                        st.success("Orden manual guardado correctamente.")
                                        st.rerun()
                                    except ValueError as e:
                                        st.error(str(e))

                    st.markdown("#### ✅ Asistencia por horario")
                    grupos_horario: dict[str, list[dict]] = {}
                    for c in canchas:
                        _horario = (c.get("horario") or "Sin horario").strip() or "Sin horario"
                        grupos_horario.setdefault(_horario, [])
                        for _j in sorted(c.get("jugadores", []), key=lambda x: x.get("posicion", 99)):
                            grupos_horario[_horario].append(
                                {
                                    "jugador_id": int(_j.get("jugador_id", 0) or 0),
                                    "nombre": _j.get("nombre", "-"),
                                    "cancha": cancha_virtual_label(c.get("numero_cancha", 0) or 0),
                                    "posicion": int(_j.get("posicion", 0) or 0),
                                }
                            )

                    llegados_sel: set[int] = set()
                    for _horario, _lista in grupos_horario.items():
                        st.markdown(f"**🕒 {_horario}**")
                        cols_asis = st.columns(2)
                        for _idx, _p in enumerate(_lista):
                            _col = cols_asis[_idx % 2]
                            _jid = _p["jugador_id"]
                            _label = f"Cancha {_p['cancha']} · P{_p['posicion']} · {_p['nombre']}"
                            _checked = _col.checkbox(
                                _label,
                                value=(_jid in asistencia_actual),
                                key=f"asis_j{jornada['id']}_u{_jid}",
                            )
                            if _checked and _jid:
                                llegados_sel.add(_jid)

                    if st.button("💾 Guardar asistencia", key=f"save_asis_{jornada['id']}", use_container_width=True):
                        guardar_asistencia_jornada(jornada["id"], llegados_sel)
                        st.success("Asistencia guardada.")
                        st.rerun()

                    col_mark_jornada, col_del_jornada = st.columns([3, 1])
                    if not jornada["completada"]:
                        if col_mark_jornada.button(
                            "✅ Completar jornada",
                            key=f"done_j_{jornada['id']}",
                            use_container_width=True,
                        ):
                            marcar_jornada_completada(jornada["id"])
                            st.success("Jornada marcada como completada.")
                            st.rerun()
                    else:
                        col_mark_jornada.caption("Jornada ya completada")

                    if col_del_jornada.button("🗑️ Eliminar jornada", key=f"del_j_{jornada['id']}", use_container_width=True):
                        eliminar_jornada(jornada["id"])
                        st.rerun()


# ═══════════════════════════════════════════════════════════════
# PÁGINA: RESULTADOS
# ═══════════════════════════════════════════════════════════════
elif pagina == "🏓  Resultados":
    st.title("🏓 Ingreso de Resultados")
    st.divider()

    tid = torneo["id"]
    jornadas = listar_jornadas(tid)
    if not jornadas:
        st.warning("No hay jornadas generadas. Ve a **📅 Jornadas** primero.")
        st.stop()

    opciones = {f"Jornada {j['numero']} — {j['fecha']}": j for j in reversed(jornadas)}
    jornada_sel = opciones[st.selectbox("Jornada", list(opciones.keys()))]
    canchas = obtener_canchas_jornada(jornada_sel["id"])
    jugadores_torneo = listar_jugadores(tid)
    mapa_jugadores = {j["id"]: j for j in jugadores_torneo}
    ausencias_actuales = obtener_ausencias_jornada(jornada_sel["id"])

    st.markdown(f"## Jornada {jornada_sel['numero']}")
    st.caption("Ingresa marcadores y registra penalizaciones individuales como puntos a restar.")

    with st.expander("🚫 Penalizaciones", expanded=bool(ausencias_actuales)):
        st.caption("Agrega solo los jugadores penalizados en esta jornada. Cada valor se resta a los puntos obtenidos.")

        penalizaciones_guardadas = [
            (jid, mapa_jugadores[jid]["nombre"], pen)
            for jid, pen in ausencias_actuales.items()
            if jid in mapa_jugadores
        ]
        penalizaciones_guardadas.sort(key=lambda item: item[1])

        if penalizaciones_guardadas:
            resumen = " | ".join(f"{nombre}: -{abs(int(pen))}" for _, nombre, pen in penalizaciones_guardadas)
            st.info(f"Registrados: {resumen}")

        cantidad_penalizados = st.number_input(
            "Cantidad de jugadores penalizados",
            min_value=0,
            max_value=len(jugadores_torneo),
            value=len(penalizaciones_guardadas),
            step=1,
            key=f"cant_pen_{jornada_sel['id']}",
        )

        defaults = [(jid, pen) for jid, _, pen in penalizaciones_guardadas]
        nuevas_pen: dict[int, int] = {}
        seleccionados: list[int] = []

        if int(cantidad_penalizados) == 0:
            if st.button("💾 Guardar (sin penalizaciones)", use_container_width=True):
                guardar_ausencias_jornada(jornada_sel["id"], {})
                st.success("Penalizaciones borradas.")
                st.rerun()
        else:
            with st.form(f"form_penalizaciones_{jornada_sel['id']}"):
                for idx in range(int(cantidad_penalizados)):
                    jid_default = defaults[idx][0] if idx < len(defaults) else None
                    pen_default = abs(defaults[idx][1]) if idx < len(defaults) else 10

                    disponibles = [
                        j for j in jugadores_torneo
                        if j["id"] == jid_default or j["id"] not in seleccionados
                    ]
                    if not disponibles:
                        break

                    nombres_disponibles = [j["nombre"] for j in disponibles]
                    idx_default = 0
                    if jid_default is not None:
                        for pos, jugador in enumerate(disponibles):
                            if jugador["id"] == jid_default:
                                idx_default = pos
                                break

                    col_jugador, col_pen = st.columns([4, 1.2])
                    nombre_sel = col_jugador.selectbox(
                        f"Jugador penalizado {idx + 1}",
                        options=nombres_disponibles,
                        index=idx_default,
                        key=f"pen_jugador_{jornada_sel['id']}_{idx}",
                    )
                    jugador_sel = next(j for j in disponibles if j["nombre"] == nombre_sel)
                    seleccionados.append(jugador_sel["id"])

                    penalizacion_sel = col_pen.number_input(
                        f"Resta {idx + 1}",
                        min_value=0,
                        max_value=99,
                        value=int(pen_default),
                        step=1,
                        key=f"pen_valor_{jornada_sel['id']}_{idx}",
                    )
                    nuevas_pen[jugador_sel["id"]] = -int(penalizacion_sel)

                if st.form_submit_button("💾 Guardar penalizaciones", use_container_width=True, type="primary"):
                    guardar_ausencias_jornada(jornada_sel["id"], nuevas_pen)
                    if nuevas_pen:
                        nombres_pen = [mapa_jugadores[jid]["nombre"] for jid in nuevas_pen]
                        st.success(f"Penalizaciones guardadas para: {', '.join(nombres_pen)}")
                    else:
                        st.info("Sin penalizaciones registradas para esta jornada.")
                    st.rerun()

    for c in canchas:
        jugadores = c["jugadores"]
        if len(jugadores) < 4:
            continue

        p = [j["nombre"].split()[0] for j in jugadores]
        res = c["resultado"]

        with st.expander(f"🎾 Cancha {cancha_virtual_label(c['numero_cancha'])}  —  {c['horario']}", expanded=(res is None)):
            st.caption(
                f"Set 1: {p[0]}+{p[1]} vs {p[2]}+{p[3]}  |  "
                f"Set 2: {p[0]}+{p[2]} vs {p[1]}+{p[3]}  |  "
                f"Set 3: {p[0]}+{p[3]} vs {p[1]}+{p[2]}"
            )

            defs = {"s1a": 0, "s1b": 0, "s2a": 0, "s2b": 0, "s3a": 0, "s3b": 0}
            if res:
                defs = {
                    "s1a": res["set1_a"], "s1b": res["set1_b"],
                    "s2a": res["set2_a"], "s2b": res["set2_b"],
                    "s3a": res["set3_a"], "s3b": res["set3_b"],
                }

            with st.form(f"form_cancha_{c['id']}"):
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.markdown(f"**Set 1**")
                    s1a = st.number_input(f"{p[0]}+{p[1]}", 0, 99, defs["s1a"], key=f"s1a_{c['id']}")
                    s1b = st.number_input(f"{p[2]}+{p[3]}", 0, 99, defs["s1b"], key=f"s1b_{c['id']}")
                with col_s2:
                    st.markdown(f"**Set 2**")
                    s2a = st.number_input(f"{p[0]}+{p[2]}", 0, 99, defs["s2a"], key=f"s2a_{c['id']}")
                    s2b = st.number_input(f"{p[1]}+{p[3]}", 0, 99, defs["s2b"], key=f"s2b_{c['id']}")
                with col_s3:
                    st.markdown(f"**Set 3**")
                    s3a = st.number_input(f"{p[0]}+{p[3]}", 0, 99, defs["s3a"], key=f"s3a_{c['id']}")
                    s3b = st.number_input(f"{p[1]}+{p[2]}", 0, 99, defs["s3b"], key=f"s3b_{c['id']}")

                if st.form_submit_button("💾 Guardar resultados", type="primary"):
                    guardar_resultado(c["id"], s1a, s1b, s2a, s2b, s3a, s3b)
                    st.success("Guardado.")
                    st.rerun()

            if res:
                pts = calcular_puntos_cancha(
                    res["set1_a"], res["set1_b"],
                    res["set2_a"], res["set2_b"],
                    res["set3_a"], res["set3_b"],
                )
                st.markdown("**Puntos calculados:**")
                pc = st.columns(len(jugadores))
                for idx, (jug, pt) in enumerate(zip(jugadores, pts)):
                    etiqueta = jug["nombre"].split()[0]
                    penalizacion = ausencias_actuales.get(jug["jugador_id"], 0)
                    delta_str = pts_str(int(penalizacion)) if penalizacion else None
                    pc[idx].metric(
                        etiqueta,
                        pts_str(pt),
                        delta=delta_str,
                        delta_color="inverse" if penalizacion < 0 else "normal",
                    )


# ═══════════════════════════════════════════════════════════════
# PÁGINA: RANKING
# ═══════════════════════════════════════════════════════════════
elif pagina == "📊  Ranking":
    st.title("📊 Ranking General")
    st.divider()

    tid = torneo["id"]
    ranking = calcular_ranking(tid, completada_only=False)
    if not ranking:
        st.info("Sin datos de ranking todavía.")
        st.stop()

    jornadas = listar_jornadas(tid)
    ultima = max((j["numero"] for j in jornadas), default="—")
    st.markdown(f"Clasificación en tiempo real hasta **Jornada {ultima}**")

    if len(ranking) >= 3:
        st.markdown("### Podio")
        col1, col2, col3 = st.columns(3)
        podio_order = [ranking[1], ranking[0], ranking[2]]
        icons = ["🥈", "🥇", "🥉"]
        for col, r, icon in zip([col1, col2, col3], podio_order, icons):
            with col:
                mostrar_foto(r.get("foto_sin_fondo", ""), r.get("foto_original", ""), size=80)
                st.markdown(
                    f"""<div class="metric-card" style="text-align:center;margin-top:8px">
                    <div style="font-size:1.8em">{icon}</div>
                    <div class="nombre">{r['nombre']}</div>
                    <div class="pts">{pts_str(r['total_pts'])} pts</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

    st.divider()
    st.markdown("### Tabla Completa")

    # Todas las jornadas completadas (para columnas fijas aunque un jugador no tenga datos)
    nums_jornadas = sorted({n for r in ranking for n in r["pts_por_jornada"].keys()} |
                           {n for r in ranking for n in r["pen_por_jornada"].keys()})

    df_data = []
    for r in ranking:
        med = MEDALLAS[r["posicion"] - 1] if r["posicion"] <= 4 else ""
        fila = {
            "Pos": f"{med} {r['posicion']}°".strip(),
            "Jugador": r["nombre"],
        }
        # Columnas de jornada: puntos si jugó, penalización si faltó, vacío si no aplica
        for n in nums_jornadas:
            if n in r["pts_por_jornada"]:
                fila[f"J{n}"] = pts_str(r["pts_por_jornada"][n])
            elif n in r["pen_por_jornada"]:
                fila[f"J{n}"] = f"✗ {r['pen_por_jornada'][n]}"
            else:
                fila[f"J{n}"] = "—"
        fila["Pen"] = pts_str(r["total_pen"]) if r["total_pen"] else "0"
        fila["Total"] = pts_str(r["total_pts"])
        df_data.append(fila)
    st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# PÁGINA: EXPORTAR PDF
# ═══════════════════════════════════════════════════════════════
elif pagina == "📄  Exportar PDF":
    st.title("📄 Exportar PDF")
    st.caption("PDFs listos para compartir por WhatsApp")
    st.divider()

    tid = torneo["id"]
    tab_jornada, tab_ranking = st.tabs(["📋 Resumen de Jornada", "🏆 Ranking General"])

    with tab_jornada:
        jornadas = listar_jornadas(tid)
        if not jornadas:
            st.info("No hay jornadas para exportar.")
        else:
            opciones = {f"Jornada {j['numero']} — {j['fecha']}": j for j in reversed(jornadas)}
            jornada_sel = opciones[st.selectbox("Jornada a exportar", list(opciones.keys()), key="pdf_j")]
            canchas_raw = obtener_canchas_jornada(jornada_sel["id"])

            if st.button("📝 Generar planilla para cargar resultados", use_container_width=True):
                if not canchas_raw:
                    st.warning("La jornada no tiene canchas cargadas.")
                else:
                    with st.spinner("Generando planilla..."):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp_path = Path(tmp.name)
                        generar_pdf_planilla_jornada(
                            jornada_sel["numero"],
                            canchas_raw,
                            tmp_path,
                            torneo=torneo,
                            fecha_jornada=jornada_sel.get("fecha"),
                        )
                        pdf_bytes = tmp_path.read_bytes()
                        os.unlink(tmp_path)
                    st.success("✅ Planilla generada")
                    st.download_button(
                        "⬇️ Descargar planilla",
                        pdf_bytes,
                        f"{torneo['nombre'].replace(' ','_')}_Planilla_Jornada_{jornada_sel['numero']}.pdf",
                        "application/pdf",
                        use_container_width=True,
                    )

            st.divider()
            st.caption("Si ya cargaste resultados, tambien puedes exportar el resumen final de la jornada.")

            if st.button("🔄 Generar PDF de Jornada", type="primary"):
                canchas_pdf = []
                for c in canchas_raw:
                    if not c["resultado"] or not c["jugadores"]:
                        continue
                    r = c["resultado"]
                    pts_tuple = calcular_puntos_cancha(
                        r["set1_a"], r["set1_b"],
                        r["set2_a"], r["set2_b"],
                        r["set3_a"], r["set3_b"],
                    )
                    jugadores_pdf = []
                    for idx, jug in enumerate(c["jugadores"]):
                        jugadores_pdf.append({
                            "nombre": jug["nombre"],
                            "puntos": pts_tuple[idx] if idx < len(pts_tuple) else 0,
                            "rank_cancha": idx + 1,
                        })
                    jugadores_pdf.sort(key=lambda x: -x["puntos"])
                    for rank, jug in enumerate(jugadores_pdf, 1):
                        jug["rank_cancha"] = rank
                    canchas_pdf.append({
                        "numero": c["numero_cancha"],
                        "jugadores": jugadores_pdf,
                        "sets": [
                            (r["set1_a"], r["set1_b"]),
                            (r["set2_a"], r["set2_b"]),
                            (r["set3_a"], r["set3_b"]),
                        ],
                    })

                if not canchas_pdf:
                    st.warning("Esta jornada no tiene resultados ingresados.")
                else:
                    with st.spinner("Generando PDF..."):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp_path = Path(tmp.name)
                        generar_pdf_jornada(jornada_sel["numero"], canchas_pdf, tmp_path, torneo=torneo)
                        pdf_bytes = tmp_path.read_bytes()
                        os.unlink(tmp_path)
                    st.success("✅ PDF generado")
                    st.download_button(
                        "⬇️ Descargar PDF",
                        pdf_bytes,
                        f"{torneo['nombre'].replace(' ','_')}_Jornada_{jornada_sel['numero']}.pdf",
                        "application/pdf",
                        use_container_width=True,
                    )

    with tab_ranking:
        ranking = calcular_ranking(tid)
        if not ranking:
            st.info("Sin datos de ranking todavía.")
        else:
            jornadas_comp = [j for j in listar_jornadas(tid) if j["completada"]]
            ref = jornadas_comp[-1]["numero"] if jornadas_comp else None
            st.info(f"Se exportará el ranking hasta **Jornada {ref}**")

            tipo_pdf = st.radio(
                "Tipo de PDF",
                ["Detallado (J1, J2, J3…)", "Resumido (solo totales)"],
                horizontal=True,
            )
            detallado_pdf = tipo_pdf.startswith("Detallado")

            if st.button("🔄 Generar PDF de Ranking", type="primary"):
                ranking_pdf = [
                    {
                        "nombre": r["nombre"],
                        "posicion": r["posicion"],
                        "total": r["total_pts"],
                        "jornadas_jugadas": r["jornadas_jugadas"],
                        "pts_por_jornada": r["pts_por_jornada"],
                        "pen_por_jornada": r["pen_por_jornada"],
                        "total_pen": r["total_pen"],
                        "total_juego": r["total_juego"],
                    }
                    for r in ranking
                ]
                with st.spinner("Generando PDF..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp_path = Path(tmp.name)
                    generar_pdf_ranking(ranking_pdf, tmp_path, jornada_ref=ref, detallado=detallado_pdf, torneo=torneo)
                    pdf_bytes = tmp_path.read_bytes()
                    os.unlink(tmp_path)
                st.success("✅ PDF generado")
                st.download_button(
                    "⬇️ Descargar PDF",
                    pdf_bytes,
                    f"{torneo['nombre'].replace(' ','_')}_Ranking_J{ref}.pdf",
                    "application/pdf",
                    use_container_width=True,
                )


# ═══════════════════════════════════════════════════════════════
# PÁGINA: PANTALLA TV
# ═══════════════════════════════════════════════════════════════
elif pagina == "📺  Pantalla TV":
    _tv_short_tid, _tv_short_jid = _parse_tv_short_token(st.query_params.get("tv"))
    tv_mode = str(st.query_params.get("mode", "display" if _tv_short_jid else "operator")).strip().lower()
    tv_readonly = tv_mode in ("display", "readonly", "tv")

    if not torneo:
        st.warning("No hay torneo seleccionado. Abre la app normalmente y selecciona un torneo primero, o comparte el link TV con `torneo_id` en el sufijo.")
        st.stop()

    # ── Modo display: inyectar CSS full-viewport antes de cualquier widget ──
    if tv_readonly:
        st.markdown(
            """
            <style>
            section[data-testid="stSidebar"] {display:none !important;}
            header[data-testid="stHeader"] {display:none !important;}
            #MainMenu {display:none !important;}
            footer {display:none !important;}
            .stApp {overflow:hidden; height:100vh;}
            section[data-testid="stMain"] > div:first-child {height:100vh; overflow:hidden;}
            .block-container {
                padding-top:0 !important;
                padding-bottom:0 !important;
                padding-left:0.6rem !important;
                padding-right:0.6rem !important;
                max-width:100% !important;
                height:100vh;
                overflow:hidden;
                display:flex;
                flex-direction:column;
            }
            /* Eliminar todos los gaps/márgenes verticales entre elementos */
            div[data-testid="stVerticalBlock"] {gap:0 !important;}
            div[data-testid="stVerticalBlock"] > div {
                margin-top:0 !important;
                margin-bottom:0 !important;
                padding-top:0 !important;
                padding-bottom:0 !important;
            }
            div[data-testid="stImage"] {margin:0 !important; padding:0 !important; line-height:0;}
            div[data-testid="stImage"] img {display:block; margin:0 !important; padding:0 !important;}
            [data-testid="stAppViewContainer"] {padding-top:0 !important; margin-top:0 !important;}
            /* columnas del header logo sin padding lateral extra */
            div[data-testid="stHorizontalBlock"]:first-of-type div[data-testid="stColumn"] {
                padding:0 !important;
            }
            div[data-testid="stHorizontalBlock"] {
                gap:0.3rem;
                margin:0 !important;
                padding:0 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                overflow:hidden;
                border:2px solid rgba(18, 18, 18, 0.95) !important;
                border-top:4px solid #e10600 !important;
                border-left:4px solid #e10600 !important;
                border-radius:6px !important;
                background:
                    repeating-linear-gradient(-45deg,
                        rgba(225, 6, 0, 0.05) 0px,
                        rgba(225, 6, 0, 0.05) 8px,
                        rgba(0, 0, 0, 0.02) 8px,
                        rgba(0, 0, 0, 0.02) 16px
                    ),
                    #ffffff !important;
                box-shadow:
                    0 0 0 1px rgba(255, 255, 255, 0.75) inset,
                    0 4px 10px rgba(0, 0, 0, 0.22) !important;
            }
            /* reducir tamaño de fuente en tarjetas */
            div[data-testid="stVerticalBlockBorderWrapper"] h3 {font-size:1.05rem !important; margin:0 !important;}
            div[data-testid="stVerticalBlockBorderWrapper"] p {font-size:1rem !important; margin:0 !important;}
            </style>
            """,
            unsafe_allow_html=True,
        )

    if not tv_readonly:
        st.title("📺 Visualización de Canchas")
        st.caption("Modo TV para mostrar asignaciones por cancha")
        st.divider()

    tid = torneo["id"]
    jornadas = listar_jornadas(tid)
    if not jornadas:
        st.info("No hay jornadas generadas todavía.")
        st.stop()

    opciones = {f"Jornada {j['numero']} — {j['fecha']}": j for j in reversed(jornadas)}
    labels_jornada = list(opciones.keys())
    qp_jornada_id = 0
    try:
        qp_jornada_id = int(str(st.query_params.get("jornada_id", str(_tv_short_jid or 0))))
    except Exception:
        qp_jornada_id = 0
    idx_default_j = 0
    if qp_jornada_id:
        for pos, lbl in enumerate(labels_jornada):
            if int(opciones[lbl]["id"]) == qp_jornada_id:
                idx_default_j = pos
                break
    if tv_readonly:
        jornada_sel = opciones[labels_jornada[idx_default_j]]
    else:
        jornada_sel = opciones[
            st.selectbox("Jornada a mostrar", labels_jornada, index=idx_default_j, key="tv_jornada")
        ]
    canchas = obtener_canchas_jornada(jornada_sel["id"])
    if not canchas:
        st.info("La jornada no tiene canchas cargadas.")
        st.stop()
    asistencia_llegaron = obtener_asistencia_jornada(jornada_sel["id"])

    if st.session_state.get("tv_last_jornada_id") != jornada_sel["id"]:
        st.session_state["tv_last_jornada_id"] = jornada_sel["id"]
        st.session_state["tv_page_idx"] = 0
        st.session_state["tv_last_switch_ts"] = time.time()

    canchas_por_pagina = 10
    paginas = [canchas[i:i + canchas_por_pagina] for i in range(0, len(canchas), canchas_por_pagina)]
    total_paginas = max(1, len(paginas))
    st.session_state["tv_page_idx"] = min(st.session_state.get("tv_page_idx", 0), total_paginas - 1)

    if tv_readonly:
        # Header superior: logo personalizado TV o strip con logos + nombre.
        _tv_header_rel = torneo.get("tv_header_logo_path", "")
        if _tv_header_rel:
            _tv_header_path = resolver_ruta(_tv_header_rel)
            if _tv_header_path.exists():
                _col_l, _col_c, _col_r = st.columns([0.3, 0.4, 0.3])
                _col_c.image(str(_tv_header_path), use_container_width=True)
            else:
                _tv_header_rel = ""
        if not _tv_header_rel:
            _logo_left_rel = torneo.get("logo_left_path") or torneo.get("logo_path", "")
            _logo_right_rel = torneo.get("logo_right_path", "")
            _top_left = resolver_ruta(_logo_left_rel) if _logo_left_rel else None
            _top_right = resolver_ruta(_logo_right_rel) if _logo_right_rel else None
            _top_strip = _top_header_strip_bytes(
                left_path=str(_top_left) if (_top_left and _top_left.exists()) else None,
                right_path=str(_top_right) if (_top_right and _top_right.exists()) else None,
                center_text=str(torneo.get("nombre", "")).strip(),
                cell_w=350,
                cell_h=66,
                padding=6,
            )
            st.image(_top_strip, use_container_width=True)

        st.markdown(
            f"<p style='margin:0;padding:0;font-size:0.8rem;color:#888;'>"
            f"📅 Jornada {jornada_sel['numero']} — {jornada_sel['fecha']} &nbsp;|&nbsp; "
            f"Página <span id='tv_pg_num'></span></p>",
            unsafe_allow_html=True,
        )

    qp_auto = str(st.query_params.get("auto", "0" if _tv_short_jid else "")).strip().lower() in ("1", "true", "yes")
    qp_hide = str(st.query_params.get("hide", "1" if _tv_short_jid else "")).strip().lower() in ("1", "true", "yes")
    try:
        qp_interval = int(str(st.query_params.get("interval", "180")))
    except Exception:
        qp_interval = 180
    if qp_interval not in [5, 8, 10, 12, 15, 20, 30, 60, 120, 180]:
        qp_interval = 180

    if str(st.query_params.get("view", "")).strip().lower() == "tv" or _tv_short_jid:
        st.session_state["tv_auto"] = qp_auto
        st.session_state["tv_interval"] = qp_interval
        st.session_state["tv_hide_sidebar"] = qp_hide
    if tv_readonly:
        auto_tv = qp_auto
        intervalo = qp_interval
        if "auto" not in st.query_params:
            auto_tv = True
        tv_full = True  # siempre ocultar sidebar en modo display
    else:
        cnav1, cnav2, cnav3, cnav4 = st.columns([1, 1, 2, 2])
        if cnav1.button("◀ Anterior", use_container_width=True, disabled=(total_paginas == 1)):
            st.session_state["tv_page_idx"] = (st.session_state["tv_page_idx"] - 1) % total_paginas
            st.session_state["tv_last_switch_ts"] = time.time()
            st.rerun()
        if cnav2.button("Siguiente ▶", use_container_width=True, disabled=(total_paginas == 1)):
            st.session_state["tv_page_idx"] = (st.session_state["tv_page_idx"] + 1) % total_paginas
            st.session_state["tv_last_switch_ts"] = time.time()
            st.rerun()

        auto_tv = cnav3.toggle("Auto carrusel", value=st.session_state.get("tv_auto", False), key="tv_auto")
        _intervalos = [5, 8, 10, 12, 15, 20, 30, 60, 120, 180]
        _intervalo_actual = st.session_state.get("tv_interval", 180)
        if _intervalo_actual not in _intervalos:
            _intervalo_actual = 180
        idx_intervalo = _intervalos.index(_intervalo_actual)
        intervalo = cnav4.selectbox("Intervalo (seg)", options=_intervalos, index=idx_intervalo, key="tv_interval")
        st.caption(f"Página {st.session_state['tv_page_idx'] + 1} de {total_paginas}")

        tv_full = st.toggle("Ocultar sidebar (vista operador)", value=st.session_state.get("tv_hide_sidebar", False), key="tv_hide_sidebar")

        # El link generado siempre oculta sidebar (hide=1) — es para TV
        tv_query = urlencode(
            {
                "view": "tv",
                "mode": "display",
                "torneo_id": int(tid),
                "jornada_id": int(jornada_sel["id"]),
                "auto": 1 if auto_tv else 0,
                "interval": int(intervalo),
                "hide": 1,
            }
        )

        # Construir URL completa usando la URL real del contexto de la sesión
        try:
            _current_url = str(st.context.url)
            _base_url = _current_url.split("?")[0].rstrip("/")
        except Exception:
            _host = st.context.headers.get("host", "localhost:8501")
            _proto = "https" if (not _host.startswith("localhost") and not _host.startswith("127.")) else "http"
            _base_url = f"{_proto}://{_host}"

        tv_full_url = f"{_base_url}?{tv_query}"
        tv_short_url = f"{_base_url}?tv={int(tid)}-{int(jornada_sel['id'])}"

        st.markdown("#### 🔗 Link TV")
        _col_link, _col_copy = st.columns([5, 1])
        _col_link.code(tv_short_url, language=None)
        _col_copy.markdown(
            f"""<button onclick="navigator.clipboard.writeText('{tv_short_url}').then(()=>{{this.innerText='✅'}},()=>{{}})" """
            f"""style="margin-top:4px;padding:6px 10px;border-radius:6px;border:1px solid #aaa;cursor:pointer;"""
            f"""background:#f0f0f0;font-size:13px;">📋</button>""",
            unsafe_allow_html=True,
        )
        st.caption("Link corto de TV: fácil de escribir y compartir.")
        with st.expander("Ver link completo (avanzado)"):
            st.code(tv_full_url, language=None)

        try:
            import qrcode
            import io as _io
            _qr = qrcode.QRCode(box_size=4, border=2)
            _qr.add_data(tv_short_url)
            _qr.make(fit=True)
            _qr_img = _qr.make_image(fill_color="black", back_color="white")
            _qr_buf = _io.BytesIO()
            _qr_img.save(_qr_buf, format="PNG")
            _qr_buf.seek(0)
            with st.expander("📱 Ver QR del link TV"):
                st.image(_qr_buf, caption="Escanea para abrir en TV", width=180)
        except Exception:
            pass

        if st.button("Aplicar estos parámetros al URL actual", use_container_width=True):
            st.query_params.clear()
            st.query_params["view"] = "tv"
            st.query_params["mode"] = "display"
            st.query_params["torneo_id"] = str(int(tid))
            st.query_params["jornada_id"] = str(int(jornada_sel["id"]))
            st.query_params["auto"] = "1" if auto_tv else "0"
            st.query_params["interval"] = str(int(intervalo))
            st.query_params["hide"] = "1" if tv_full else "0"
            st.rerun()

    if auto_tv and tv_readonly:
        now = time.time()
        last_ts = st.session_state.get("tv_last_switch_ts")
        if not last_ts:
            st.session_state["tv_last_switch_ts"] = now
        elif now - last_ts >= max(1.0, float(intervalo) - 1.0):
            if total_paginas > 1:
                st.session_state["tv_page_idx"] = (st.session_state["tv_page_idx"] + 1) % total_paginas
            st.session_state["tv_last_switch_ts"] = now
        st.markdown(f"<meta http-equiv='refresh' content='{int(intervalo)}'>", unsafe_allow_html=True)

    if auto_tv and total_paginas > 1 and not tv_readonly:
        now = time.time()
        last_ts = st.session_state.get("tv_last_switch_ts")
        if not last_ts:
            st.session_state["tv_last_switch_ts"] = now
        elif now - last_ts >= float(intervalo):
            st.session_state["tv_page_idx"] = (st.session_state["tv_page_idx"] + 1) % total_paginas
            st.session_state["tv_last_switch_ts"] = now
            st.rerun()
        st.markdown(f"<meta http-equiv='refresh' content='{int(intervalo)}'>", unsafe_allow_html=True)

    if tv_full and not tv_readonly:
        # El toggle del operador para ocultar su propio sidebar
        st.markdown(
            """
            <style>
            section[data-testid="stSidebar"] {display: none !important;}
            </style>
            """,
            unsafe_allow_html=True,
        )

    pagina_canchas = paginas[st.session_state["tv_page_idx"]] if paginas else []
    for fila in range(2):
        cols = st.columns(5)
        for col in range(5):
            idx = fila * 5 + col
            with cols[col]:
                if idx >= len(pagina_canchas):
                    st.write("")
                    continue
                c = pagina_canchas[idx]
                jugadores_orden = sorted(c.get("jugadores", []), key=lambda x: x.get("posicion", 99))
                # Calcular puntos por posición si hay resultado
                _pts_map: dict[int, int] = {}
                if c.get("resultado"):
                    _r = c["resultado"]
                    _pts_tuple = calcular_puntos_cancha(
                        _r["set1_a"], _r["set1_b"],
                        _r["set2_a"], _r["set2_b"],
                        _r["set3_a"], _r["set3_b"],
                    )
                    _pts_map = {1: _pts_tuple[0], 2: _pts_tuple[1], 3: _pts_tuple[2], 4: _pts_tuple[3]}
                with st.container(border=True):
                    _cf = (c.get("cancha_fisica") or "").strip()
                    _titulo_cancha = f"Cancha {cancha_virtual_label(c['numero_cancha'])}"
                    if _cf:
                        _titulo_cancha += f" · {_cf}"
                    st.markdown(f"### {_titulo_cancha}")
                    st.caption(f"⏰ {c.get('horario') or '-'}")

                    for j in jugadores_orden:
                        cf, cn = st.columns([1, 4])
                        with cf:
                            mostrar_foto(j.get("foto_sin_fondo", ""), j.get("foto_original", ""), size=63)
                        with cn:
                            _pos = j.get("posicion", 0)
                            _jid = int(j.get("jugador_id", 0) or 0)
                            _llego = _jid in asistencia_llegaron
                            _name_color = "#14833b" if _llego else "inherit"
                            _llego_badge = " ✅" if _llego else ""
                            _pts_badge = (
                                f" <span style='color:#e10600;font-weight:700'>{_pts_map[_pos]:+d}pts</span>"
                                if _pos in _pts_map else ""
                            )
                            st.markdown(
                                f"<span style='font-size:1rem;color:{_name_color}'>**P{_pos} · {j.get('nombre', '-')}**{_llego_badge}{_pts_badge}</span>",
                                unsafe_allow_html=True,
                            )
                        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

                    if c.get("resultado"):
                        _r = c["resultado"]
                        st.caption(
                            f"S1 {_r['set1_a']}-{_r['set1_b']} | "
                            f"S2 {_r['set2_a']}-{_r['set2_b']} | "
                            f"S3 {_r['set3_a']}-{_r['set3_b']}"
                        )



    # ── Franja de patrocinadores (solo en modo display) ──────────────
    if tv_readonly:
        _sponsor_rutas = []
        for _n in range(1, 9):
            _sp = torneo.get(f"sponsor_logo_{_n}_path", "")
            if _sp:
                _rp = resolver_ruta(_sp)
                if _rp.exists():
                    _sponsor_rutas.append(_rp)
        if _sponsor_rutas:
            st.markdown("<hr style='margin:0.2rem 0;border-color:#444;'>", unsafe_allow_html=True)
            _total = len(_sponsor_rutas)
            _tile_h = 102 if _total <= 3 else (88 if _total <= 5 else 74)

            # Tira única para eliminar cualquier separación visual entre logos.
            _strip_png = _sponsor_strip_bytes(
                tuple(str(p) for p in _sponsor_rutas),
                cell_w=340,
                cell_h=_tile_h * 3,
                padding=2,
            )
            st.image(_strip_png, use_container_width=True)

    if tv_readonly and auto_tv and total_paginas > 1:
        time.sleep(float(intervalo))
        st.session_state["tv_page_idx"] = (st.session_state["tv_page_idx"] + 1) % total_paginas
        st.rerun()

# ═══════════════════════════════════════════════════════════════
# PÁGINA: CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════
elif pagina == "⚙️  Configuración":
    st.title("⚙️ Configuración del Torneo")
    st.divider()

    tid = torneo["id"]

    with st.form("form_config"):
        st.markdown("### Datos generales")
        nombre    = st.text_input("Nombre", value=torneo["nombre"])
        temporada = st.text_input("Temporada", value=torneo["temporada"])
        num_can   = st.number_input("Canchas", 1, 20, value=torneo["num_canchas"])
        tv_theme_actual = str(torneo.get("tv_theme", "apj") or "apj").lower()
        tv_theme = st.selectbox(
            "Tema Pantalla TV (Vercel)",
            options=["apj", "ocean", "sunset"],
            index=["apj", "ocean", "sunset"].index(tv_theme_actual) if tv_theme_actual in {"apj", "ocean", "sunset"} else 0,
            help="Este tema se usa automaticamente en la pantalla TV de Vercel para este torneo.",
        )

        st.markdown("### Horarios")
        horarios_actuales = listar_horarios(tid)
        horarios_txt = st.text_area(
            "Horarios (uno por línea)",
            value="\n".join(h["nombre"] for h in horarios_actuales),
            height=100,
        )
        canchas_fisicas_txt = st.text_area(
            "Canchas físicas (una por línea)",
            value=torneo.get("canchas_fisicas_txt", ""),
            height=100,
            help="Ejemplo: Central 1, Central 2, Pista 3...",
        )

        st.markdown("### Logos")
        logo_left_actual = torneo.get("logo_left_path") or torneo.get("logo_path", "")
        logo_right_actual = torneo.get("logo_right_path", "")
        col_logo_cfg_1, col_logo_cfg_2 = st.columns(2)
        if logo_left_actual:
            with col_logo_cfg_1:
                _mostrar_imagen_ref(logo_left_actual, width=100, caption="Logo izquierdo")
        if logo_right_actual:
            with col_logo_cfg_2:
                _mostrar_imagen_ref(logo_right_actual, width=100, caption="Logo derecho (solo PDF)")
        logo_left_file = st.file_uploader("Subir logo izquierdo", type=["png", "jpg", "jpeg"], key="cfg_logo_left")
        logo_right_file = st.file_uploader("Subir logo derecho (solo PDF)", type=["png", "jpg", "jpeg"], key="cfg_logo_right")

        st.markdown("### Logo cabecera TV")
        tv_header_logo_actual = torneo.get("tv_header_logo_path", "")
        if tv_header_logo_actual:
            _mostrar_imagen_ref(tv_header_logo_actual, width=300, caption="Cabecera TV actual")
        tv_header_logo_file = st.file_uploader(
            "Subir logo/banner para la cabecera de Pantalla TV",
            type=["png", "jpg", "jpeg"],
            key="cfg_tv_header_logo",
            help="Se mostrará como imagen completa en la parte superior de la Pantalla TV.",
        )

        st.markdown("### Patrocinadores en planilla PDF")
        sponsor_actuales = [torneo.get(f"sponsor_logo_{idx}_path", "") for idx in range(1, 9)]
        sponsor_files = []
        for fila in range(2):
            cols_sponsor = st.columns(4)
            for col_idx in range(4):
                idx = fila * 4 + col_idx + 1
                if idx > 8:
                    break
                sponsor_actual = sponsor_actuales[idx - 1]
                with cols_sponsor[col_idx]:
                    if sponsor_actual:
                        _mostrar_imagen_ref(sponsor_actual, width=90, caption=f"Sponsor {idx}")
                    sponsor_files.append(
                        st.file_uploader(
                            f"Sponsor {idx}",
                            type=["png", "jpg", "jpeg", "webp"],
                            key=f"cfg_sponsor_{idx}",
                        )
                    )

        if st.form_submit_button("💾 Guardar cambios", type="primary"):
            assets_dir = BASE_DIR / "assets"
            assets_dir.mkdir(exist_ok=True)

            logo_left_path = logo_left_actual
            if logo_left_file:
                logo_left_path = _guardar_upload_persistente(
                    logo_left_file,
                    folder=f"torneos/{tid}/logos",
                    fallback_dir=assets_dir,
                )
            else:
                logo_left_path = _migrar_ref_local_a_storage(
                    logo_left_path,
                    object_path=build_storage_object_path(f"torneos/{tid}/logos", file_name="logo_left"),
                )

            logo_right_path = logo_right_actual
            if logo_right_file:
                logo_right_path = _guardar_upload_persistente(
                    logo_right_file,
                    folder=f"torneos/{tid}/logos",
                    fallback_dir=assets_dir,
                )
            else:
                logo_right_path = _migrar_ref_local_a_storage(
                    logo_right_path,
                    object_path=build_storage_object_path(f"torneos/{tid}/logos", file_name="logo_right"),
                )

            tv_header_logo_path = tv_header_logo_actual
            if tv_header_logo_file:
                tv_header_logo_path = _guardar_upload_persistente(
                    tv_header_logo_file,
                    folder=f"torneos/{tid}/tv",
                    fallback_dir=assets_dir,
                )
            else:
                tv_header_logo_path = _migrar_ref_local_a_storage(
                    tv_header_logo_path,
                    object_path=build_storage_object_path(f"torneos/{tid}/tv", file_name="tv_header"),
                )

            sponsor_updates = {}
            for idx in range(1, 9):
                sponsor_path = sponsor_actuales[idx - 1]
                sponsor_file = sponsor_files[idx - 1]
                if sponsor_file:
                    if storage_enabled():
                        sponsor_path = upload_bytes_to_storage(
                            build_storage_object_path(
                                f"torneos/{tid}/sponsors",
                                file_name=f"sponsor_{idx}",
                            ),
                            sponsor_file.getvalue(),
                            sponsor_file.type or None,
                        )
                    else:
                        sponsor_ext = extension_desde_filename(sponsor_file.name)
                        sponsor_dest = assets_dir / f"sponsor_{idx}{sponsor_ext}"
                        sponsor_dest.write_bytes(sponsor_file.getvalue())
                        sponsor_path = ruta_relativa_a_base(sponsor_dest)
                else:
                    sponsor_path = _migrar_ref_local_a_storage(
                        sponsor_path,
                        object_path=build_storage_object_path(
                            f"torneos/{tid}/sponsors",
                            file_name=f"sponsor_{idx}",
                        ),
                    )
                sponsor_updates[f"sponsor_logo_{idx}_path"] = sponsor_path

            actualizar_torneo(tid, nombre=nombre, temporada=temporada,
                              num_canchas=int(num_can), logo_path=logo_left_path,
                              logo_left_path=logo_left_path, logo_right_path=logo_right_path,
                              canchas_fisicas_txt=canchas_fisicas_txt,
                              tv_theme=tv_theme,
                              tv_header_logo_path=tv_header_logo_path,
                              **sponsor_updates)
            crear_horarios(tid, [h for h in horarios_txt.splitlines() if h.strip()])
            st.success("✅ Configuración guardada.")
            st.rerun()

    st.divider()
    st.markdown("### ⚠️ Zona peligrosa")
    with st.expander("Eliminar este torneo"):
        st.warning("Esta acción eliminará todos los datos del torneo. No se puede deshacer.")
        confirmar = st.text_input("Escribe el nombre del torneo para confirmar:")
        if st.button("🗑️ Eliminar torneo", type="secondary"):
            if confirmar.strip() == torneo["nombre"]:
                eliminar_torneo(tid)
                st.session_state.torneo_id = None
                st.success("Torneo eliminado.")
                st.rerun()
            else:
                st.error("El nombre no coincide.")
