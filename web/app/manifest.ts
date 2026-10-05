import type { MetadataRoute } from "next";

/**
 * O que faz o navegador oferecer "instalar" e abrir sem barra de endereço.
 *
 * O ganho real não é estética: é o conferente contar a câmara fria com o
 * telefone na mão, em vez de anotar no papel e digitar depois — e os atalhos
 * abaixo caem direto na tela da contagem.
 */
// 🔑 **O nome do aplicativo instalado é o da CASA, do cadastro da empresa**
// (05/10/2026). Por isso o manifesto é montado a cada pedido, e não na
// compilação: o mesmo código serve a mais de uma empresa.
export const dynamic = "force-dynamic";

const API = process.env.NEXT_PUBLIC_API ?? "http://127.0.0.1:9200";
const GENERICO = "Sistema de gestão";

/** O nome da casa, ou nulo. ⚠️ Com prazo curto e sem estourar: manifesto que
    demora ou falha tira o "instalar" do navegador, e o nome genérico é melhor
    que nenhum manifesto. */
async function nomeDaCasa(): Promise<string | null> {
  try {
    const r = await fetch(`${API}/publico/marca`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    if (!r.ok) return null;
    return ((await r.json()) as { nome: string | null }).nome;
  } catch {
    return null;
  }
}

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const casa = await nomeDaCasa();
  return {
    name: casa ?? GENERICO,
    // Cabe embaixo do ícone na tela inicial sem ser cortado: a primeira
    // palavra do nome da casa.
    short_name: casa ? casa.trim().split(/\s+/)[0].slice(0, 12) : "Gestão",
    description: casa ? `${GENERICO} — ${casa}` : GENERICO,
    lang: "pt-BR",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f3f5ef",
    theme_color: "#2c6a4a",
    categories: ["business", "food", "productivity"],
    icons: [
      { src: "/icone-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icone-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      // O Android recorta o ícone na forma do aparelho; o "maskable" é o
      // desenho já encolhido para sobreviver ao corte.
      { src: "/icone-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      {
        name: "Contagem de inventário",
        short_name: "Inventário",
        description: "Abrir a contagem do estoque",
        url: "/inventario",
      },
      {
        name: "Pontos de atenção",
        short_name: "Alertas",
        description: "Vencimentos e produtos abaixo do mínimo",
        url: "/alertas",
      },
      {
        name: "Saldos de estoque",
        short_name: "Estoque",
        description: "Consultar saldo e custo médio",
        url: "/estoque",
      },
    ],
  };
}
