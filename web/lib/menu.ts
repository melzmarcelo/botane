import type { NomeIcone } from "./icones";

/**
 * As telas do sistema, e em que grupo cada uma mora.
 *
 * 🔑 **Saiu do `layout.tsx` em 15/09/2026**, quando a busca por Ctrl+K nasceu:
 * a mesma lista passou a servir a TRÊS peças — o menu lateral, a paleta de
 * busca e os atalhos fixados. Lista de navegação duplicada é lista que
 * diverge: a tela nova entra no menu, não entra na busca, e a busca vira uma
 * coisa em que não se confia.
 */
export type ItemMenu = {
  href: string;
  nome: string;
  icone: NomeIcone;
  /** `chave` pode ser uma lista: a tela de Ajustes serve a quatro permissões e
      quem tem só a de perda também precisa chegar nela. */
  chave?: string | string[];
  /** Só entra no menu com o envio ao PDV ligado — ver `enviar_ao_pdv`. */
  soComEnvioAoPdv?: boolean;
  /** 🔑 Só entra com MAIS DE UMA loja. Com uma só, a visão da rede é o
      Início repetido — e item de menu que leva a uma tela redundante ensina
      a ignorar o menu. */
  soComVariasLojas?: boolean;
  /** 🔑 Só entra com o módulo de Reservas ligado NESTA loja
      (`parametros.reservas_ligado`). Casa que não faz reserva não tem por que
      ver um grupo inteiro que não leva a lugar nenhum. */
  soComReservas?: boolean;
};

export type GrupoMenu = { grupo: string; icone: NomeIcone; itens: ItemMenu[] };

