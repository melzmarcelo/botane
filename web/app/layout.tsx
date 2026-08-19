import type { Metadata, Viewport } from "next";
import "./globals.css";
import { RegistroPWA } from "@/components/pwa";

export const metadata: Metadata = {
  title: "Botané Deli e Café",
  description: "Gestão de custo, fichas técnicas e CMV",
  applicationName: "Botané Deli e Café",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [{ url: "/favicon-32.png", sizes: "32x32", type: "image/png" }],
    apple: "/apple-touch-icon.png",
  },
  appleWebApp: { capable: true, title: "Botané", statusBarStyle: "default" },
  other: {
    // O Next 16 emite só o nome padronizado `mobile-web-app-capable`, que o
    // Safari do iPhone só entende do iOS 17.4 em diante. Sem o nome antigo,
    // aparelho mais velho instala o ícone e abre uma aba do Safari com barra de
    // endereço, em vez da tela cheia.
    "apple-mobile-web-app-capable": "yes",
  },
};

export const viewport: Viewport = {
  themeColor: "#2c6a4a",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,600;12..96,700;12..96,800&family=Newsreader:opsz,wght@6..72,400;6..72,500&family=IBM+Plex+Mono:wght@400;500&display=swap"
        />
      </head>
      <body>
        {children}
        <RegistroPWA />
      </body>
    </html>
  );
}
