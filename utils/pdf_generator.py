"""
pdf_generator.py
Genera PDFs de resumen de jornada y ranking general para compartir por WhatsApp.
"""
from fpdf import FPDF
from pathlib import Path
from datetime import datetime
from PIL import Image

BASE_DIR = Path(__file__).parent.parent


def _cancha_label(n: int) -> str:
    """Convierte número de cancha a letra(s): 1→A, 2→B, ..., 26→Z, 27→AA."""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _nombre_apellido(nombre: str) -> str:
    """Convierte 'Juan García' a 'Juan G.' (nombre + primera letra del apellido)."""
    partes = nombre.strip().split()
    if len(partes) < 2:
        return nombre.strip()
    return f"{partes[0]} {partes[-1][0]}."


# Colores corporativos
AZUL       = (30,  80,  160)
AZUL_CLARO = (220, 230, 245)
VERDE      = (0,   130,  60)
ROJO       = (180,  30,  30)
GRIS       = (100, 100, 100)
BLANCO     = (255, 255, 255)
NEGRO      = (30,   30,  30)
AMARILLO   = (180, 140,   0)
FILA_PAR   = (240, 245, 255)
FILA_IMPAR = (255, 255, 255)


def _watermark_path() -> Path | None:
    """Prepara una marca de agua RGBA de baja opacidad para asegurar visibilidad en PDF."""
    src = BASE_DIR / "assets" / "pighead_black.png"
    if not src.exists():
        return None

    cache_dir = BASE_DIR / "assets" / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dst = cache_dir / "pighead_black_wm_v2.png"

    try:
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst

        limite_original = Image.MAX_IMAGE_PIXELS
        try:
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(src) as img:
                rgba = img.convert("RGBA")
                max_dim = 1800
                rgba.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                alpha = rgba.getchannel("A")
                alpha = alpha.point(lambda p: int(p * 0.18))
                rgba.putalpha(alpha)
                rgba.save(dst, format="PNG", optimize=True)
        finally:
            Image.MAX_IMAGE_PIXELS = limite_original

        return dst
    except Exception:
        return src


class LigaPDF(FPDF):
    def __init__(
        self,
        liga_nombre: str,
        temporada: str,
        logo_left_path: str = "",
        logo_right_path: str = "",
    ):
        super().__init__()
        self.liga_nombre = liga_nombre
        self.temporada = temporada
        self.logo_left_path = logo_left_path
        self.logo_right_path = logo_right_path
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        # ── Logos configurables del usuario ──
        if self.logo_left_path and Path(self.logo_left_path).exists():
            self.image(str(self.logo_left_path), x=10, y=8, h=18)

        # ── Logo Pighead blanco fijo (siempre en la derecha) ──
        if self.logo_right_path and Path(self.logo_right_path).exists():
            self.image(str(self.logo_right_path), x=172, y=9, h=13)
        else:
            ph_white = BASE_DIR / "assets" / "pighead_white.png"
            if ph_white.exists():
                self.image(str(ph_white), x=172, y=9, h=13)

        # Nombre de la liga
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*AZUL)
        self.set_xy(10, 8)
        self.cell(190, 9, self.liga_nombre, align="C")

        # Temporada
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*GRIS)
        self.set_xy(10, 17)
        self.cell(190, 6, f"Temporada {self.temporada}", align="C")

        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRIS)
        self.set_xy(10, 23)
        self.cell(190, 4, "Powered by Pighead", align="C")

        # Línea separadora
        self.set_y(30)
        self.set_draw_color(*AZUL)
        self.set_line_width(0.6)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def _draw_watermark(self):
        """Dibuja la marca de agua centrada al final para que no quede tapada."""
        wm_path = _watermark_path()
        if not wm_path or not wm_path.exists():
            return
        wm_w = 160
        wm_x = (210 - wm_w) / 2
        wm_y = (297 - wm_w) / 2
        self.image(str(wm_path), x=wm_x, y=wm_y, w=wm_w)

    def footer(self):
        self._draw_watermark()
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRIS)
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        self.cell(0, 10, f"Generado el {fecha}  |  Powered by Pighead  |  Pag. {self.page_no()}", align="C")

    def titulo_seccion(self, texto: str):
        """Encabezado azul para cada cancha o sección."""
        self.set_fill_color(*AZUL)
        self.set_text_color(*BLANCO)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"  {texto}", fill=True)
        self.ln(8)

    def fila_tabla(self, cols: list, widths: list, aligns: list,
                   fila_num: int = 0, bold: bool = False,
                   color_texto=None):
        """Dibuja una fila de tabla con alternado de colores."""
        fill_color = FILA_PAR if fila_num % 2 == 0 else FILA_IMPAR
        self.set_fill_color(*fill_color)

        if color_texto:
            self.set_text_color(*color_texto)
        else:
            self.set_text_color(*NEGRO)

        self.set_font("Helvetica", "B" if bold else "", 10)

        for texto, ancho, alineacion in zip(cols, widths, aligns):
            self.cell(ancho, 7, str(texto), border=1, align=alineacion, fill=True)
        self.ln(7)

    def encabezado_tabla(self, cols: list, widths: list, aligns: list):
        """Fila de encabezado azul para tablas."""
        self.set_fill_color(*AZUL)
        self.set_text_color(*BLANCO)
        self.set_font("Helvetica", "B", 10)
        for texto, ancho, alineacion in zip(cols, widths, aligns):
            self.cell(ancho, 8, texto, border=1, align=alineacion, fill=True)
        self.ln(8)


