"""
database.py
Capa de acceso a datos usando SQLite.
Sin dependencias externas — migrar a PostgreSQL en el futuro cambiando solo este archivo.
"""
import os
import sqlite3
from functools import lru_cache
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH  = BASE_DIR / "data" / "liga.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_URL esta configurada, pero falta psycopg. "
            "Instala dependencias con: pip install -r requirements.txt"
        ) from exc


def _pg_url() -> str:
    if DATABASE_URL.startswith("postgres://"):
        url = "postgresql://" + DATABASE_URL[len("postgres://"):]
    else:
        url = DATABASE_URL
    # Supabase / Streamlit Cloud require SSL
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


def _to_driver_sql(sql: str) -> str:
    if USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


class _ConnAdapter:
    def __init__(self, conn, use_postgres: bool):
        self._conn = conn
        self._use_postgres = use_postgres

    def execute(self, sql: str, params=()):
        return self._conn.execute(_to_driver_sql(sql), params)

    def executescript(self, script: str):
        if not self._use_postgres:
            return self._conn.executescript(script)
        statements = [s.strip() for s in script.split(";") if s.strip()]
        with self._conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)

    def __getattr__(self, item):
        return getattr(self._conn, item)


def _table_columns(conn: _ConnAdapter, table_name: str) -> set[str]:
    if USE_POSTGRES:
        rows = conn.execute(
            """SELECT column_name
               FROM information_schema.columns
               WHERE table_schema='public' AND table_name=%s""",
            (table_name,),
        ).fetchall()
        return {r["column_name"] for r in rows}
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {r["name"] for r in rows}


def _clear_read_caches():
    """Limpia caches de lecturas cuando cambia cualquier dato."""
    for fn in (
        listar_torneos,
        obtener_torneo,
        listar_horarios,
        listar_jugadores,
        obtener_jugador,
        listar_jornadas,
        obtener_canchas_jornada,
        obtener_ausencias_jornada,
        obtener_asistencia_jornada,
        calcular_ranking,
    ):
        try:
            fn.cache_clear()
        except AttributeError:
            pass


