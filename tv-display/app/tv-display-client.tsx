"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@supabase/supabase-js";
import type { TvSnapshot } from "@/lib/tv";

type Court = TvSnapshot["canchas"][number];

type PageGroup = {
  horario: string | null;
  courts: Court[];
};

function horarioSortValue(horario: string | null): number {
  const raw = String(horario ?? "").trim().toLowerCase();
  if (!raw) return Number.MAX_SAFE_INTEGER;

  const match = raw.match(/(\d{1,2})\s*[:h]\s*(\d{2})?/i);
  if (!match) return Number.MAX_SAFE_INTEGER;

  const hh = Number(match[1]);
  const mm = Number(match[2] ?? "0");
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return Number.MAX_SAFE_INTEGER;
  return hh * 60 + mm;
}

export default function TvDisplayClient() {
  const searchParams = useSearchParams();
  const [snapshot, setSnapshot] = useState<TvSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const mountedRef = useRef(true);
  const requestSeqRef = useRef(0);

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

  const themeFromQuery = useMemo(() => {
    const raw = (searchParams.get("theme") ?? "").toLowerCase();
    if (raw === "ocean" || raw === "sunset" || raw === "apj") {
      return raw;
    }
    return "";
  }, [searchParams]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadSnapshot = useCallback(
    async (showLoader = false) => {
      const seq = ++requestSeqRef.current;
      try {
        if (showLoader) {
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
        if (!mountedRef.current || seq !== requestSeqRef.current) return;
        setSnapshot(data);
        setError(null);
      } catch (err) {
        if (!mountedRef.current || seq !== requestSeqRef.current) return;
        setError(err instanceof Error ? err.message : "Error desconocido");
      } finally {
        if (showLoader && mountedRef.current && seq === requestSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [query]
  );

  useEffect(() => {
    void loadSnapshot(true);

    const interval = window.setInterval(() => {
      void loadSnapshot(false);
    }, Number(process.env.NEXT_PUBLIC_TV_POLL_INTERVAL_MS ?? 12000));

    return () => {
      window.clearInterval(interval);
    };
  }, [loadSnapshot]);

  const assetBaseUrl = (process.env.NEXT_PUBLIC_TV_ASSET_BASE_URL ?? "").trim();
  const loadingBrandUrl = (process.env.NEXT_PUBLIC_TV_LOADING_LOGO_URL ?? "").trim();
  const realtimeUrl = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").trim();
  const realtimeAnonKey = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "").trim();

  useEffect(() => {
    if (!realtimeUrl || !realtimeAnonKey) {
      return;
    }

    const supabase = createClient(realtimeUrl, realtimeAnonKey);
    let refreshTimer: number | undefined;

    const triggerRefresh = () => {
      if (refreshTimer !== undefined) {
        window.clearTimeout(refreshTimer);
      }
      refreshTimer = window.setTimeout(() => {
        void loadSnapshot(false);
      }, 250);
    };

    const channel = supabase.channel(`tv-live-${query || "default"}`);
    const watchedTables = [
      "torneos",
      "jornadas",
      "canchas_jornada",
      "asignaciones",
      "resultados",
      "asistencia_jornada",
      "jugadores"
    ];

    watchedTables.forEach((table) => {
      channel.on(
        "postgres_changes",
        { event: "*", schema: "public", table },
        () => triggerRefresh()
      );
    });

    channel.subscribe();

    return () => {
      if (refreshTimer !== undefined) {
        window.clearTimeout(refreshTimer);
      }
      void supabase.removeChannel(channel);
    };
  }, [loadSnapshot, query, realtimeAnonKey, realtimeUrl]);

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

  function LoadingBrand() {
    if (!loadingBrandUrl) {
      return <div className="tv-brand-mark">🏓</div>;
    }
    return (
      <img
        src={loadingBrandUrl}
        alt="Marca"
        className="tv-loading-brand"
        onError={(e) => {
          (e.target as HTMLImageElement).style.display = "none";
        }}
      />
    );
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

    const sortedGroups = Array.from(byHorario.entries()).sort((left, right) => {
      const leftMinutes = horarioSortValue(left[0]);
      const rightMinutes = horarioSortValue(right[0]);
      if (leftMinutes !== rightMinutes) {
        return leftMinutes - rightMinutes;
      }
      return String(left[0] ?? "").localeCompare(String(right[0] ?? ""), "es");
    });

    const result: PageGroup[] = [];
    const pageSize = 4;
    for (const [horario, courts] of sortedGroups) {
      const orderedCourts = [...courts].sort((a, b) => a.numero_cancha - b.numero_cancha);
      for (let i = 0; i < orderedCourts.length; i += pageSize) {
        result.push({
          horario,
          courts: orderedCourts.slice(i, i + pageSize)
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

  const selectedTheme = useMemo(() => {
    const dbTheme = String(snapshot?.torneo?.tv_theme ?? "").toLowerCase();
    if (dbTheme === "ocean" || dbTheme === "sunset" || dbTheme === "apj") {
      return dbTheme;
    }
    if (themeFromQuery) {
      return themeFromQuery;
    }
    return "apj";
  }, [snapshot?.torneo?.tv_theme, themeFromQuery]);

  if (loading || !snapshot) {
    return (
      <main className={`tv-fullscreen theme-${selectedTheme}`}>
        <div className="tv-loading">
          <LoadingBrand />
          <div className="tv-loading-text">{loading ? "Cargando..." : "Sin datos"}</div>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className={`tv-fullscreen theme-${selectedTheme}`}>
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
      <main className={`tv-fullscreen theme-${selectedTheme}`}>
        <div className="tv-loading">
          <LoadingBrand />
          <div className="tv-loading-text">No hay canchas</div>
        </div>
      </main>
    );
  }

  const presentSet = new Set(snapshot.asistenciaIds);

  return (
    <main className={`tv-fullscreen theme-${selectedTheme}`}>
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
  function courtVirtualLabel(numero: number): string {
    let n = Number(numero);
    if (!Number.isFinite(n) || n <= 0) {
      return String(numero);
    }

    let letters = "";
    while (n > 0) {
      n -= 1;
      letters = String.fromCharCode(65 + (n % 26)) + letters;
      n = Math.floor(n / 26);
    }
    return letters;
  }

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
          <strong>Cancha {courtVirtualLabel(court.numero_cancha)}</strong>
          {court.cancha_fisica && (
            <span className="tv-physical">{court.cancha_fisica}</span>
          )}
        </div>
        {court.resultado ? (
          <span className="tv-badge-done">Finalizado</span>
        ) : (
          <span className="tv-badge-pending">Pendiente</span>
        )}
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
