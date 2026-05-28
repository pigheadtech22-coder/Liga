import { Pool } from "pg";

export type TvRequest = {
  torneoId?: number;
  jornadaId?: number;
};

export type TvPlayer = {
  jugador_id: number;
  nombre: string;
  posicion: number;
  foto_original: string | null;
  foto_sin_fondo: string | null;
};

export type TvCourt = {
  id: number;
  numero_cancha: number;
  horario: string | null;
  cancha_fisica: string | null;
  jugadores: TvPlayer[];
  resultado: {
    set1_a: number | null;
    set1_b: number | null;
    set2_a: number | null;
    set2_b: number | null;
    set3_a: number | null;
    set3_b: number | null;
  } | null;
};

export type TvSnapshot = {
  torneo: {
    id: number;
    nombre: string;
    descripcion: string | null;
    tv_header_logo_path: string | null;
    logo_left_path: string | null;
    logo_right_path: string | null;
    sponsor_logos: string[];
  } | null;
  jornada: {
    id: number;
    numero: number;
    fecha: string | null;
    completada: boolean;
  } | null;
  jornadas: Array<{
    id: number;
    numero: number;
    fecha: string | null;
    completada: boolean;
  }>;
  canchas: TvCourt[];
  asistenciaIds: number[];
  summary: {
    canchasCount: number;
    jugadoresCount: number;
    presentesCount: number;
    resultadosCount: number;
  };
  generatedAt: string;
};

const globalForPg = globalThis as typeof globalThis & {
  pgPool?: Pool;
};

