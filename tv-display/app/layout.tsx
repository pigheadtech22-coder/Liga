import type { Metadata } from "next";
import { Bebas_Neue, Space_Grotesk } from "next/font/google";
import "./globals.css";

const bodyFont = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-body"
});

const titleFont = Bebas_Neue({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-title"
});

export const metadata: Metadata = {
  title: "Liga APJ TV",
  description: "Pantalla TV moderna para la liga APJ con datos en tiempo real desde Supabase."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className={`${bodyFont.variable} ${titleFont.variable}`}>
        {children}
      </body>
    </html>
  );
}