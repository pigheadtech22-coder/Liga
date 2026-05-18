import { NextResponse } from "next/server";
import { fetchTvSnapshot, parseTvToken } from "@/lib/tv";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const token = parseTvToken(url.searchParams.get("tv"));
    const torneoId = Number(url.searchParams.get("torneo_id") ?? token.torneoId ?? 0) || undefined;
    const jornadaId = Number(url.searchParams.get("jornada_id") ?? token.jornadaId ?? 0) || undefined;

    const snapshot = await fetchTvSnapshot({ torneoId, jornadaId });
    return NextResponse.json(snapshot, {
      headers: {
        "Cache-Control": "no-store"
      }
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "No se pudo cargar el TV snapshot";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}