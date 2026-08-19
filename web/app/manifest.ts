import type { MetadataRoute } from "next";

/**
 * O que faz o navegador oferecer "instalar" e abrir sem barra de endereço.
 *
 * O ganho real não é estética: é o conferente contar a câmara fria com o
 * telefone na mão, em vez de anotar no papel e digitar depois — e os atalhos
 * abaixo caem direto na tela da contagem.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Botané Deli e Café",
    // Cabe embaixo do ícone na tela inicial sem virar "Botané De…".
    short_name: "Botané",
    description: "Fichas técnicas, estoque e CMV do Botané Deli e Café",
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
