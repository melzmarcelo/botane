import type { Metadata, Viewport } from "next";
import { notFound } from "next/navigation";
import CardapioVivo from "@/components/cardapio-vivo/cardapio-vivo";

/**
 * O Cardápio Vivo (113): `/c/{loja}` (vitrine, balcão) e `/c/{loja}/{token}` (a mesa).
 *
 * 🔑 **A mesa é o TOKEN, não um número**: com `/c/1/5` qualquer pessoa em casa abriria
 * a mesa 5. O token se gera de novo no salão quando um QR impresso vaza.
 * ⚠️ Pública, fora do grupo `(app)`: sem login, sem menu, sem service worker.
 */

export const metadata: Metadata = {
  title: "Cardápio",
  description: "O cardápio da casa, prato a prato",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#000000", width: "device-width", initialScale: 1,
                                    viewportFit: "cover" };

export default async function Pagina({ params, searchParams }: {
  params: Promise<{ loja: string; mesa?: string[] }>;
  searchParams: Promise<{ cardapio?: string }>;
}) {
  const { loja, mesa } = await params;
  const { cardapio } = await searchParams;
  const id = Number(loja);
  if (!Number.isInteger(id) || id <= 0 || (mesa && mesa.length > 1)) notFound();
  // 🔑 Vários Cardápios Vivos (117): `?cardapio=catering` abre aquele; sem ele, o principal.
  // ⚠️ A mesa (token) abre SEMPRE o principal — o `?cardapio=` só vale sem mesa.
  const qual = !mesa?.[0] && cardapio && /^[a-z0-9-]{1,40}$/.test(cardapio) ? cardapio : null;
  return <CardapioVivo loja={id} token={mesa?.[0] ?? null} cardapio={qual} />;
}