export const MENU: GrupoMenu[] = [
  {
    grupo: "Cadastros",
    icone: "etiqueta",
    itens: [
      { href: "/produtos", nome: "Produtos", icone: "caixa", chave: "cadastros.produtos" },
      { href: "/fichas", nome: "Fichas técnicas", icone: "ficha", chave: "fichas.visualizar" },
      // 🔑 **"Pessoas", e não "Fornecedores"** (04/09/2026, pedido do dono): a
      // tabela passou a guardar quem não vende nada para a casa —
      // funcionário, sócio. ⚠️ A ROTA continua `/fornecedores`: mudá-la
      // espalharia risco por Compras, Integrações e exportações para o
      // usuário ver exatamente a mesma tela. O nome que importa é o do menu.
      { href: "/fornecedores", nome: "Pessoas", icone: "pessoa", chave: "cadastros.fornecedores" },
      // As quatro num item só. Quem procura "local de estoque" no menu não o
      // encontra pelo nome — por isso a tela DIZ o que tem dentro, logo abaixo
      // do título, e cada aba tem endereço próprio (`?aba=locais`).
      {
        href: "/cadastros",
        nome: "Tabelas de apoio",
        icone: "tabelas",
        chave: ["cadastros.setores", "cadastros.locais", "cadastros.categorias",
                "cadastros.unidades_medida", "cmv.grupos"],
      },
      // ⚠️ Só aparece com o envio ao PDV LIGADO. Item de menu para um recurso
      // desligado é uma porta que abre numa tela que explica que não faz nada.
      {
        href: "/exportacao",
        nome: "Exportação para o PDV",
        icone: "exportar",
        chave: ["integracao.pdv", "admin.integracoes"],
        soComEnvioAoPdv: true,
      },
    ],
  },
  {
    grupo: "Estoque",
    icone: "caixas",
    itens: [
      { href: "/estoque", nome: "Saldos e movimentos", icone: "caixas", chave: "estoque.saldos" },
      {
        href: "/ajustes",
        nome: "Ajustes",
        icone: "ajustes",
        // ⚠️ Lista de chaves: a tela serve a cinco tipos, e quem tem só a de
        // custo (ou só a de perda) também precisa chegar nela.
        chave: ["estoque.entradas", "estoque.saidas", "estoque.perdas",
                "estoque.transferencias", "estoque.custo"],
      },
      {
        href: "/transferencias",
        nome: "Remessas entre lojas",
        icone: "caminhao",
        // ⚠️ Só aparece com mais de uma loja: numa casa só, remessa não existe
        // — a transferência entre prateleiras é imediata e mora em Ajustes.
        soComVariasLojas: true,
        chave: ["estoque.transferencias", "estoque.transferencia_receber"],
      },
      { href: "/producao", nome: "Produção", icone: "panela", chave: "estoque.saidas" },
      { href: "/inventario", nome: "Inventário", icone: "inventario", chave: "estoque.inventario" },
    ],
  },
  {
    grupo: "Compras",
    icone: "nota",
    itens: [
      { href: "/compras", nome: "Notas de entrada", icone: "nota", chave: "compras.notas" },
    ],
  },
  {
    grupo: "CMV",
    icone: "grafico",
    itens: [
      { href: "/cmv", nome: "Painel de CMV", icone: "grafico", chave: "cmv.painel" },
      { href: "/rede", nome: "Visão da rede", icone: "rede", chave: "cmv.painel", soComVariasLojas: true },
      { href: "/vendas", nome: "Vendas", icone: "vendas", chave: "cmv.painel" },
      // ⚠️ **Não entra com `cmv.painel`.** Esta tela mostra o que cada PESSOA
      // deve — dívida individual, não número de negócio — e a chave do painel é
      // a mais larga da casa. Fica com as mesmas do servidor.
      {
        href: "/consumo",
        nome: "Períodos de consumo",
        icone: "calendario",
        chave: ["consumo.periodos", "cmv.relatorios"],
      },
    ],
  },
  {
    // 🔑 **O grupo inteiro só existe com o módulo ligado** nesta loja
    // (migração 068). Não é só esconder item: uma casa que não faz reserva não
    // ganha um grupo a mais no menu para nunca abrir.
    // ⚠️ O `soComReservas` vai em CADA item, não no grupo: o filtro do menu é
    // por item, e grupo que fica sem item some sozinho — é assim que
    // Transferências já desaparece na casa de uma loja só.
    grupo: "Reservas",
    icone: "agenda",
    itens: [
      {
        // 🔑 A agenda vem PRIMEIRO: e a tela que a recepcao abre todo dia. Salao
        // e Configuracoes se visitam no comeco e quase nunca mais.
        href: "/reservas/agenda",
        nome: "Agenda do dia",
        icone: "agenda",
        chave: ["reservas.ver", "reservas.editar"],
        soComReservas: true,
      },
      {
        href: "/reservas/salao",
        nome: "Salão",
        icone: "mesas",
        // ⚠️ `reservas.ver` basta para OLHAR o salão — quem atende o telefone
        // precisa saber quantos lugares existem. Editar exige `configurar`, e
        // quem decide é o servidor; a tela só esconde os controles.
        chave: ["reservas.ver", "reservas.configurar"],
        soComReservas: true,
      },
      {
        // 🔑 **Catálogos mora DENTRO de Reservas** (correção do dono,
        // 21/09/2026: *"o menu de catálogo fica dentro de reservas, onde
        // somente será demonstrada quando utilizado reserva"*). O catálogo é o
        // PDF que o site de reservas apresenta — sem reserva ele não tem onde
        // aparecer, e um grupo próprio no menu prometia um módulo que a casa
        // não usa.
        // ⚠️ **`soComReservas` como os outros três**: o filtro do menu é por
        // item, e é ele que faz o catálogo sumir junto com o resto do grupo.
        href: "/catalogos",
        nome: "Catálogos",
        icone: "vendas",
        // ⚠️ `ver` basta para OLHAR; criar é que exige `editar`, e quem decide
        // é o servidor — a tela só esconde os controles.
        chave: ["catalogos.ver", "catalogos.editar"],
        soComReservas: true,
      },
      {
        href: "/reservas/configuracoes",
        nome: "Configurações",
        icone: "config",
        chave: "reservas.configurar",
        soComReservas: true,
      },
    ],
  },
  {
    grupo: "Administração",
    icone: "predio",
    itens: [
      { href: "/empresa", nome: "Empresa", icone: "predio", chave: "admin.empresa" },
      { href: "/lojas", nome: "Lojas", icone: "loja", chave: "admin.unidades" },
      { href: "/usuarios", nome: "Usuários", icone: "usuarios", chave: "admin.usuarios" },
      { href: "/papeis", nome: "Papéis e permissões", icone: "chave", chave: "admin.papeis" },
      { href: "/integracoes", nome: "Integrações", icone: "tomada", chave: "admin.integracoes" },
      { href: "/auditoria", nome: "Auditoria", icone: "lupa", chave: "admin.auditoria" },
    ],
  },
];