def _pts_str(pts) -> str:
    """Formatea un número de puntos con signo."""
    try:
        n = int(pts)
        return f"+{n}" if n > 0 else str(n)
    except (TypeError, ValueError):
        return str(pts)


def _torneo_pdf_kwargs(torneo: dict | None) -> dict:
    torneo = torneo or {}
    return {
        "liga_nombre": torneo.get("nombre", "Liga"),
        "temporada": torneo.get("temporada", ""),
        "logo_left_path": torneo.get("logo_left_path") or torneo.get("logo_path", ""),
        "logo_right_path": torneo.get("logo_right_path", ""),
    }


def _resolve_pdf_path(path_str: str) -> Path | None:
    if not path_str:
        return None
    path = Path(path_str)
    if path.exists():
        return path
    alt = BASE_DIR / path_str
    if alt.exists():
        return alt
    return None


def generar_pdf_jornada(numero_jornada: int, canchas: list, output_path, torneo: dict | None = None) -> Path:
    """
    Genera el PDF de resultados de una jornada.
    Incluye tabla de jugadores por cancha con puntos y marcadores.
    """
    pdf = LigaPDF(**_torneo_pdf_kwargs(torneo))
    pdf.add_page()

    # Título de la jornada
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 10, f"JORNADA {numero_jornada}  -  Resultados", align="C")
    pdf.ln(12)

    widths_j  = [10, 115, 30, 30]
    aligns_j  = ["C", "L", "C", "C"]
    headers_j = ["Pos", "Jugador", "Puntos", "Posicion"]

    medallas = ["1 er", "2 do", "3 er", "4 to"]

    for cancha in canchas:
        # Revisar espacio disponible en la página
        if pdf.get_y() > 230:
            pdf.add_page()

        pdf.titulo_seccion(f"CANCHA {_cancha_label(cancha['numero'])}")
        pdf.encabezado_tabla(headers_j, widths_j, aligns_j)

        for i, j in enumerate(cancha["jugadores"]):
            pts = j["puntos"]
            if i == 0:
                color = VERDE
            elif i == len(cancha["jugadores"]) - 1:
                color = ROJO
            else:
                color = NEGRO

            pdf.fila_tabla(
                cols=[medallas[i] if i < 4 else f"{i+1}o",
                      j["nombre"],
                      _pts_str(pts),
                      f"#{i+1} cancha"],
                widths=widths_j,
                aligns=aligns_j,
                fila_num=i,
                bold=(i == 0),
                color_texto=color,
            )

        # Marcadores de sets
        sets = cancha.get("sets", [])
        if any(s[0] or s[1] for s in sets):
            jugadores = cancha["jugadores"]
            p = [_nombre_apellido(j["nombre"]) for j in jugadores]  # nombre + inicial apellido

            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*GRIS)
            pdf.ln(1)

            lineas_sets = [
                f"Set 1: ({p[0]}+{p[1]}) {sets[0][0]} - {sets[0][1]} ({p[2]}+{p[3]})",
                f"Set 2: ({p[0]}+{p[2]}) {sets[1][0]} - {sets[1][1]} ({p[1]}+{p[3]})",
                f"Set 3: ({p[0]}+{p[3]}) {sets[2][0]} - {sets[2][1]} ({p[1]}+{p[2]})",
            ]
            for linea in lineas_sets:
                pdf.cell(0, 5, "  " + linea)
                pdf.ln(5)

        pdf.ln(6)

    output_path = Path(output_path)
    pdf.output(str(output_path))
    return output_path


