"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { TvSnapshot } from "@/lib/tv";

function formatDate(value: string | null) {
  if (!value) {
    return "Sin fecha";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function resultLabel(value: number | null) {
  return value === null ? "-" : String(value);
}

function pickCourtTag(index: number) {
  const labels = ["A", "B", "C", "D", "E", "F", "G", "H"];
  return labels[index] ?? String(index + 1);
}

type ScoreSet = {
  a: number | null;
  b: number | null;
  label: string;
};

export default function TvDisplayClient() {
  const searchParams = useSearchParams();
  const [snapshot, setSnapshot] = useState<TvSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    const tv = searchParams.get("tv");
    const torneoId = searchParams.get("torneo_id");
    const jornadaId = searchParams.get("jornada_id");

    if (tv) {
      params.set("tv", tv);
    }
    if (torneoId) {
      params.set("torneo_id", torneoId);
    }
    if (jornadaId) {
      params.set("jornada_id", jornadaId);
    }

    return params.toString();
  }, [searchParams]);

  useEffect(() => {
    let alive = true;

    async function loadSnapshot() {
      try {
        setLoading(true);
        const response = await fetch(`/api/tv${query ? `?${query}` : ""}`, {
          cache: "no-store"
        });

        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(payload?.error ?? "No se pudo cargar la pantalla TV");
        }

        const data = (await response.json()) as TvSnapshot;

        if (!alive) {
          return;
        }

        setSnapshot(data);
        setError(null);
        setLastUpdated(new Date(data.generatedAt).toLocaleTimeString("es-ES", { hour12: false }));
      } catch (loadError) {
        if (!alive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Error desconocido");
      } finally {
        if (alive) {
          setLoading(false);
        }
      }
    }

    void loadSnapshot();
    const interval = window.setInterval(loadSnapshot, Number(process.env.NEXT_PUBLIC_TV_POLL_INTERVAL_MS ?? 12000));

    return () => {
      alive = false;
      window.clearInterval(interval);
    };
  }, [query]);

  const title = snapshot?.torneo?.nombre ?? "Liga APJ Live";
  const jornadaLabel = snapshot?.jornada ? `Jornada ${snapshot.jornada.numero}` : "Sin jornada";
  const attendance = snapshot?.summary.presentesCount ?? 0;
  const courts = snapshot?.summary.canchasCount ?? 0;
  const players = snapshot?.summary.jugadoresCount ?? 0;

  return (
    <main className="app-shell">
      <div className="ambient one" />
      <div className="ambient two" />
      <div className="ambient three" />

      <div className="container">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark">APJ</div>
            <div>
              <div className="eyebrow">Pantalla en vivo</div>
              <h1 className="title">{title}</h1>
              <p className="subtitle">
                Visualización full-screen conectada al mismo Postgres de Supabase que usa la app de Streamlit.
              </p>
            </div>
          </div>

          <div className="status-pill">
            <span className="status-dot" />
            <span>{loading ? "Actualizando datos" : "Sincronizado con Supabase"}</span>
          </div>
        </header>

        <section className="stats">
          <article className="stat-card">
            <div className="stat-label">Jornada activa</div>
            <div className="stat-value">{jornadaLabel}</div>
            <div className="stat-note">{snapshot?.jornada ? formatDate(snapshot.jornada.fecha) : "Esperando datos"}</div>
          </article>

          <article className="stat-card">
            <div className="stat-label">Canchas</div>
            <div className="stat-value">{courts}</div>
            <div className="stat-note">Asignaciones cargadas en tiempo real</div>
          </article>

          <article className="stat-card">
            <div className="stat-label">Presentes</div>
            <div className="stat-value">{attendance}</div>
            <div className="stat-note">Marcados en asistencia para esta jornada</div>
          </article>

          <article className="stat-card">
            <div className="stat-label">Jugadores</div>
            <div className="stat-value">{players}</div>
            <div className="stat-note">Total de nombres montados en pantalla</div>
          </article>
        </section>

        <section className="hero">
          <article className="panel hero-copy">
            <div className="hero-kicker">
              <strong>Live board</strong>
              <span>refresh automático cada 12s</span>
            </div>
            <h2 className="hero-headline">
              Una pantalla TV más limpia, más rápida y lista para Vercel.
            </h2>
            <p className="hero-description">
              Este frontend reemplaza la parte visual del Streamlit para la TV: lee los datos desde Supabase,
              muestra canchas, jugadores y asistencia, y aplica una estética más moderna con tarjetas translúcidas,
              contraste alto y animaciones suaves.
            </p>

            <div className="mini-grid">
              <div className="mini-stat">
                <div className="mini-stat-label">Actualización</div>
                <div className="mini-stat-value">Auto</div>
                <div className="mini-stat-note">Polling sin recargar la página</div>
              </div>
              <div className="mini-stat">
                <div className="mini-stat-label">Conexión</div>
                <div className="mini-stat-value">DB</div>
                <div className="mini-stat-note">Mismo Postgres que la app actual</div>
              </div>
            </div>
          </article>

          <div className="side-stack">
            <aside className="message-card">
              <h3>Qué cubre esta primera fase</h3>
              <p>
                La prioridad es que el TV funcione bien antes de migrar toda la administración.
                Por eso este primer paso se limita a lectura y presentación.
              </p>
              <ul className="message-list">
                <li>Lee jornada y canchas desde la misma base de datos.</li>
                <li>Resalta presentes y estados de resultado.</li>
                <li>Está pensado para desplegarse en Vercel.</li>
              </ul>
            </aside>

            <aside className="message-card">
              <h3>Estado de sincronización</h3>
              <p>{error ? <span className="error-state">{error}</span> : "Los datos están en línea."}</p>
              <ul className="message-list">
                <li>Última lectura: {lastUpdated ?? "pendiente"}</li>
                <li>Jornadas disponibles: {snapshot?.jornadas.length ?? 0}</li>
                <li>Resultado activo: {snapshot?.summary.resultadosCount ?? 0} canchas</li>
              </ul>
            </aside>
          </div>
        </section>

        <section className="courts-header">
          <div>
            <h3 className="courts-title">Canchas en vivo</h3>
            <p className="courts-subtitle">
              La lectura se basa en la jornada seleccionada. Si no se pasa `tv=`, toma la más reciente.
            </p>
          </div>
          <div className="pill-row">
            <span className="pill highlight">{snapshot?.torneo?.nombre ?? "Sin torneo"}</span>
            <span className="pill hot">{snapshot?.jornada ? `J${snapshot.jornada.numero}` : "N/D"}</span>
          </div>
        </section>

        {!snapshot?.canchas.length ? (
          <section className="panel empty-state">
            <strong>No hay canchas para mostrar todavía.</strong>
            <div>Genera una jornada en Streamlit o abre un torneo con asignaciones cargadas.</div>
          </section>
        ) : (
          <section className="court-grid">
            {snapshot.canchas.map((court, index) => (
              <article className="court-card" key={court.id} style={{ ["--delay" as string]: `${index * 80}ms` }}>
                <div className="court-head">
                  <div className="court-name">
                    <strong>Cancha {pickCourtTag(index)}</strong>
                    <div className="pill-row">
                      <span className="pill">#{court.numero_cancha}</span>
                      {court.cancha_fisica ? <span className="pill highlight">{court.cancha_fisica}</span> : null}
                      {court.horario ? <span className="pill">{court.horario}</span> : null}
                    </div>
                  </div>
                  <span className="pill hot">{court.resultado ? "En juego" : "Pendiente"}</span>
                </div>

                <div className="player-list">
                  {court.jugadores.map((player) => {
                    const present = snapshot.asistenciaIds.includes(player.jugador_id);

                    return (
                      <div className="player" key={`${court.id}-${player.jugador_id}`}>
                        <div className="pos-badge">{player.posicion}</div>
                        <div className="player-main">
                          <div className="player-name">{player.nombre}</div>
                          <div className="player-meta">ID {player.jugador_id}</div>
                        </div>
                        <div className={`player-state ${present ? "present" : "absent"}`}>
                          {present ? "Presente" : "Ausente"}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {court.resultado ? (
                  <div className="scoreboard">
                    {([
                      { a: court.resultado.set1_a, b: court.resultado.set1_b, label: "Set 1" },
                      { a: court.resultado.set2_a, b: court.resultado.set2_b, label: "Set 2" },
                      { a: court.resultado.set3_a, b: court.resultado.set3_b, label: "Set 3" }
                    ] satisfies ScoreSet[]).map(({ a, b, label }) => (
                      <div className="score-chip" key={label}>
                        <strong>{resultLabel(a)} - {resultLabel(b)}</strong>
                        <span>{label}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </section>
        )}
      </div>
    </main>
  );
}