/**
 * O Início não pertence a grupo nenhum.
 *
 * 🔑 **Um grupo de um item só é uma pasta com um papel dentro.** "Operação"
 * existia para abrigar Início, Alertas e Ajuda — e as duas últimas foram para o
 * menu do usuário, onde a pessoa as procura: alerta e manual são de QUEM está
 * usando, não de um assunto do sistema. Sobrou o Início, e um cabeçalho de
 * grupo sobre ele só custava um clique para chegar à primeira tela.
 */
export const INICIO: ItemMenu = { href: "/", nome: "Início", icone: "casa" };

export type Ambiente = {
  pode: (chave: string) => boolean;
  /** Dica de interface: item de menu para recurso desligado é porta que não leva a nada. */
  enviaAoPdv: boolean;
  /** A casa tem mais de uma loja que esta pessoa enxerga. */
  variasLojas: boolean;
  temReservas: boolean;
};

/** Uma entrada do menu já montado: ou um item solto, ou um grupo com filhos. */
export type Entrada =
  | { tipo: "item"; grupo: string; item: ItemMenu }
  | { tipo: "grupo"; grupo: string; icone: NomeIcone; itens: ItemMenu[] };

const visivel = (i: ItemMenu, a: Ambiente) =>
  (!i.chave || (Array.isArray(i.chave) ? i.chave.some(a.pode) : a.pode(i.chave))) &&
  (!i.soComEnvioAoPdv || a.enviaAoPdv) &&
  (!i.soComVariasLojas || a.variasLojas) &&
  (!i.soComReservas || a.temReservas);

/**
 * O menu desta pessoa, nesta loja.
 *
 * 🔑 **Grupo que sobra com UM item vira item.** Abrir uma pasta com um papel
 * dentro é um clique que não compra nada — e isso não vale só para Compras, que
 * nasce com um item: vale para quem tem permissão de uma tela só dentro de um
 * grupo de seis. Antes, essa pessoa clicava em "ADMINISTRAÇÃO" para encontrar
 * "Usuários" sozinho lá dentro.
 */
export function montarMenu(a: Ambiente): Entrada[] {
  const entradas: Entrada[] = [];
  for (const g of MENU) {
    const itens = g.itens.filter((i) => visivel(i, a));
    if (!itens.length) continue;
    if (itens.length === 1) entradas.push({ tipo: "item", grupo: g.grupo, item: itens[0] });
    else entradas.push({ tipo: "grupo", grupo: g.grupo, icone: g.icone, itens });
  }
  return entradas;
}

/** Tudo o que esta pessoa pode abrir, numa lista só — é o que a busca varre. */
export function telasDisponiveis(a: Ambiente): (ItemMenu & { grupo: string })[] {
  return [
    { ...INICIO, grupo: "Início" },
    ...MENU.flatMap((g) => g.itens.filter((i) => visivel(i, a)).map((i) => ({ ...i, grupo: g.grupo }))),
  ];
}
