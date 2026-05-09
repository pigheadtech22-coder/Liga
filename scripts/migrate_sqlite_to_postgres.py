import os
import sqlite3
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_PATH = BASE_DIR / "data" / "liga.db"

TABLE_ORDER = [
    "torneos",
    "horarios",
    "jugadores",
    "jornadas",
    "canchas_jornada",
    "asignaciones",
    "resultados",
    "ausencias_jornada",
    "asistencia_jornada",
]


def _pg_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("Falta DATABASE_URL en variables de entorno")
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _sqlite_rows(conn: sqlite3.Connection, table: str):
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(r) for r in rows]


def _truncate_target(conn):
    conn.execute(
        "TRUNCATE TABLE "
        "asistencia_jornada, ausencias_jornada, resultados, asignaciones, "
        "canchas_jornada, jornadas, jugadores, horarios, torneos "
        "RESTART IDENTITY CASCADE"
    )


def _insert_rows(conn, table: str, rows: list[dict]):
    if not rows:
        return

    cols = list(rows[0].keys())
    col_sql = ", ".join(cols)
    val_sql = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({val_sql})"

    values = [tuple(r[c] for c in cols) for r in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)



def _fix_sequences(conn):
    for table in TABLE_ORDER:
        conn.execute(
            """
            SELECT setval(
                pg_get_serial_sequence(%s, 'id'),
                COALESCE((SELECT MAX(id) FROM """ + table + """), 1),
                true
            )
            """,
            (table,),
        )



def main():
    if not SQLITE_PATH.exists():
        raise RuntimeError(f"No existe la base SQLite: {SQLITE_PATH}")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = psycopg.connect(_pg_url(), row_factory=dict_row)

    try:
        print("Leyendo datos de SQLite...")
        data = {table: _sqlite_rows(sqlite_conn, table) for table in TABLE_ORDER}

        print("Limpiando tablas en Supabase...")
        _truncate_target(pg_conn)

        print("Insertando datos en Supabase...")
        for table in TABLE_ORDER:
            _insert_rows(pg_conn, table, data[table])
            print(f"  - {table}: {len(data[table])} filas")

        _fix_sequences(pg_conn)
        pg_conn.commit()
        print("Migracion completada.")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
