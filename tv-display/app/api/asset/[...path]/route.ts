import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs";
import * as path from "path";

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  try {
    // Construir la ruta desde el parámetro
    const filePath = Array.isArray(params.path) ? params.path.join("/") : params.path;

    // Validar que no haya traversal attacks (solo permitir assets/)
    if (!filePath.startsWith("assets/") && filePath.includes("..")) {
      return new NextResponse("Forbidden", { status: 403 });
    }

    // Ruta al directorio parent (donde está app.py)
    const parentDir = path.join(process.cwd(), "..");
    const fullPath = path.join(parentDir, filePath);

    // Validar que el archivo existe
    if (!fs.existsSync(fullPath)) {
      return new NextResponse("Not Found", { status: 404 });
    }

    // Leer el archivo
    const fileContent = fs.readFileSync(fullPath);

    // Determinar el content-type según la extensión
    const ext = path.extname(fullPath).toLowerCase();
    const contentType = {
      ".png": "image/png",
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".gif": "image/gif",
      ".webp": "image/webp",
      ".svg": "image/svg+xml"
    }[ext] || "application/octet-stream";

    return new NextResponse(fileContent, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=3600, immutable"
      }
    });
  } catch (error) {
    console.error("Asset serving error:", error);
    return new NextResponse("Internal Server Error", { status: 500 });
  }
}
