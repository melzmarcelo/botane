/**
 * Os desenhos do menu — um traçado por tela.
 *
 * 🔑 **Nasceram com o menu novo (15/09/2026).** O menu era texto puro em caixa
 * alta de 11px, que lê como legenda de seção e não como navegação: para achar
 * "Inventário" era preciso LER a lista inteira. Ícone é reconhecimento, e é o
 * que faz uma lateral parecer contemporânea sem trocar cor nenhuma.
 *
 * ⚠️ **Nada de biblioteca de ícones.** Uma fonte inteira (ou um pacote de
 * milhares de SVG) para vinte e cinco desenhos é peso de download que este
 * sistema não tem por que pagar — e prender o visual do menu a uma dependência
 * externa que envelhece por conta própria. São caminhos de 18×18, traço de 1,5,
 * `currentColor`: herdam a cor do estado (cinza, erva quando ativo) sozinhos.
 */
export const ICONES = {
  casa: "M3 8.5 9 3.5l6 5V15a1 1 0 0 1-1 1h-3v-4H7v4H4a1 1 0 0 1-1-1z",
  etiqueta: "M3 3h5l7 7-5 5-7-7zM6 6h.01",
  caixa: "M3 6.2 9 3l6 3.2v5.6L9 15l-6-3.2zM3 6.2 9 9.4l6-3.2M9 9.4V15",
  ficha: "M5 2.5h8v13H5zM7.5 6h3M7.5 9h3M7.5 12h2",
  pessoa: "M9 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3.5 15.5c.6-2.7 2.8-4 5.5-4s4.9 1.3 5.5 4",
  tabelas: "M2.5 4.5h13M2.5 9h13M2.5 13.5h13M6 2.5v13",
  exportar: "M9 11.5V3m0 0L6 6m3-3 3 3M3.5 12.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2",
  caixas: "M2.5 5.5h13v9h-13zM2.5 9h13M7 5.5V3h4v2.5",
  ajustes: "M3 5.5h12M3 12.5h12M7 3.5v4M11.5 10.5v4",
  caminhao:
    "M1.5 5.5h8v6h-8zM9.5 8h3l2 2v1.5h-5zM4.5 13.5a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4zM12 13.5a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4z",
  panela: "M3 7.5h12v3a4.5 4.5 0 0 1-4.5 4.5h-3A4.5 4.5 0 0 1 3 10.5zM6.5 4.5c0-1 1-1.2 1-2M10 4.5c0-1 1-1.2 1-2",
  inventario: "M5 2.5h8v13H5zM7 6l1.2 1.2L11 4.5M7 11l1.2 1.2L11 9.5",
  nota: "M4 2.5h10v13l-2-1.2-2 1.2-2-1.2-2 1.2-2-1.2zM6.5 6h5M6.5 9h5",
  grafico: "M3 15V8M7.5 15V4M12 15v-5M2 15.5h14",
  rede: "M9 2.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM2.5 9h13M9 2.5c1.8 2 2.6 4.2 2.6 6.5S10.8 14 9 15.5C7.2 14 6.4 11.8 6.4 9S7.2 4.5 9 2.5z",
  vendas:
    "M2.5 3.5h2l1.6 7.6a1 1 0 0 0 1 .8h5.4a1 1 0 0 0 1-.8L15 6H5.2M7 14.5a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8zM12.5 14.5a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8z",
  calendario: "M3 4.5h12v11H3zM3 8h12M6.5 2.5v3M11.5 2.5v3",
  agenda: "M3 4.5h12v11H3zM3 8h12M6.5 2.5v3M11.5 2.5v3M6 11h2M10 11h2",
  mesas: "M2.5 6.5h13M4.5 6.5v6M13.5 6.5v6M6.5 4.5a2.5 2.5 0 0 1 5 0",
  config:
    "M9 11.2a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4zM9 2.5v1.8M9 13.7v1.8M15.5 9h-1.8M4.3 9H2.5M13.6 4.4l-1.3 1.3M5.7 12.3l-1.3 1.3M13.6 13.6l-1.3-1.3M5.7 5.7 4.4 4.4",
  predio: "M3.5 15.5v-13h11v13M6 5.5h2M10 5.5h2M6 9h2M10 9h2M7.5 15.5v-3h3v3",
  loja: "M2.5 7.5h13v8h-13zM2.5 7.5 4 3h10l1.5 4.5M7 15.5v-4h4v4",
  usuarios:
    "M6.5 8.5a2.6 2.6 0 1 0 0-5.2 2.6 2.6 0 0 0 0 5.2zM1.5 15c.5-2.4 2.5-3.6 5-3.6s4.5 1.2 5 3.6M12 4.2a2.4 2.4 0 0 1 0 4.6M13.2 11.6c1.7.4 2.9 1.5 3.3 3.4",
  chave: "M11.5 2.5a4 4 0 1 1-3.3 6.3L3 14h-1.5v-1.5l.9-.9 1.3.3.3-1.3 1.3-1.3 1.3.3.4-1.4a4 4 0 0 1 4.5-5.7z",
  tomada: "M6.5 2.5v4M11.5 2.5v4M4.5 6.5h9v2a4.5 4.5 0 0 1-4.5 4.5A4.5 4.5 0 0 1 4.5 8.5zM9 13v3",
  // Fidelidade (091): o prêmio do cartão de visitas.
  presente: "M3.5 8.5h11v7h-11zM2.5 5.5h13v3h-13zM9 5.5v10M9 5.5C7.8 2.6 5 2.8 5.8 4.6 6.2 5.4 9 5.5 9 5.5s2.8-.1 3.2-.9C13 2.8 10.2 2.6 9 5.5",
  lupa: "M8.2 13.4a5.2 5.2 0 1 0 0-10.4 5.2 5.2 0 0 0 0 10.4zM12.2 12.2 15.5 15.5",
  alfinete: "M11 2.5 15.5 7l-2.2.6-3 3 .4 2.6-1.3 1.3-3-3-3.4 3.4 3.4-3.4-3-3L4.7 7.3l2.6.4 3-3z",
} as const;

export type NomeIcone = keyof typeof ICONES;
