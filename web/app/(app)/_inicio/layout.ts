/**
 * 🔑 **A tela inicial de CADA UM** (pedido do dono, 06/11/2026: *"permitir configuração no
 * dashboard, assim o usuário pode configurar a sua tela inicial como achar melhor, com os dados
 * que preferir e a posição que preferir. Gravar isto por usuário"*).
 *
 * O Início virou uma lista de QUADROS: cada um com posição, largura e visível ou não, mais os
 * indicadores que a faixa do dia mostra. Fica em `preferencias_usuario` (migração 148), chave
 * `painel:inicio` — no servidor, para valer em qualquer aparelho.
 * ⚠️ O layout diz o que a pessoa QUER ver, não o que ela PODE: quadro sem dado (sem permissão, sem
 * módulo) some na hora de desenhar, e a linha se fecha sem buraco (`larguras`).
 * ⚠️ Quadro novo que nascer depois de a pessoa salvar entra no FIM, visível: senão ninguém que
 * já personalizou o veria nunca.
 */

export type Largura = 4 | 6 | 8 | 12;

export type IdBloco =
  | "hoje" | "faturamento" | "atencao" | "atalhos" | "mais_vendidos" | "periodo"
  | "pedidos" | "mesas" | "producao" | "custo" | "casa";

export type Bloco = { id: IdBloco; largura: Largura; oculto?: boolean };

/** Os indicadores da faixa "Vendas do dia". */
export type IdIndicador = "vendas" | "faturado" | "ticket" | "pedidos" | "mesas" | "producao" | "etiquetas";

/** `indicadores_ocultos` nulo = a pessoa nunca escolheu (vale a regra de sempre da faixa). */
export type LayoutInicio = { versao: 1; blocos: Bloco[]; indicadores_ocultos: IdIndicador[] | null };

export const CHAVE_LAYOUT = "painel:inicio";

export const NOMES: Record<IdBloco, string> = {
  hoje: "Vendas do dia (indicadores)",
  faturamento: "Faturamento por dia",
  atencao: "Precisa de atenção",
  atalhos: "Atalhos",
  mais_vendidos: "Mais vendidos",
  periodo: "Período até agora",
  pedidos: "Pedidos do site",
  mesas: "Mesas do dia",
  producao: "Produção do dia",
  custo: "Onde o custo pesa",
  casa: "A casa",
};

export const INDICADORES: { id: IdIndicador; nome: string }[] = [
  { id: "vendas", nome: "Vendas" },
  { id: "faturado", nome: "Faturado" },
  { id: "ticket", nome: "Ticket médio" },
  { id: "pedidos", nome: "Pedidos em aberto" },
  { id: "mesas", nome: "Mesas" },
  { id: "producao", nome: "Produção" },
  { id: "etiquetas", nome: "Etiquetas" },
];

export const LARGURAS: { valor: Largura; nome: string }[] = [
  { valor: 4, nome: "⅓" },
  { valor: 6, nome: "½" },
  { valor: 8, nome: "⅔" },
  { valor: 12, nome: "inteira" },
];

/** O padrão é a tela de antes (protótipo aprovado em 05/11/2026), quadro a quadro. */
export const PADRAO: LayoutInicio = {
  versao: 1,
  blocos: [
    { id: "hoje", largura: 12 },
    { id: "faturamento", largura: 8 },
    { id: "atencao", largura: 4 },
    { id: "atalhos", largura: 4 },
    { id: "mais_vendidos", largura: 8 },
    { id: "periodo", largura: 12 },
    { id: "pedidos", largura: 4 },
    { id: "mesas", largura: 4 },
    { id: "producao", largura: 4 },
    { id: "custo", largura: 8 },
    { id: "casa", largura: 4 },
  ],
  indicadores_ocultos: null,
};

const IDS = new Set<string>(PADRAO.blocos.map((b) => b.id));
const LARG = new Set<number>([4, 6, 8, 12]);
const IND = new Set<string>(INDICADORES.map((i) => i.id));

/** O que veio do servidor, saneado: id desconhecido sai, repetido sai, novo entra no fim. */
export function normalizar(bruto: unknown): LayoutInicio {
  const v = (bruto ?? {}) as Partial<LayoutInicio>;
  if (!Array.isArray(v.blocos)) return clonar(PADRAO);
  const vistos = new Set<string>();
  const blocos: Bloco[] = [];
  for (const b of v.blocos) {
    if (!b || !IDS.has(b.id) || vistos.has(b.id)) continue;
    vistos.add(b.id);
    const padrao = PADRAO.blocos.find((p) => p.id === b.id)!;
    blocos.push({ id: b.id, largura: LARG.has(b.largura) ? b.largura : padrao.largura, ...(b.oculto ? { oculto: true } : {}) });
  }
  for (const p of PADRAO.blocos) if (!vistos.has(p.id)) blocos.push({ ...p });
  const indicadores_ocultos = Array.isArray(v.indicadores_ocultos)
    ? v.indicadores_ocultos.filter((i): i is IdIndicador => IND.has(i)) : null;
  return { versao: 1, blocos, indicadores_ocultos };
}

export function clonar(l: LayoutInicio): LayoutInicio {
  return { versao: 1, blocos: l.blocos.map((b) => ({ ...b })), indicadores_ocultos: l.indicadores_ocultos ? [...l.indicadores_ocultos] : null };
}

/**
 * A largura EFETIVA de cada quadro desenhado: quando o próximo não cabe no resto da linha, o
 * último da linha estica até o fim. É o que fecha o buraco do quadro que sumiu por falta de dado
 * (quem não vê dinheiro perde o faturamento, e a atenção ocupa a linha).
 */
export function larguras(blocos: Bloco[]): Map<IdBloco, Largura> {
  const r = new Map<IdBloco, Largura>();
  let usado = 0;
  blocos.forEach((b, i) => {
    if (usado + b.largura > 12) usado = 0;
    usado += b.largura;
    const prox = blocos[i + 1];
    const fecha = !prox || usado + prox.largura > 12;
    r.set(b.id, (fecha ? b.largura + (12 - usado) : b.largura) as Largura);
    if (fecha) usado = 0;
  });
  return r;
}

/** As classes de coluna: no Tailwind a classe tem de existir por inteiro no código. */
export const SPAN: Record<number, string> = {
  4: "lg:col-span-4", 6: "lg:col-span-6", 8: "lg:col-span-8", 10: "lg:col-span-10", 12: "lg:col-span-12",
};
