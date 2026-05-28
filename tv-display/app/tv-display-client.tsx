"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { TvSnapshot } from "@/lib/tv";

type Court = TvSnapshot["canchas"][number];

type PageGroup = {
  horario: string | null;
  courts: Court[];
};

export default function TvDisplayClient() {
  const searchParams = useSearchParams();
  const [snapshot, setSnapshot] = useState<TvSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    const tv = searchParams.get("tv");
    const torneoId = searchParams.get("torneo_id");
    const jornadaId = searchParams.get("jornada_id");
    if (tv) params.set("tv", tv);
    if (torneoId) params.set("torneo_id", torneoId);
    if (jornadaId) params.set("jornada_id", jornadaId);
    return params.toString();
  }, [searchParams]);

  useEffect(() => {
    let alive = true;
    let firstRun = true;

    async function loadSnapshot() {
      try {
        if (firstRun) {
          setLoading(true);
        }
        const response = await fetch(`/api/tv${query ? `?${query}` : ""}`, {
          cache: "no-store"
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(payload?.error ?? "Error cargando TV");
        }
        const data = (await response.json()) as TvSnapshot;
        if (!alive) return;
        setSnapshot(data);
        setError(null);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Error desconocido");
      } finally {
        if (alive && firstRun) {
          setLoading(false);
          firstRun = false;
        }
      }
    }
    void loadSnapshot();
    const interval = window.setInterval(
      loadSnapshot,
      Number(process.env.NEXT_PUBLIC_TV_POLL_INTERVAL_MS ?? 12000)
    );
    return () => {
      alive = false;
      window.clearInterval(interval);
    };
  }, [query]);

  const assetBaseUrl = (process.env.NEXT_PUBLIC_TV_ASSET_BASE_URL ?? "").trim();

  function toAssetUrl(rawPath: string | null | undefined): string | null {
    if (!rawPath) return null;

    const clean = rawPath.trim().replace(/\\/g, "/");
    if (!clean) return null;

    if (/^https?:\/\//i.test(clean)) {
      return clean;
    }

    if (assetBaseUrl) {
      const base = assetBaseUrl.replace(/\/+$/, "");
      const rel = clean.replace(/^\/+/, "");
      return `${base}/${rel}`;
    }

    const rel = clean.replace(/^\/+/, "");
    return `/api/asset/${rel}`;
  }

  // Agrupar por horario, máx 4 canchas por pantalla
  const pages: PageGroup[] = useMemo(() => {
    if (!snapshot?.canchas.length) return [];
    const byHorario = new Map<string | null, Court[]>();
    snapshot.canchas.forEach((court) => {
      const key = court.horario || "Sin horario";
      if (!byHorario.has(key)) byHorario.set(key, []);
      byHorario.get(key)!.push(court);
    });
    const result: PageGroup[] = [];
    const pageSize = 4;
    for (const [horario, courts] of byHorario.entries()) {
      for (let i = 0; i < courts.length; i += pageSize) {
        result.push({
          horario,
          courts: courts.slice(i, i + pageSize)
        });
      }
    }
    return result;
  }, [snapshot?.canchas]);

  // Carrusel automático cada 15s
  useEffect(() => {
    if (pages.length <= 1) return;
    const timer = setInterval(() => {
      setPageIndex((prev) => (prev + 1) % pages.length);
    }, 15000);
    return () => clearInterval(timer);
  }, [pages.length]);

  useEffect(() => {
    setPageIndex(0);
  }, [query]);

  const footerLogos = useMemo(() => {
    return [
      ...(snapshot?.torneo?.sponsor_logos ?? []),
      snapshot?.torneo?.logo_left_path ?? null,
      snapshot?.torneo?.logo_right_path ?? null
    ]
      .filter((value): value is string => Boolean(value && value.trim()))
      .map((value) => value.trim());
  }, [snapshot?.torneo]);

  if (loading || !snapshot) {
    return (
      <main className="tv-fullscreen">
        <div className="tv-loading">
          <div className="tv-brand-mark">🏓</div>
          <div className="tv-loading-text">{loading ? "Cargando..." : "Sin datos"}</div>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="tv-fullscreen">
        <div className="tv-loading tv-error">
          <div className="tv-brand-mark">⚠️</div>
          <div className="tv-loading-text">{error}</div>
        </div>
      </main>
    );
  }

  const currentPage = pages[pageIndex];
  if (!currentPage) {
    return (
      <main className="tv-fullscreen">
        <div className="tv-loading">
          <div className="tv-brand-mark">📺</div>
          <div className="tv-loading-text">No hay canchas</div>
        </div>
      </main>
    );
  }

  const presentSet = new Set(snapshot.asistenciaIds);

  return (
    <main className="tv-fullscreen">
      <header className="tv-header">
        {snapshot.torneo?.tv_header_logo_path && snapshot.torneo.tv_header_logo_path.trim() ? (
          <div className="tv-header-logo">
            <img
              src={toAssetUrl(snapshot.torneo.tv_header_logo_path) ?? ""}
              alt="Torneo Logo"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          </div>
        ) : snapshot.torneo?.logo_left_path || snapshot.torneo?.logo_right_path ? (
          <div className="tv-header-fallback">
            <div className="tv-header-left">
              {snapshot.torneo.logo_left_path && (
                <img
                  src={toAssetUrl(snapshot.torneo.logo_left_path) ?? ""}
                  alt="Logo Left"
                  className="tv-logo-side"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              )}
            </div>
            <div className="tv-header-center-text">
              <h1>{snapshot.torneo?.nombre || "Liga APJ"}</h1>
            </div>
            <div className="tv-header-right">
              {snapshot.torneo?.logo_right_path && (
                <img
                  src={toAssetUrl(snapshot.torneo.logo_right_path) ?? ""}
                  alt="Logo Right"
                  className="tv-logo-side"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              )}
            </div>
          </div>
        ) : (
          <div className="tv-header-left">
            <div className="tv-brand-mark">🏓</div>
            <div className="tv-header-info">
              <h1>{snapshot.torneo?.nombre || "Liga APJ"}</h1>
              <p>Jornada {snapshot.jornada?.numero || "—"}</p>
            </div>
          </div>
        )}
        
        <div className="tv-header-center">
          <p className="tv-horario">🕒 {currentPage.horario}</p>
        </div>
        
        {pages.length > 1 && (
          <div className="tv-page-counter">
            {pageIndex + 1}/{pages.length}
          </div>
        )}
      </header>

      <section className="tv-content">
        <div className="tv-grid">
          {currentPage.courts.map((court, idx) => (
            <CourtCard
              key={court.id}
              court={court}
              index={idx}
              presentSet={presentSet}
            />
          ))}
        </div>
      </section>

      <footer className="tv-footer">
        {footerLogos.length ? (
          <div className="tv-sponsors-ribbon">
            <div className="tv-sponsors">
              {footerLogos.map((logoPath, idx) => (
              <div key={idx} className="tv-sponsor-item">
                <img
                  src={toAssetUrl(logoPath) ?? ""}
                  alt={`Sponsor ${idx + 1}`}
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="tv-stats">
            <span>🏛️ {snapshot.summary.canchasCount} canchas</span>
            <span>👥 {snapshot.summary.presentesCount}/{snapshot.summary.jugadoresCount}</span>
            <span>🎾 {snapshot.summary.resultadosCount} resultados</span>
          </div>
        )}
      </footer>
    </main>
  );
}

function CourtCard({
  court,
  index,
  presentSet
}: {
  court: Court;
  index: number;
  presentSet: Set<number>;
}) {
  const s1a = court.resultado?.set1_a ?? 0;
  const s1b = court.resultado?.set1_b ?? 0;
  const s2a = court.resultado?.set2_a ?? 0;
  const s2b = court.resultado?.set2_b ?? 0;
  const s3a = court.resultado?.set3_a ?? 0;
  const s3b = court.resultado?.set3_b ?? 0;

  function puntosByPosicion(posicion: number): number {
    // Misma regla de Streamlit (utils/liga_engine.py):
    // Set1: P1+P2 vs P3+P4
    // Set2: P1+P3 vs P2+P4
    // Set3: P1+P4 vs P2+P3
    if (posicion === 1) return (s1a - s1b) + (s2a - s2b) + (s3a - s3b);
    if (posicion === 2) return (s1a - s1b) + (s2b - s2a) + (s3b - s3a);
    if (posicion === 3) return (s1b - s1a) + (s2a - s2b) + (s3b - s3a);
    if (posicion === 4) return (s1b - s1a) + (s2b - s2a) + (s3a - s3b);
    return 0;
  }

  return (
    <article
      className="tv-court"
      style={{ "--delay": `${index * 100}ms` } as React.CSSProperties}
    >
      <div className="tv-court-head">
        <div>
          <strong>Cancha {String.fromCharCode(65 + index)}</strong>
          {court.cancha_fisica && (
            <span className="tv-physical">{court.cancha_fisica}</span>
          )}
        </div>
        {court.resultado && <span className="tv-badge-live">En juego</span>}
      </div>

      <div className="tv-players">
        {court.jugadores.map((p) => {
          const present = presentSet.has(p.jugador_id);
          const playerPoints = puntosByPosicion(p.posicion);
          return (
            <div
              key={`${court.id}-${p.jugador_id}`}
              className={`tv-player ${present ? "present" : "absent"}`}
            >
              <span className="tv-pos">{p.posicion}</span>
              <span className="tv-name-wrap">
                <span className="tv-name">{p.nombre}</span>
                {court.resultado ? (
                  <span className="tv-player-games">{playerPoints > 0 ? `+${playerPoints}` : String(playerPoints)}</span>
                ) : null}
              </span>
            </div>
          );
        })}
      </div>

      {court.resultado && (
        <div className="tv-scores">
          {[
            { a: court.resultado.set1_a, b: court.resultado.set1_b, label: "S1" },
            { a: court.resultado.set2_a, b: court.resultado.set2_b, label: "S2" },
            { a: court.resultado.set3_a, b: court.resultado.set3_b, label: "S3" }
          ].map(({ a, b, label }) => (
            <div key={label} className="tv-score">
              <span>{a ?? "-"}</span>
              <span>{b ?? "-"}</span>
              <small>{label}</small>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
