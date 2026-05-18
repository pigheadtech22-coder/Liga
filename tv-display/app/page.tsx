import { Suspense } from "react";
import TvDisplayClient from "./tv-display-client";

function LoadingState() {
  return (
    <main className="app-shell">
      <div className="container">
        <section className="panel empty-state">
          <strong>Cargando pantalla TV...</strong>
          <div>Preparando la lectura desde Supabase.</div>
        </section>
      </div>
    </main>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <TvDisplayClient />
    </Suspense>
  );
}