def generar_pdf_ranking(
    ranking: list,
    output_path,
    jornada_ref: int | None = None,
    detallado: bool = True,
    torneo: dict | None = None,
) -> Path:
    """
    Genera el PDF del Ranking General acumulado.
    """
    pdf = LigaPDF(**_torneo_pdf_kwargs(torneo))
    pdf.add_page()

    # Título
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*AZUL)
    titulo = "RANKING GENERAL"
    if jornada_ref:
        titulo += f"  -  Despues de Jornada {jornada_ref}"
    pdf.cell(0, 10, titulo, align="C")
    pdf.ln(12)

    # Encabezado tabla
    # Determinar columnas de jornadas
    nums_jornadas = sorted(
        {n for r in ranking for n in r.get("pts_por_jornada", {}).keys()} |
        {n for r in ranking for n in r.get("pen_por_jornada", {}).keys()}
    )

    if detallado:
        ancho_jugador = max(30, 130 - len(nums_jornadas) * 14)
        ancho_j = 14 if nums_jornadas else 0
        widths_r = [10, ancho_jugador] + [ancho_j] * len(nums_jornadas) + [20, 25]
        aligns_r = ["C", "L"] + ["C"] * len(nums_jornadas) + ["C", "C"]
        headers_r = ["Pos", "Jugador"] + [f"J{n}" for n in nums_jornadas] + ["Pen", "Total"]
    else:
        widths_r = [10, 75, 20, 25, 20, 25]
        aligns_r = ["C", "L", "C", "C", "C", "C"]
        headers_r = ["Pos", "Jugador", "PJ", "Puntos", "Pen", "Total"]

    pdf.encabezado_tabla(headers_r, widths_r, aligns_r)

    for r in ranking:
        pos = r["posicion"]
        total = r["total"]
        total_pen = r.get("total_pen", 0)

        if pos == 1:
            color = AMARILLO
            bold = True
        elif pos <= 3:
            color = AZUL
            bold = True
        else:
            color = NEGRO
            bold = False

        pos_txt = str(pos)

        if detallado:
            celdas_j = []
            for n in nums_jornadas:
                pts_j = r.get("pts_por_jornada", {})
                pen_j = r.get("pen_por_jornada", {})
                if n in pts_j:
                    celdas_j.append(_pts_str(pts_j[n]))
                elif n in pen_j:
                    celdas_j.append(str(pen_j[n]))
                else:
                    celdas_j.append("-")

            pen_str = _pts_str(total_pen) if total_pen else "0"

            pdf.fila_tabla(
                cols=[pos_txt, r["nombre"]] + celdas_j + [pen_str, _pts_str(total)],
                widths=widths_r,
                aligns=aligns_r,
                fila_num=pos,
                bold=bold,
                color_texto=color,
            )
        else:
            pj = r.get("jornadas_jugadas", 0)
            total_juego = r.get("total_juego", total - total_pen)
            pen_str = _pts_str(total_pen) if total_pen else "0"
            pdf.fila_tabla(
                cols=[pos_txt, r["nombre"], str(pj), _pts_str(total_juego), pen_str, _pts_str(total)],
                widths=widths_r,
                aligns=aligns_r,
                fila_num=pos,
                bold=bold,
                color_texto=color,
            )

    output_path = Path(output_path)
    pdf.output(str(output_path))
    return output_path


