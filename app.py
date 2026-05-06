"""
app.py  -  Liga APJ
App de gestión de liga de pádel americano.
Ejecutar: streamlit run app.py
"""
import tempfile
import os
import io
import time
from urllib.parse import urlencode
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image as _PILImage

@st.cache_data(show_spinner=False)
def _img_preview_bytes(path_str: str, max_px: int = 1400) -> bytes:
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


def _mostrar_imagen(path: Path, **kwargs):
    """Muestra imagen rápida; si PIL detecta bomba de descompresión, usa preview seguro."""
    try:
        st.image(str(path), **kwargs)
    except Exception as exc:
        if "DecompressionBombError" not in str(exc):
            raise
        st.image(_img_preview_bytes(str(path)), **kwargs)


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

from utils.database import (
    init_db,
    crear_torneo, listar_torneos, obtener_torneo, actualizar_torneo, eliminar_torneo,
    crear_horarios, listar_horarios,
    crear_jugador, listar_jugadores, actualizar_jugador, eliminar_jugador,
    listar_jornadas, marcar_jornada_completada, eliminar_jornada,
    actualizar_horario_cancha,
    obtener_canchas_jornada,
    guardar_resultado, guardar_ausencias_jornada, obtener_ausencias_jornada,
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
    guardar_foto_original,
    quitar_fondo_rembg,
    resolver_ruta,
    ruta_relativa_a_base,
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

# ─────────────────────────────────────────────
# Estado de sesión
# ─────────────────────────────────────────────
if "torneo_id" not in st.session_state:
    st.session_state.torneo_id = None
    # Si la URL trae torneo_id (ej: link TV compartido), lo auto-seleccionamos
    _qp_tid = st.query_params.get("torneo_id")
    if _qp_tid:
        try:
            st.session_state.torneo_id = int(str(_qp_tid))
        except (ValueError, TypeError):
            pass
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


def mostrar_foto(foto_sin_fondo: str, foto_original: str, size: int = 60):
    for ruta_rel in [foto_sin_fondo, foto_original]:
        if ruta_rel:
            ruta = resolver_ruta(ruta_rel)
            if ruta.exists():
                _mostrar_imagen(ruta, width=size)
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
                ruta_logo_left = resolver_ruta(logo_left)
                if ruta_logo_left.exists():
                    with col_logo_1:
                        _mostrar_imagen(ruta_logo_left, width=90)
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
                    cc.markdown(f"**C{c['numero_cancha']}**")
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

                    logo_left_path = ""
                    if logo_left_file:
                        logo_left_dest = assets_dir / logo_left_file.name
                        logo_left_dest.write_bytes(logo_left_file.getvalue())
                        logo_left_path = ruta_relativa_a_base(logo_left_dest)

                    logo_right_path = ""
                    if logo_right_file:
                        logo_right_dest = assets_dir / logo_right_file.name
                        logo_right_dest.write_bytes(logo_right_file.getvalue())
                        logo_right_path = ruta_relativa_a_base(logo_right_dest)

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
elif pagina == "👥  Jugadores":
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
                    mostrar_foto(j["foto_sin_fondo"], j["foto_original"], size=44)
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
                    r = resolver_ruta(jug["foto_original"])
                    if r.exists():
                        _mostrar_imagen(r, use_container_width=True)
                    else:
                        st.caption("Archivo no encontrado.")
                else:
                    st.info("Sin foto cargada.")

            with col_b:
                st.markdown("**Foto sin fondo**")
                if jug["foto_sin_fondo"]:
                    r = resolver_ruta(jug["foto_sin_fondo"])
                    if r.exists():
                        _mostrar_imagen(r, use_container_width=True)
                    else:
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
                        ruta = guardar_foto_original(nombre_sel, foto_file.name, foto_file.getvalue())
                        actualizar_jugador(jug["id"], foto_original=ruta_relativa_a_base(ruta))
                        st.success("Foto guardada.")
                        st.rerun()
            with bc2:
                if st.button("✨ Quitar fondo (rembg)", use_container_width=True):
                    if not jug["foto_original"]:
                        st.warning("Primero guarda la foto original.")
                    else:
                        ruta_abs = resolver_ruta(jug["foto_original"])
                        if not ruta_abs.exists():
                            st.error("Archivo original no encontrado.")
                        else:
                            try:
                                with st.spinner("Procesando con rembg..."):
                                    ruta_nobg = quitar_fondo_rembg(ruta_abs)
                                actualizar_jugador(jug["id"], foto_sin_fondo=ruta_relativa_a_base(ruta_nobg))
                                st.success("¡Fondo eliminado!")
                                st.rerun()
                            except RemBgNoDisponibleError as e:
                                st.error(str(e))
                            except Exception as e:
                                st.error(f"Error: {e}")


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
                    st.markdown(f"#### Cancha {cancha_n}")
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
                            f"Horario Cancha {i+1}",
                            options=horarios_cfg,
                            index=horarios_cfg.index(default_h),
                            key=f"j1_horario_{i+1}",
                        )
                    else:
                        h = st.text_input(f"Horario Cancha {i+1}", key=f"j1_horario_txt_{i+1}")
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
                try:
                    canchas_gen = generar_canchas_por_movimiento(canchas_base, int(movimiento))
                except ValueError:
                    # Fallback para casos especiales (sin resultados completos, etc.).
                    ranking_previo = calcular_ranking(tid)
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
                            f"Horario Cancha {i+1}",
                            options=horarios_cfg,
                            index=horarios_cfg.index(default_h),
                            key=f"auto_horario_{i+1}",
                        )
                    else:
                        h = st.text_input(f"Horario Cancha {i+1}", key=f"auto_horario_txt_{i+1}")
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
                    for c in canchas:
                        ctop1, ctop2 = st.columns([2, 1])
                        ctop1.markdown(f"**Cancha {c['numero_cancha']}**")
                        nuevo_horario = ctop2.text_input(
                            "Horario",
                            value=c["horario"] or "",
                            key=f"edit_horario_{c['id']}",
                            label_visibility="collapsed",
                            placeholder="Horario",
                        )
                        if nuevo_horario != (c["horario"] or ""):
                            actualizar_horario_cancha(c["id"], nuevo_horario.strip())
                            st.success(f"Horario actualizado en Cancha {c['numero_cancha']}")
                            st.rerun()

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
                                f"**C{c['numero_cancha']}** {c['horario']}  ·  "
                                f"{resumen_pts}  ·  "
                                f"_{r['set1_a']}-{r['set1_b']} / {r['set2_a']}-{r['set2_b']} / {r['set3_a']}-{r['set3_b']}_"
                            )
                        else:
                            marcar_jornada_completada(jornada["id"])
                            invalidar_cache_torneo()
                            st.rerun()
                    if bc2.button("🗑️ Eliminar jornada", key=f"del_j_{jornada['id']}", use_container_width=True):
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

        with st.expander(f"🎾 Cancha {c['numero_cancha']}  —  {c['horario']}", expanded=(res is None)):
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
    ranking = calcular_ranking(tid)
    if not ranking:
        st.info("Sin datos de ranking todavía.")
        st.stop()

    jornadas = listar_jornadas(tid)
    completadas = [j for j in jornadas if j["completada"]]
    ultima = completadas[-1]["numero"] if completadas else "—"
    st.markdown(f"Clasificación hasta **Jornada {ultima}**")

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
    tv_mode = str(st.query_params.get("mode", "operator")).strip().lower()
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
                padding-top:0.4rem !important;
                padding-bottom:0 !important;
                padding-left:0.6rem !important;
                padding-right:0.6rem !important;
                max-width:100% !important;
                height:100vh;
                overflow:hidden;
                display:flex;
                flex-direction:column;
            }
            div[data-testid="stHorizontalBlock"] {
                flex:1;
                min-height:0;
                align-items:stretch;
                gap:0.3rem;
            }
            div[data-testid="stColumn"] > div:first-child {
                height:100%;
                overflow:hidden;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                height:100% !important;
                overflow:hidden;
            }
            div[data-testid="stVerticalBlock"] {
                height:100%;
                overflow:hidden;
            }
            /* reducir tamaño de fuente en tarjetas */
            div[data-testid="stVerticalBlockBorderWrapper"] h3 {font-size:1rem !important; margin:0 !important;}
            div[data-testid="stVerticalBlockBorderWrapper"] p {font-size:0.78rem !important; margin:0 !important;}
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
        qp_jornada_id = int(str(st.query_params.get("jornada_id", "0")))
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
        st.markdown(
            f"<p style='margin:0;padding:0;font-size:0.8rem;color:#888;'>"
            f"📅 Jornada {jornada_sel['numero']} — {jornada_sel['fecha']} &nbsp;|&nbsp; "
            f"Página <span id='tv_pg_num'></span></p>",
            unsafe_allow_html=True,
        )
    else:
        jornada_sel = opciones[
            st.selectbox("Jornada a mostrar", labels_jornada, index=idx_default_j, key="tv_jornada")
        ]
    canchas = obtener_canchas_jornada(jornada_sel["id"])
    if not canchas:
        st.info("La jornada no tiene canchas cargadas.")
        st.stop()

    if st.session_state.get("tv_last_jornada_id") != jornada_sel["id"]:
        st.session_state["tv_last_jornada_id"] = jornada_sel["id"]
        st.session_state["tv_page_idx"] = 0
        st.session_state["tv_last_switch_ts"] = time.time()

    canchas_por_pagina = 10
    paginas = [canchas[i:i + canchas_por_pagina] for i in range(0, len(canchas), canchas_por_pagina)]
    total_paginas = max(1, len(paginas))
    st.session_state["tv_page_idx"] = min(st.session_state.get("tv_page_idx", 0), total_paginas - 1)

    qp_auto = str(st.query_params.get("auto", "")).strip().lower() in ("1", "true", "yes")
    qp_hide = str(st.query_params.get("hide", "")).strip().lower() in ("1", "true", "yes")
    try:
        qp_interval = int(str(st.query_params.get("interval", "10")))
    except Exception:
        qp_interval = 10
    if qp_interval not in [5, 8, 10, 12, 15, 20]:
        qp_interval = 10

    if str(st.query_params.get("view", "")).strip().lower() == "tv":
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
        idx_intervalo = [5, 8, 10, 12, 15, 20].index(st.session_state.get("tv_interval", 10))
        intervalo = cnav4.selectbox("Intervalo (seg)", options=[5, 8, 10, 12, 15, 20], index=idx_intervalo, key="tv_interval")
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

        st.markdown("#### 🔗 Link TV")
        _col_link, _col_copy = st.columns([5, 1])
        _col_link.code(tv_full_url, language=None)
        _col_copy.markdown(
            f"""<button onclick="navigator.clipboard.writeText('{tv_full_url}').then(()=>{{this.innerText='✅'}},()=>{{}})" """
            f"""style="margin-top:4px;padding:6px 10px;border-radius:6px;border:1px solid #aaa;cursor:pointer;"""
            f"""background:#f0f0f0;font-size:13px;">📋</button>""",
            unsafe_allow_html=True,
        )
        st.caption("Abre este link en cualquier dispositivo — el torneo y jornada se seleccionan automáticamente.")

        try:
            import qrcode
            import io as _io
            _qr = qrcode.QRCode(box_size=4, border=2)
            _qr.add_data(tv_full_url)
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

    if auto_tv and total_paginas > 1:
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
                with st.container(border=True):
                    st.markdown(f"### Cancha {c['numero_cancha']}")
                    st.caption(f"⏰ {c.get('horario') or '-'}")

                    for j in jugadores_orden:
                        cf, cn = st.columns([1, 4])
                        with cf:
                            mostrar_foto(j.get("foto_sin_fondo", ""), j.get("foto_original", ""), size=38)
                        with cn:
                            st.markdown(f"**P{j.get('posicion', '-')} · {j.get('nombre', '-')}**")

                    if c.get("resultado"):
                        r = c["resultado"]
                        st.caption(
                            f"S1 {r['set1_a']}-{r['set1_b']} | "
                            f"S2 {r['set2_a']}-{r['set2_b']} | "
                            f"S3 {r['set3_a']}-{r['set3_b']}"
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
            _por_fila = 4
            for _ini in range(0, len(_sponsor_rutas), _por_fila):
                _fila = _sponsor_rutas[_ini:_ini + _por_fila]
                _sp_cols = st.columns(len(_fila))
                for _si, _sruta in enumerate(_fila):
                    with _sp_cols[_si]:
                        st.image(_logo_tile_bytes(str(_sruta)), use_container_width=True)

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

        st.markdown("### Horarios")
        horarios_actuales = listar_horarios(tid)
        horarios_txt = st.text_area(
            "Horarios (uno por línea)",
            value="\n".join(h["nombre"] for h in horarios_actuales),
            height=100,
        )

        st.markdown("### Logos")
        logo_left_actual = torneo.get("logo_left_path") or torneo.get("logo_path", "")
        logo_right_actual = torneo.get("logo_right_path", "")
        col_logo_cfg_1, col_logo_cfg_2 = st.columns(2)
        if logo_left_actual:
            r_left = resolver_ruta(logo_left_actual)
            if r_left.exists():
                with col_logo_cfg_1:
                    _mostrar_imagen(r_left, width=100, caption="Logo izquierdo")
        if logo_right_actual:
            r_right = resolver_ruta(logo_right_actual)
            if r_right.exists():
                with col_logo_cfg_2:
                    _mostrar_imagen(r_right, width=100, caption="Logo derecho (solo PDF)")
        logo_left_file = st.file_uploader("Subir logo izquierdo", type=["png", "jpg", "jpeg"], key="cfg_logo_left")
        logo_right_file = st.file_uploader("Subir logo derecho (solo PDF)", type=["png", "jpg", "jpeg"], key="cfg_logo_right")

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
                        r_sponsor = resolver_ruta(sponsor_actual)
                        if r_sponsor.exists():
                            _mostrar_imagen(r_sponsor, width=90, caption=f"Sponsor {idx}")
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
                logo_left_dest = assets_dir / logo_left_file.name
                logo_left_dest.write_bytes(logo_left_file.getvalue())
                logo_left_path = ruta_relativa_a_base(logo_left_dest)

            logo_right_path = logo_right_actual
            if logo_right_file:
                logo_right_dest = assets_dir / logo_right_file.name
                logo_right_dest.write_bytes(logo_right_file.getvalue())
                logo_right_path = ruta_relativa_a_base(logo_right_dest)

            sponsor_updates = {}
            for idx in range(1, 9):
                sponsor_path = sponsor_actuales[idx - 1]
                sponsor_file = sponsor_files[idx - 1]
                if sponsor_file:
                    sponsor_dest = assets_dir / sponsor_file.name
                    sponsor_dest.write_bytes(sponsor_file.getvalue())
                    sponsor_path = ruta_relativa_a_base(sponsor_dest)
                sponsor_updates[f"sponsor_logo_{idx}_path"] = sponsor_path

            actualizar_torneo(tid, nombre=nombre, temporada=temporada,
                              num_canchas=int(num_can), logo_path=logo_left_path,
                              logo_left_path=logo_left_path, logo_right_path=logo_right_path,
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