@contextmanager
def get_conn():
    if USE_POSTGRES:
        raw_conn = psycopg.connect(_pg_url(), row_factory=dict_row)
        conn = _ConnAdapter(raw_conn, use_postgres=True)
    else:
        DB_PATH.parent.mkdir(exist_ok=True)
        raw_conn = sqlite3.connect(DB_PATH)
        raw_conn.row_factory = sqlite3.Row
        raw_conn.execute("PRAGMA foreign_keys = ON")
        conn = _ConnAdapter(raw_conn, use_postgres=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Crea las tablas si no existen."""
    with get_conn() as conn:
        if USE_POSTGRES:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS torneos (
                id                  SERIAL PRIMARY KEY,
                nombre              TEXT    NOT NULL,
                temporada           TEXT    DEFAULT '',
                num_canchas         INTEGER NOT NULL DEFAULT 5,
                logo_path           TEXT    DEFAULT '',
                logo_left_path      TEXT    DEFAULT '',
                logo_right_path     TEXT    DEFAULT '',
                tv_header_logo_path TEXT    DEFAULT '',
                tv_theme            TEXT    DEFAULT 'apj',
                canchas_fisicas_txt TEXT    DEFAULT '',
                creado_en           TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS horarios (
                id        SERIAL PRIMARY KEY,
                torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                nombre    TEXT    NOT NULL,
                orden     INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS jugadores (
                id             SERIAL PRIMARY KEY,
                torneo_id      INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                nombre         TEXT    NOT NULL,
                foto_original  TEXT    DEFAULT '',
                foto_sin_fondo TEXT    DEFAULT '',
                activo         INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS jornadas (
                id         SERIAL PRIMARY KEY,
                torneo_id  INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                numero     INTEGER NOT NULL,
                fecha      TEXT    DEFAULT '',
                completada INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS canchas_jornada (
                id            SERIAL PRIMARY KEY,
                jornada_id    INTEGER NOT NULL REFERENCES jornadas(id) ON DELETE CASCADE,
                numero_cancha INTEGER NOT NULL,
                horario       TEXT    DEFAULT '',
                cancha_fisica TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS asignaciones (
                id                SERIAL PRIMARY KEY,
                cancha_jornada_id INTEGER NOT NULL REFERENCES canchas_jornada(id) ON DELETE CASCADE,
                jugador_id        INTEGER NOT NULL REFERENCES jugadores(id),
                posicion          INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS resultados (
                id                SERIAL PRIMARY KEY,
                cancha_jornada_id INTEGER NOT NULL UNIQUE REFERENCES canchas_jornada(id) ON DELETE CASCADE,
                set1_a INTEGER DEFAULT 0, set1_b INTEGER DEFAULT 0,
                set2_a INTEGER DEFAULT 0, set2_b INTEGER DEFAULT 0,
                set3_a INTEGER DEFAULT 0, set3_b INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS ausencias_jornada (
                id           SERIAL PRIMARY KEY,
                jornada_id   INTEGER NOT NULL REFERENCES jornadas(id) ON DELETE CASCADE,
                jugador_id   INTEGER NOT NULL REFERENCES jugadores(id),
                penalizacion INTEGER NOT NULL DEFAULT -10,
                UNIQUE (jornada_id, jugador_id)
            );

            CREATE TABLE IF NOT EXISTS asistencia_jornada (
                id         SERIAL PRIMARY KEY,
                jornada_id INTEGER NOT NULL REFERENCES jornadas(id) ON DELETE CASCADE,
                jugador_id INTEGER NOT NULL REFERENCES jugadores(id),
                llego      INTEGER NOT NULL DEFAULT 1,
                UNIQUE (jornada_id, jugador_id)
            );
            """)

            columnas_torneos = _table_columns(conn, "torneos")
            if "logo_left_path" not in columnas_torneos:
                conn.execute("ALTER TABLE torneos ADD COLUMN logo_left_path TEXT DEFAULT ''")
            if "logo_right_path" not in columnas_torneos:
                conn.execute("ALTER TABLE torneos ADD COLUMN logo_right_path TEXT DEFAULT ''")
            for idx in range(1, 9):
                col = f"sponsor_logo_{idx}_path"
                if col not in columnas_torneos:
                    conn.execute(f"ALTER TABLE torneos ADD COLUMN {col} TEXT DEFAULT ''")
            if "tv_header_logo_path" not in columnas_torneos:
                conn.execute("ALTER TABLE torneos ADD COLUMN tv_header_logo_path TEXT DEFAULT ''")
            if "tv_theme" not in columnas_torneos:
                conn.execute("ALTER TABLE torneos ADD COLUMN tv_theme TEXT DEFAULT 'apj'")
            if "canchas_fisicas_txt" not in columnas_torneos:
                conn.execute("ALTER TABLE torneos ADD COLUMN canchas_fisicas_txt TEXT DEFAULT ''")

            columnas_canchas_jornada = _table_columns(conn, "canchas_jornada")
            if "cancha_fisica" not in columnas_canchas_jornada:
                conn.execute("ALTER TABLE canchas_jornada ADD COLUMN cancha_fisica TEXT DEFAULT ''")
            conn.execute(
                """UPDATE torneos
                   SET logo_left_path = COALESCE(NULLIF(logo_left_path, ''), logo_path)
                   WHERE COALESCE(logo_left_path, '') = '' AND COALESCE(logo_path, '') != ''"""
            )
            conn.execute(
                """UPDATE torneos
                   SET tv_theme = 'apj'
                   WHERE COALESCE(tv_theme, '') = ''"""
            )
            return

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS torneos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT    NOT NULL,
            temporada   TEXT    DEFAULT '',
            num_canchas INTEGER NOT NULL DEFAULT 5,
            logo_path   TEXT    DEFAULT '',
            logo_left_path        TEXT DEFAULT '',
            logo_right_path       TEXT DEFAULT '',
            tv_header_logo_path   TEXT DEFAULT '',
            tv_theme             TEXT DEFAULT 'apj',
            canchas_fisicas_txt   TEXT DEFAULT '',
            creado_en   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS horarios (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
            nombre    TEXT    NOT NULL,
            orden     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS jugadores (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            torneo_id      INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
            nombre         TEXT    NOT NULL,
            foto_original  TEXT    DEFAULT '',
            foto_sin_fondo TEXT    DEFAULT '',
            activo         INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS jornadas (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            torneo_id  INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
            numero     INTEGER NOT NULL,
            fecha      TEXT    DEFAULT '',
            completada INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS canchas_jornada (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            jornada_id    INTEGER NOT NULL REFERENCES jornadas(id) ON DELETE CASCADE,
            numero_cancha INTEGER NOT NULL,
            horario       TEXT    DEFAULT '',
            cancha_fisica TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS asignaciones (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            cancha_jornada_id INTEGER NOT NULL REFERENCES canchas_jornada(id) ON DELETE CASCADE,
            jugador_id        INTEGER NOT NULL REFERENCES jugadores(id),
            posicion          INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS resultados (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            cancha_jornada_id INTEGER NOT NULL UNIQUE REFERENCES canchas_jornada(id) ON DELETE CASCADE,
            set1_a INTEGER DEFAULT 0, set1_b INTEGER DEFAULT 0,
            set2_a INTEGER DEFAULT 0, set2_b INTEGER DEFAULT 0,
            set3_a INTEGER DEFAULT 0, set3_b INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ausencias_jornada (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            jornada_id  INTEGER NOT NULL REFERENCES jornadas(id) ON DELETE CASCADE,
            jugador_id  INTEGER NOT NULL REFERENCES jugadores(id),
            penalizacion INTEGER NOT NULL DEFAULT -10,
            UNIQUE (jornada_id, jugador_id)
        );

        CREATE TABLE IF NOT EXISTS asistencia_jornada (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            jornada_id INTEGER NOT NULL REFERENCES jornadas(id) ON DELETE CASCADE,
            jugador_id INTEGER NOT NULL REFERENCES jugadores(id),
            llego      INTEGER NOT NULL DEFAULT 1,
            UNIQUE (jornada_id, jugador_id)
        );
        """)

        columnas_torneos = _table_columns(conn, "torneos")

        # Migra instalaciones antiguas donde jornadas.torneo_id referenciaba mal a jornadas(id).
        fk_jornadas = conn.execute("PRAGMA foreign_key_list(jornadas)").fetchall()
        fk_torneo_tabla = fk_jornadas[0][2] if fk_jornadas else ""
        if fk_torneo_tabla != "torneos":
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS jornadas_fix (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                torneo_id  INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                numero     INTEGER NOT NULL,
                fecha      TEXT    DEFAULT '',
                completada INTEGER DEFAULT 0
            );

            INSERT INTO jornadas_fix (id, torneo_id, numero, fecha, completada)
            SELECT id, torneo_id, numero, fecha, completada
            FROM jornadas;

            DROP TABLE jornadas;
            ALTER TABLE jornadas_fix RENAME TO jornadas;
            """)
            conn.execute("PRAGMA foreign_keys = ON")

        if "logo_left_path" not in columnas_torneos:
            conn.execute("ALTER TABLE torneos ADD COLUMN logo_left_path TEXT DEFAULT ''")
        if "logo_right_path" not in columnas_torneos:
            conn.execute("ALTER TABLE torneos ADD COLUMN logo_right_path TEXT DEFAULT ''")
        for idx in range(1, 9):
            col = f"sponsor_logo_{idx}_path"
            if col not in columnas_torneos:
                conn.execute(f"ALTER TABLE torneos ADD COLUMN {col} TEXT DEFAULT ''")
        if "tv_header_logo_path" not in columnas_torneos:
            conn.execute("ALTER TABLE torneos ADD COLUMN tv_header_logo_path TEXT DEFAULT ''")
        if "tv_theme" not in columnas_torneos:
            conn.execute("ALTER TABLE torneos ADD COLUMN tv_theme TEXT DEFAULT 'apj'")
        if "canchas_fisicas_txt" not in columnas_torneos:
            conn.execute("ALTER TABLE torneos ADD COLUMN canchas_fisicas_txt TEXT DEFAULT ''")

        columnas_canchas_jornada = _table_columns(conn, "canchas_jornada")
        if "cancha_fisica" not in columnas_canchas_jornada:
            conn.execute("ALTER TABLE canchas_jornada ADD COLUMN cancha_fisica TEXT DEFAULT ''")
        conn.execute(
            """UPDATE torneos
               SET logo_left_path = COALESCE(NULLIF(logo_left_path, ''), logo_path)
               WHERE COALESCE(logo_left_path, '') = '' AND COALESCE(logo_path, '') != ''"""
        )
        conn.execute(
            """UPDATE torneos
               SET tv_theme = 'apj'
               WHERE COALESCE(tv_theme, '') = ''"""
        )


# ─────────────────────────── TORNEOS ────────────────────────────

def crear_torneo(
    nombre: str,
    temporada: str,
    num_canchas: int,
    logo_path: str = "",
    logo_left_path: str = "",
    logo_right_path: str = "",
) -> int:
    with get_conn() as conn:
        if USE_POSTGRES:
            row = conn.execute(
                """INSERT INTO torneos
                   (nombre, temporada, num_canchas, logo_path, logo_left_path, logo_right_path)
                   VALUES (?,?,?,?,?,?)
                   RETURNING id""",
                (
                    nombre,
                    temporada,
                    num_canchas,
                    logo_path,
                    logo_left_path or logo_path,
                    logo_right_path,
                ),
            ).fetchone()
            return int(row["id"])
        cur = conn.execute(
            """INSERT INTO torneos
               (nombre, temporada, num_canchas, logo_path, logo_left_path, logo_right_path)
               VALUES (?,?,?,?,?,?)""",
            (
                nombre,
                temporada,
                num_canchas,
                logo_path,
                logo_left_path or logo_path,
                logo_right_path,
            ),
        )
        nuevo_id = cur.lastrowid
    _clear_read_caches()
    return nuevo_id


@lru_cache(maxsize=128)
def listar_torneos() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM torneos ORDER BY creado_en DESC"
        ).fetchall()
        return [dict(r) for r in rows]


@lru_cache(maxsize=256)
def obtener_torneo(torneo_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM torneos WHERE id=?", (torneo_id,)).fetchone()
        return dict(row) if row else None


def actualizar_torneo(torneo_id: int, **kwargs):
    with get_conn() as conn:
        # Filter kwargs to only include columns that actually exist in the table
        columnas = _table_columns(conn, "torneos")
        filtrado = {k: v for k, v in kwargs.items() if k in columnas}
        if not filtrado:
            return
        campos = ", ".join(f"{k}=?" for k in filtrado)
        valores = list(filtrado.values()) + [torneo_id]
        conn.execute(f"UPDATE torneos SET {campos} WHERE id=?", valores)
    _clear_read_caches()


def eliminar_torneo(torneo_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM torneos WHERE id=?", (torneo_id,))
    _clear_read_caches()


# ─────────────────────────── HORARIOS ───────────────────────────

def crear_horarios(torneo_id: int, horarios: list[str]):
    """Reemplaza los horarios del torneo con la nueva lista."""
    with get_conn() as conn:
        conn.execute("DELETE FROM horarios WHERE torneo_id=?", (torneo_id,))
        for i, h in enumerate(horarios):
            h = h.strip()
            if h:
                conn.execute(
                    "INSERT INTO horarios (torneo_id, nombre, orden) VALUES (?,?,?)",
                    (torneo_id, h, i),
                )
    _clear_read_caches()


@lru_cache(maxsize=256)
def listar_horarios(torneo_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM horarios WHERE torneo_id=? ORDER BY orden", (torneo_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────── JUGADORES ──────────────────────────

def crear_jugador(torneo_id: int, nombre: str) -> int:
    with get_conn() as conn:
        if USE_POSTGRES:
            row = conn.execute(
                "INSERT INTO jugadores (torneo_id, nombre) VALUES (?,?) RETURNING id",
                (torneo_id, nombre.strip()),
            ).fetchone()
            nuevo_id = int(row["id"])
        else:
            cur = conn.execute(
                "INSERT INTO jugadores (torneo_id, nombre) VALUES (?,?)",
                (torneo_id, nombre.strip()),
            )
            nuevo_id = cur.lastrowid
    _clear_read_caches()
    return nuevo_id


@lru_cache(maxsize=512)
def listar_jugadores(torneo_id: int, solo_activos: bool = False) -> list[dict]:
    sql = "SELECT * FROM jugadores WHERE torneo_id=?"
    if solo_activos:
        sql += " AND activo=1"
    sql += " ORDER BY nombre"
    with get_conn() as conn:
        rows = conn.execute(sql, (torneo_id,)).fetchall()
        return [dict(r) for r in rows]


@lru_cache(maxsize=1024)
def obtener_jugador(jugador_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jugadores WHERE id=?", (jugador_id,)).fetchone()
        return dict(row) if row else None


def actualizar_jugador(jugador_id: int, **kwargs):
    campos = ", ".join(f"{k}=?" for k in kwargs)
    valores = list(kwargs.values()) + [jugador_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE jugadores SET {campos} WHERE id=?", valores)
    _clear_read_caches()


def eliminar_jugador(jugador_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM jugadores WHERE id=?", (jugador_id,))
    _clear_read_caches()


# ─────────────────────────── JORNADAS ───────────────────────────

def crear_jornada(torneo_id: int, numero: int, fecha: str = "") -> int:
    with get_conn() as conn:
        if USE_POSTGRES:
            row = conn.execute(
                "INSERT INTO jornadas (torneo_id, numero, fecha) VALUES (?,?,?) RETURNING id",
                (torneo_id, numero, fecha),
            ).fetchone()
            nuevo_id = int(row["id"])
        else:
            cur = conn.execute(
                "INSERT INTO jornadas (torneo_id, numero, fecha) VALUES (?,?,?)",
                (torneo_id, numero, fecha),
            )
            nuevo_id = cur.lastrowid
    _clear_read_caches()
    return nuevo_id


@lru_cache(maxsize=256)
def listar_jornadas(torneo_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jornadas WHERE torneo_id=? ORDER BY numero", (torneo_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def marcar_jornada_completada(jornada_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE jornadas SET completada=1 WHERE id=?", (jornada_id,))
    _clear_read_caches()


def eliminar_jornada(jornada_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM jornadas WHERE id=?", (jornada_id,))
    _clear_read_caches()


# ──────────────────────── CANCHAS / ASIGNACIONES ────────────────

def crear_cancha_jornada(jornada_id: int, numero_cancha: int, horario: str = "") -> int:
    with get_conn() as conn:
        if USE_POSTGRES:
            row = conn.execute(
                "INSERT INTO canchas_jornada (jornada_id, numero_cancha, horario) VALUES (?,?,?) RETURNING id",
                (jornada_id, numero_cancha, horario),
            ).fetchone()
            nuevo_id = int(row["id"])
        else:
            cur = conn.execute(
                "INSERT INTO canchas_jornada (jornada_id, numero_cancha, horario) VALUES (?,?,?)",
                (jornada_id, numero_cancha, horario),
            )
            nuevo_id = cur.lastrowid
    _clear_read_caches()
    return nuevo_id


def crear_asignacion(cancha_jornada_id: int, jugador_id: int, posicion: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO asignaciones (cancha_jornada_id, jugador_id, posicion) VALUES (?,?,?)",
            (cancha_jornada_id, jugador_id, posicion),
        )
    _clear_read_caches()


def guardar_asignaciones_jornada(jornada_id: int, nuevas_asignaciones: list[dict]):
    """Reemplaza todas las asignaciones de una jornada.

    nuevas_asignaciones: lista de dicts con claves
      - cancha_jornada_id
      - jugador_id
      - posicion
    """
    with get_conn() as conn:
        canchas = conn.execute(
            "SELECT id FROM canchas_jornada WHERE jornada_id=?",
            (jornada_id,),
        ).fetchall()
        cancha_ids = {int(c["id"]) for c in canchas}
        if not cancha_ids:
            raise ValueError("La jornada no tiene canchas para reordenar.")

        actuales = conn.execute(
            """SELECT a.jugador_id, a.cancha_jornada_id, a.posicion
               FROM asignaciones a
               JOIN canchas_jornada cj ON cj.id = a.cancha_jornada_id
               WHERE cj.jornada_id=?""",
            (jornada_id,),
        ).fetchall()
        if not actuales:
            raise ValueError("La jornada no tiene jugadores asignados.")

        ids_actuales = [int(r["jugador_id"]) for r in actuales]
        ids_nuevos = [int(a.get("jugador_id", 0)) for a in nuevas_asignaciones]

        if len(ids_nuevos) != len(ids_actuales):
            raise ValueError("Debes asignar exactamente la misma cantidad de jugadores.")
        if set(ids_nuevos) != set(ids_actuales):
            raise ValueError("Debes usar exactamente los mismos jugadores de la jornada.")
        if len(set(ids_nuevos)) != len(ids_nuevos):
            raise ValueError("Hay jugadores repetidos en la reasignación.")

        pares = set()
        for a in nuevas_asignaciones:
            cancha_id = int(a.get("cancha_jornada_id", 0))
            posicion = int(a.get("posicion", 0))
            if cancha_id not in cancha_ids:
                raise ValueError("Se detectó una cancha inválida para esta jornada.")
            if posicion <= 0:
                raise ValueError("Las posiciones deben ser mayores a cero.")
            par = (cancha_id, posicion)
            if par in pares:
                raise ValueError("Hay posiciones duplicadas dentro de una misma cancha.")
            pares.add(par)

        for cancha_id in cancha_ids:
            conn.execute("DELETE FROM asignaciones WHERE cancha_jornada_id=?", (cancha_id,))

        for a in nuevas_asignaciones:
            conn.execute(
                "INSERT INTO asignaciones (cancha_jornada_id, jugador_id, posicion) VALUES (?,?,?)",
                (
                    int(a["cancha_jornada_id"]),
                    int(a["jugador_id"]),
                    int(a["posicion"]),
                ),
            )
    _clear_read_caches()


def actualizar_horario_cancha(cancha_jornada_id: int, horario: str):
    """Actualiza el horario de una cancha puntual dentro de una jornada."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT jornada_id, cancha_fisica FROM canchas_jornada WHERE id=?",
            (cancha_jornada_id,),
        ).fetchone()
        if not row:
            return
        jornada_id = int(row["jornada_id"])
        cancha_fisica = (row["cancha_fisica"] or "").strip()
        horario_nuevo = (horario or "").strip()

        if cancha_fisica:
            existente = conn.execute(
                """SELECT id FROM canchas_jornada
                   WHERE jornada_id=?
                     AND id<>?
                     AND TRIM(COALESCE(horario, '')) = ?
                     AND LOWER(TRIM(COALESCE(cancha_fisica, ''))) = LOWER(?)
                   LIMIT 1""",
                (jornada_id, cancha_jornada_id, horario_nuevo, cancha_fisica),
            ).fetchone()
            if existente:
                raise ValueError("Ese horario ya tiene asignada la misma cancha física.")

        conn.execute(
            "UPDATE canchas_jornada SET horario=? WHERE id=?",
            (horario_nuevo, cancha_jornada_id),
        )
    _clear_read_caches()


def actualizar_cancha_fisica_cancha_jornada(cancha_jornada_id: int, cancha_fisica: str):
    """Actualiza la cancha física validando que no se repita en el mismo horario/jornada."""
    nueva = (cancha_fisica or "").strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT jornada_id, horario FROM canchas_jornada WHERE id=?",
            (cancha_jornada_id,),
        ).fetchone()
        if not row:
            return

        jornada_id = int(row["jornada_id"])
        horario = (row["horario"] or "").strip()

        if nueva:
            existente = conn.execute(
                """SELECT id FROM canchas_jornada
                   WHERE jornada_id=?
                     AND id<>?
                     AND TRIM(COALESCE(horario, '')) = ?
                     AND LOWER(TRIM(COALESCE(cancha_fisica, ''))) = LOWER(?)
                   LIMIT 1""",
                (jornada_id, cancha_jornada_id, horario, nueva),
            ).fetchone()
            if existente:
                raise ValueError("Esa cancha física ya está asignada en el mismo horario.")

        conn.execute(
            "UPDATE canchas_jornada SET cancha_fisica=? WHERE id=?",
            (nueva, cancha_jornada_id),
        )
    _clear_read_caches()


@lru_cache(maxsize=256)
def obtener_canchas_jornada(jornada_id: int) -> list[dict]:
    """Devuelve canchas con sus jugadores ya incluidos."""
    with get_conn() as conn:
        canchas = conn.execute(
            "SELECT * FROM canchas_jornada WHERE jornada_id=? ORDER BY numero_cancha",
            (jornada_id,),
        ).fetchall()

        resultado = []
        for c in canchas:
            cid = c["id"]
            asigs = conn.execute(
                """SELECT a.posicion, j.id as jugador_id, j.nombre,
                          j.foto_original, j.foto_sin_fondo
                   FROM asignaciones a
                   JOIN jugadores j ON j.id = a.jugador_id
                   WHERE a.cancha_jornada_id = ?
                   ORDER BY a.posicion""",
                (cid,),
            ).fetchall()
            res = conn.execute(
                "SELECT * FROM resultados WHERE cancha_jornada_id=?", (cid,)
            ).fetchone()
            resultado.append(
                {
                    "id": cid,
                    "numero_cancha": c["numero_cancha"],
                    "horario": c["horario"],
                    "cancha_fisica": c["cancha_fisica"],
                    "jugadores": [dict(a) for a in asigs],
                    "resultado": dict(res) if res else None,
                }
            )
        return resultado


# ──────────────────────── RESULTADOS ────────────────────────────

def guardar_resultado(
    cancha_jornada_id: int,
    s1a: int, s1b: int,
    s2a: int, s2b: int,
    s3a: int, s3b: int,
):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO resultados
               (cancha_jornada_id, set1_a, set1_b, set2_a, set2_b, set3_a, set3_b)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(cancha_jornada_id) DO UPDATE SET
                 set1_a=excluded.set1_a, set1_b=excluded.set1_b,
                 set2_a=excluded.set2_a, set2_b=excluded.set2_b,
                 set3_a=excluded.set3_a, set3_b=excluded.set3_b""",
            (cancha_jornada_id, s1a, s1b, s2a, s2b, s3a, s3b),
        )
    _clear_read_caches()


def guardar_ausencias_jornada(jornada_id: int, penalizaciones: dict[int, int]):
    """Reemplaza ausencias registradas para una jornada.
    penalizaciones: {jugador_id: puntos_penalizacion}
    """
    with get_conn() as conn:
        conn.execute("DELETE FROM ausencias_jornada WHERE jornada_id=?", (jornada_id,))
        for jugador_id, penalizacion in penalizaciones.items():
            conn.execute(
                """INSERT INTO ausencias_jornada (jornada_id, jugador_id, penalizacion)
                   VALUES (?,?,?)""",
                (jornada_id, jugador_id, penalizacion),
            )
    _clear_read_caches()


@lru_cache(maxsize=256)
def obtener_ausencias_jornada(jornada_id: int) -> dict[int, int]:
    """Devuelve {jugador_id: penalizacion} para una jornada."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT jugador_id, penalizacion FROM ausencias_jornada WHERE jornada_id=?",
            (jornada_id,),
        ).fetchall()
        return {int(r["jugador_id"]): int(r["penalizacion"]) for r in rows}


def guardar_asistencia_jornada(jornada_id: int, jugador_ids_llegaron: set[int] | list[int]):
    """Reemplaza la asistencia de una jornada con los IDs de jugadores que llegaron."""
    ids = {int(jid) for jid in jugador_ids_llegaron}
    with get_conn() as conn:
        conn.execute("DELETE FROM asistencia_jornada WHERE jornada_id=?", (jornada_id,))
        for jugador_id in ids:
            conn.execute(
                """INSERT INTO asistencia_jornada (jornada_id, jugador_id, llego)
                   VALUES (?,?,1)""",
                (jornada_id, jugador_id),
            )
    _clear_read_caches()


@lru_cache(maxsize=256)
def obtener_asistencia_jornada(jornada_id: int) -> set[int]:
    """Devuelve el conjunto de jugador_id marcados como presentes para una jornada."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT jugador_id FROM asistencia_jornada WHERE jornada_id=? AND llego=1",
            (jornada_id,),
        ).fetchall()
        return {int(r["jugador_id"]) for r in rows}


# ──────────────────────── RANKING ───────────────────────────────

@lru_cache(maxsize=128)
def calcular_ranking(torneo_id: int, completada_only: bool = True) -> list[dict]:
    """
    Devuelve ranking general calculado desde la DB.
    Cada entrada: id, nombre, total_pts, pts_por_jornada, jornadas_jugadas, posicion.
    Si completada_only=False incluye también jornadas en curso (para TV en tiempo real).
    """
    from utils.liga_engine import calcular_puntos_jugador

    with get_conn() as conn:
        jugadores = conn.execute(
            "SELECT * FROM jugadores WHERE torneo_id=? ORDER BY nombre", (torneo_id,)
        ).fetchall()

        _jornada_filter = "AND completada=1" if completada_only else ""
        jornadas = conn.execute(
            f"SELECT * FROM jornadas WHERE torneo_id=? {_jornada_filter} ORDER BY numero",
            (torneo_id,),
        ).fetchall()

        ranking = []
        for j in jugadores:
            jid = j["id"]
            pts_por_jornada: dict[int, int] = {}   # solo puntos de juego
            pen_por_jornada: dict[int, int] = {}   # solo penalizaciones
            total_juego = 0
            total_pen   = 0

            for jornada in jornadas:
                penalizacion = conn.execute(
                    """SELECT penalizacion FROM ausencias_jornada
                       WHERE jornada_id=? AND jugador_id=?""",
                    (jornada["id"], jid),
                ).fetchone()

                if penalizacion:
                    pen = int(penalizacion["penalizacion"])
                    pen_por_jornada[jornada["numero"]] = pen
                    total_pen += pen

                # Buscar si este jugador tiene asignación en esta jornada
                row = conn.execute(
                    """SELECT a.posicion, r.set1_a, r.set1_b, r.set2_a, r.set2_b,
                              r.set3_a, r.set3_b
                       FROM asignaciones a
                       JOIN canchas_jornada cj ON cj.id = a.cancha_jornada_id
                       JOIN resultados r ON r.cancha_jornada_id = cj.id
                       WHERE cj.jornada_id=? AND a.jugador_id=?""",
                    (jornada["id"], jid),
                ).fetchone()

                if row:
                    pts = calcular_puntos_jugador(
                        posicion=row["posicion"],
                        s1a=row["set1_a"], s1b=row["set1_b"],
                        s2a=row["set2_a"], s2b=row["set2_b"],
                        s3a=row["set3_a"], s3b=row["set3_b"],
                    )
                    pts_por_jornada[jornada["numero"]] = pts
                    total_juego += pts

            ranking.append(
                {
                    "id": jid,
                    "nombre": j["nombre"],
                    "foto_original": j["foto_original"],
                    "foto_sin_fondo": j["foto_sin_fondo"],
                    "pts_por_jornada": pts_por_jornada,
                    "pen_por_jornada": pen_por_jornada,
                    "total_juego": total_juego,
                    "total_pen": total_pen,
                    "total_pts": total_juego + total_pen,
                    "jornadas_jugadas": len(pts_por_jornada),
                }
            )

    # Desempate de ranking:
    # - Jornada 1: orden de captura (id)
    # - Jornadas siguientes: posicion en ranking previo (equivale a acumulado hasta la jornada anterior)
    nums_j = sorted(int(j["numero"]) for j in jornadas)
    ultima_j = nums_j[-1] if nums_j else None

    def _prev_total(r: dict) -> int:
        if ultima_j is None:
            return 0
        prev_nums = [n for n in nums_j if n < ultima_j]
        s = 0
        for n in prev_nums:
            s += int(r["pts_por_jornada"].get(n, 0))
            s += int(r["pen_por_jornada"].get(n, 0))
        return s

    ranking.sort(
        key=lambda r: (
            -r["total_pts"],
            -_prev_total(r),
            int(r["id"]),
        )
    )
    for i, r in enumerate(ranking, 1):
        r["posicion"] = i

    return ranking