function getPool() {
  if (!process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL no está configurada");
  }

  if (!globalForPg.pgPool) {
    globalForPg.pgPool = new Pool({
      connectionString: process.env.DATABASE_URL,
      ssl: { rejectUnauthorized: false },
      max: 1,
      idleTimeoutMillis: 30_000
    });
  }

  return globalForPg.pgPool;
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseBoolean(value: unknown): boolean {
  return value === true || value === 1 || value === "1" || value === "true";
}

export function parseTvToken(token: string | null): { torneoId: number | null; jornadaId: number | null } {
  const raw = String(token ?? "").trim();
  if (!raw) {
    return { torneoId: null, jornadaId: null };
  }

  const parts = raw.split("-", 2);
  if (parts.length !== 2) {
    return { torneoId: null, jornadaId: null };
  }

  const torneoId = toNumber(parts[0]);
  const jornadaId = toNumber(parts[1]);

  if (!torneoId || !jornadaId || torneoId <= 0 || jornadaId <= 0) {
    return { torneoId: null, jornadaId: null };
  }

  return { torneoId, jornadaId };
}

export async function fetchTvSnapshot(input: TvRequest = {}): Promise<TvSnapshot> {
  const pool = getPool();

  const torneoId = input.torneoId ?? null;
  const jornadaId = input.jornadaId ?? null;

  let torneoRow;
  try {
    torneoRow = torneoId
      ? await pool.query(
          "SELECT id, nombre, descripcion, tv_header_logo_path, logo_left_path, logo_right_path, sponsor_logo_1_path, sponsor_logo_2_path, sponsor_logo_3_path, sponsor_logo_4_path, sponsor_logo_5_path, sponsor_logo_6_path, sponsor_logo_7_path, sponsor_logo_8_path FROM torneos WHERE id=$1 LIMIT 1",
          [torneoId]
        )
      : await pool.query(
          "SELECT id, nombre, descripcion, tv_header_logo_path, logo_left_path, logo_right_path, sponsor_logo_1_path, sponsor_logo_2_path, sponsor_logo_3_path, sponsor_logo_4_path, sponsor_logo_5_path, sponsor_logo_6_path, sponsor_logo_7_path, sponsor_logo_8_path FROM torneos ORDER BY id DESC LIMIT 1"
        );
  } catch (error) {
    const isMissingDescripcionColumn =
      typeof error === "object" &&
      error !== null &&
      "code" in error &&
      (error as { code?: string }).code === "42703";

    if (!isMissingDescripcionColumn) {
      throw error;
    }

    torneoRow = torneoId
      ? await pool.query(
          "SELECT id, nombre, NULL::text AS descripcion, tv_header_logo_path, logo_left_path, logo_right_path, sponsor_logo_1_path, sponsor_logo_2_path, sponsor_logo_3_path, sponsor_logo_4_path, sponsor_logo_5_path, sponsor_logo_6_path, sponsor_logo_7_path, sponsor_logo_8_path FROM torneos WHERE id=$1 LIMIT 1",
          [torneoId]
        )
      : await pool.query(
          "SELECT id, nombre, NULL::text AS descripcion, tv_header_logo_path, logo_left_path, logo_right_path, sponsor_logo_1_path, sponsor_logo_2_path, sponsor_logo_3_path, sponsor_logo_4_path, sponsor_logo_5_path, sponsor_logo_6_path, sponsor_logo_7_path, sponsor_logo_8_path FROM torneos ORDER BY id DESC LIMIT 1"
        );
  }

  const sponsorLogos: string[] = [];
  for (let i = 1; i <= 8; i++) {
    const logoPath = torneoRow.rows[0]?.[`sponsor_logo_${i}_path`];
    if (logoPath) {
      sponsorLogos.push(String(logoPath));
    }
  }

  const torneo = torneoRow.rows[0]
    ? {
        id: Number(torneoRow.rows[0].id),
        nombre: String(torneoRow.rows[0].nombre ?? "Torneo"),
        descripcion: torneoRow.rows[0].descripcion ? String(torneoRow.rows[0].descripcion) : null,
        tv_header_logo_path: torneoRow.rows[0].tv_header_logo_path ? String(torneoRow.rows[0].tv_header_logo_path) : null,
        logo_left_path: torneoRow.rows[0].logo_left_path ? String(torneoRow.rows[0].logo_left_path) : null,
        logo_right_path: torneoRow.rows[0].logo_right_path ? String(torneoRow.rows[0].logo_right_path) : null,
        sponsor_logos: sponsorLogos
      }
    : null;

  if (!torneo) {
    return {
      torneo: null,
      jornada: null,
      jornadas: [],
      canchas: [],
      asistenciaIds: [],
      summary: {
        canchasCount: 0,
        jugadoresCount: 0,
        presentesCount: 0,
        resultadosCount: 0
      },
      generatedAt: new Date().toISOString()
    };
  }

  const jornadasResult = await pool.query(
    "SELECT id, numero, fecha, completada FROM jornadas WHERE torneo_id=$1 ORDER BY numero",
    [torneo.id]
  );

  const jornadas = jornadasResult.rows.map((row) => ({
    id: Number(row.id),
    numero: Number(row.numero),
    fecha: row.fecha ? String(row.fecha) : null,
    completada: parseBoolean(row.completada)
  }));

  const selectedJornada = (() => {
    if (jornadaId) {
      return jornadas.find((row) => row.id === jornadaId) ?? null;
    }

    return jornadas.length ? jornadas[jornadas.length - 1] : null;
  })();

  if (!selectedJornada) {
    return {
      torneo,
      jornada: null,
      jornadas,
      canchas: [],
      asistenciaIds: [],
      summary: {
        canchasCount: 0,
        jugadoresCount: 0,
        presentesCount: 0,
        resultadosCount: 0
      },
      generatedAt: new Date().toISOString()
    };
  }

  const canchasResult = await pool.query(
    `SELECT
       cj.id,
       cj.numero_cancha,
       cj.horario,
       cj.cancha_fisica,
       r.set1_a, r.set1_b, r.set2_a, r.set2_b, r.set3_a, r.set3_b,
       a.posicion,
       j.id AS jugador_id,
       j.nombre,
       j.foto_original,
       j.foto_sin_fondo
     FROM canchas_jornada cj
     LEFT JOIN asignaciones a ON a.cancha_jornada_id = cj.id
     LEFT JOIN jugadores j ON j.id = a.jugador_id
     LEFT JOIN resultados r ON r.cancha_jornada_id = cj.id
     WHERE cj.jornada_id = $1
     ORDER BY cj.numero_cancha, a.posicion`,
    [selectedJornada.id]
  );

  const asistenciaResult = await pool.query(
    "SELECT jugador_id FROM asistencia_jornada WHERE jornada_id=$1 AND llego=1",
    [selectedJornada.id]
  );

  const asistenciaIds = asistenciaResult.rows.map((row) => Number(row.jugador_id));
  const asistenciaSet = new Set(asistenciaIds);

  const courtsMap = new Map<number, TvCourt>();

  for (const row of canchasResult.rows) {
    const courtId = Number(row.id);
    if (!courtsMap.has(courtId)) {
      courtsMap.set(courtId, {
        id: courtId,
        numero_cancha: Number(row.numero_cancha),
        horario: row.horario ? String(row.horario) : null,
        cancha_fisica: row.cancha_fisica ? String(row.cancha_fisica) : null,
        jugadores: [],
        resultado: row.set1_a === null && row.set1_b === null && row.set2_a === null && row.set2_b === null && row.set3_a === null && row.set3_b === null
          ? null
          : {
              set1_a: row.set1_a === null ? null : Number(row.set1_a),
              set1_b: row.set1_b === null ? null : Number(row.set1_b),
              set2_a: row.set2_a === null ? null : Number(row.set2_a),
              set2_b: row.set2_b === null ? null : Number(row.set2_b),
              set3_a: row.set3_a === null ? null : Number(row.set3_a),
              set3_b: row.set3_b === null ? null : Number(row.set3_b)
            }
      });
    }

    const jugadorId = row.jugador_id === null ? null : Number(row.jugador_id);
    if (jugadorId) {
      courtsMap.get(courtId)?.jugadores.push({
        jugador_id: jugadorId,
        nombre: String(row.nombre ?? "Sin nombre"),
        posicion: Number(row.posicion ?? 0),
        foto_original: row.foto_original ? String(row.foto_original) : null,
        foto_sin_fondo: row.foto_sin_fondo ? String(row.foto_sin_fondo) : null
      });
    }
  }

  const canchas = Array.from(courtsMap.values()).sort((left, right) => left.numero_cancha - right.numero_cancha);
  const jugadoresCount = canchas.reduce((accumulator, court) => accumulator + court.jugadores.length, 0);
  const resultadosCount = canchas.filter((court) => Boolean(court.resultado)).length;

  return {
    torneo,
    jornada: selectedJornada,
    jornadas,
    canchas,
    asistenciaIds,
    summary: {
      canchasCount: canchas.length,
      jugadoresCount,
      presentesCount: asistenciaSet.size,
      resultadosCount
    },
    generatedAt: new Date().toISOString()
  };
}