def generar_pdf_planilla_jornada(
    numero_jornada: int,
    canchas: list,
    output_path,
    torneo: dict | None = None,
    fecha_jornada: str | None = None,
) -> Path:
    """
    Genera una planilla vacia de jornada para que jugadores anoten resultados en cancha.
    """
    pdf = LigaPDF(**_torneo_pdf_kwargs(torneo))

    fecha_txt = fecha_jornada or datetime.now().strftime("%d/%m/%Y")
    try:
        fecha_txt = datetime.strptime(fecha_txt, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        pass

    paginas_generadas = 0
    for cancha in canchas:
        jugadores = cancha.get("jugadores", [])
        if len(jugadores) < 4:
            continue

        pdf.add_page()
        paginas_generadas += 1

        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*AZUL)
        pdf.cell(0, 10, f"JORNADA {numero_jornada}  -  Planilla de Carga", align="C")
        pdf.ln(11)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GRIS)
        pdf.cell(0, 6, "Completar en cancha y luego cargar en la app.")
        pdf.ln(8)

        p = [j["nombre"] for j in jugadores]
        horario = cancha.get("horario", "")
        titulo = f"CANCHA {_cancha_label(cancha['numero_cancha'])}"

        pdf.titulo_seccion(titulo)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GRIS)
        pdf.cell(0, 5, f"Jornada: {numero_jornada}    Fecha: {fecha_txt}    Hora: {horario or '-'}")
        pdf.ln(6)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*NEGRO)
        pdf.cell(75, 7, "Jugador", border=1, align="L")
        pdf.cell(115, 7, "Observaciones", border=1, align="L")
        pdf.ln(7)

        pdf.set_font("Helvetica", "", 10)
        for idx, nombre in enumerate(p, start=1):
            pdf.cell(75, 7, f"J{idx}: {nombre}", border=1, align="L")
            pdf.cell(115, 7, "", border=1, align="L")
            pdf.ln(7)
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Resultados:")
        pdf.ln(6)

        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, f"Set 1 ({_nombre_apellido(p[0])}+{_nombre_apellido(p[1])})  ____  -  ____  ({_nombre_apellido(p[2])}+{_nombre_apellido(p[3])})")
        pdf.ln(7)
        pdf.cell(0, 7, f"Set 2 ({_nombre_apellido(p[0])}+{_nombre_apellido(p[2])})  ____  -  ____  ({_nombre_apellido(p[1])}+{_nombre_apellido(p[3])})")
        pdf.ln(7)
        pdf.cell(0, 7, f"Set 3 ({_nombre_apellido(p[0])}+{_nombre_apellido(p[3])})  ____  -  ____  ({_nombre_apellido(p[1])}+{_nombre_apellido(p[2])})")
        pdf.ln(8)

        pdf.set_font("Helvetica", "", 10)
        pdf.cell(95, 7, f"Firma J1 ({_nombre_apellido(p[0])}): _____________________")
        pdf.cell(95, 7, f"Firma J2 ({_nombre_apellido(p[1])}): _____________________")
        pdf.ln(7)
        pdf.cell(95, 7, f"Firma J3 ({_nombre_apellido(p[2])}): _____________________")
        pdf.cell(95, 7, f"Firma J4 ({_nombre_apellido(p[3])}): _____________________")
        pdf.ln(6)

        sponsor_paths = [
            _resolve_pdf_path((torneo or {}).get(f"sponsor_logo_{idx}_path", ""))
            for idx in range(1, 9)
        ]
        sponsor_paths = [p for p in sponsor_paths if p and p.exists()]
        if sponsor_paths:
            y_slots = 220
            max_por_fila = 4
            filas = [sponsor_paths[:max_por_fila], sponsor_paths[max_por_fila:8]]

            for row, fila_paths in enumerate(filas):
                if not fila_paths:
                    continue
                n = len(fila_paths)
                if n == 1:
                    slot_w, slot_h, gap_x = 84, 24, 0
                elif n == 2:
                    slot_w, slot_h, gap_x = 64, 20, 8
                elif n == 3:
                    slot_w, slot_h, gap_x = 52, 18, 6
                else:
                    slot_w, slot_h, gap_x = 44, 16, 4
                ancho_total = len(fila_paths) * slot_w + max(0, len(fila_paths) - 1) * gap_x
                x0 = (210 - ancho_total) / 2
                y = y_slots + row * (24 + 8)
                for col, sponsor_path in enumerate(fila_paths):
                    x = x0 + col * (slot_w + gap_x)
                    pdf.image(str(sponsor_path), x=x, y=y, w=slot_w, h=slot_h, keep_aspect_ratio=True)

    if paginas_generadas == 0:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*AZUL)
        pdf.cell(0, 10, f"JORNADA {numero_jornada}  -  Planilla de Carga", align="C")
        pdf.ln(10)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*GRIS)
        pdf.multi_cell(0, 6, "No hay canchas completas para generar la planilla.")

    output_path = Path(output_path)
    pdf.output(str(output_path))
    return output_path
