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

/**
 * 🔑 **A aba do navegador é a do SITE** (16/10/2026, pedido do dono: "até a logo no título da
 * página está mudando"): o nome da casa no título e a logo cadastrada no ícone, lidos da
 * mesma rota que o site lê (`/publico/{loja}/casa`). Antes a aba dizia "Cardápio" com o ícone
 * do sistema, e quem saía da página inicial via a aba trocar de dono.
 * ⚠️ Sem a API (fora do ar, lenta), a página abre do mesmo jeito, com o padrão.
 */
const API = process.env.NEXT_PUBLIC_API ?? "http://127.0.0.1:9200";
type Casa = { casa?: string; logo_url?: string | null; marca?: { logo?: string | null; cor_principal?: string | null } };

async function casa(loja: string): Promise<Casa | null> {
  if (!/^\d+$/.test(loja)) return null;
  try {
    const r = await fetch(`${API}/publico/${loja}/casa`, { next: { revalidate: 300 }, signal: AbortSignal.timeout(3000) });
    return r.ok ? ((await r.json()) as Casa) : null;
  } catch {
    return null;
  }
}

const arquivo = (u: string) => (u.startsWith("http") ? u : API + u);

export async function generateMetadata({ params }: { params: Promise<{ loja: string }> }): Promise<Metadata> {
  const c = await casa((await params).loja);
  const logo = c?.marca?.logo ?? c?.logo_url ?? null;
  return {
    title: c?.casa ?? "Cardápio",
    description: "O cardápio da casa, prato a prato",
    robots: { index: false, follow: false },
    ...(logo ? { icons: { icon: arquivo(logo), apple: arquivo(logo) } } : {}),
  };
}

export async function generateViewport({ params }: { params: Promise<{ loja: string }> }): Promise<Viewport> {
  const c = await casa((await params).loja);
  return { themeColor: c?.marca?.cor_principal ?? "#3C4A3E", width: "device-width", initialScale: 1,
           viewportFit: "cover" };
}

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
