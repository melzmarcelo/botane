import type { NomeIcone } from "./icones";

/**
 * As telas do sistema, e em que grupo cada uma mora.
 *
 * 🔑 **Saiu do `layout.tsx` em 15/09/2026**, quando a busca por Ctrl+K nasceu:
 * a mesma lista passou a servir a TRÊS peças — o menu lateral, a paleta de
 * busca (os atalhos fixados saíram em 05/10/2026). Lista de navegação duplicada é lista que
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
  /** 🔑 Um nível a mais dentro do grupo (24/09/2026: "Reservas" com Agenda e
      Salão dentro do Portal de Clientes). Itens com o mesmo `subgrupo` aparecem
      sob um título recolhível; a busca continua vendo cada item. */
  subgrupo?: string;
  /** ⚠️ O subgrupo fica mesmo com UM item só — exceção à regra de
      `blocosDoGrupo`. Pedido do dono (14/10/2026): "Catálogos › Cadastro" no
      Portal de Clientes, que deve ganhar telas irmãs. */
  manterSubgrupo?: boolean;
};

export type GrupoMenu = { grupo: string; icone: NomeIcone; itens: ItemMenu[] };

export const MENU: GrupoMenu[] = [
  // 🔑 **A ORDEM é a do dono** (28/09/2026): Cadastro · Nota de entrada · Vendas ·
  // Estoque · CMV · Portal de Clientes · Etiquetas · Administração — o caminho do dado,
  // da compra ao número.
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
    grupo: "Compras",
    icone: "nota",
    itens: [
      { href: "/compras", nome: "Notas de entrada", icone: "nota", chave: "compras.notas" },
    ],
  },
  {
    grupo: "Vendas",
    icone: "vendas",
    itens: [
      // ⚠️ **Não entra com `cmv.painel`.** Esta tela mostra o que cada PESSOA
      // deve — dívida individual, não número de negócio — e a chave do painel é
      // a mais larga da casa. Fica com as mesmas do servidor.
      {
        href: "/consumo",
        nome: "Períodos",
        icone: "calendario",
        chave: ["consumo.periodos", "cmv.relatorios"],
      },
      // 🔑 O estudo das vendas (21/10/2026) — a mesma chave dos documentos.
      { href: "/vendas/painel", nome: "Painel", icone: "grafico",
        chave: ["cmv.painel", "cmv.relatorios"] },
      // Os documentos de venda (cupons do PDV e os lançados à mão) — a antiga "Vendas".
      { href: "/vendas", nome: "Documentos", icone: "vendas", chave: "cmv.painel" },
    ],
  },
  {
    grupo: "Estoque",
    icone: "caixas",
    itens: [
      // 🔑 A visão para decidir (22/10/2026) — a mesma chave de Saldos: não mostra nada que
      // a lista e o razão já não mostrem.
      { href: "/estoque/painel", nome: "Painel", icone: "grafico", chave: "estoque.saldos" },
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
    // 🔑 **CMV direto no menu** (pedido do dono, 28/09/2026: *"colocar o CMV diretamente no
    // menu; criar um novo item com Vendas, e dentro Períodos e Documentos (atual Vendas)"*).
    // Grupo de um item só vira item em `montarMenu` — é o que o põe direto na lateral.
    // ⚠️ Por isso a Visão da rede saiu daqui (foi para Administração): com ela, numa casa de
    // duas lojas, o CMV voltaria a ser uma pasta com dois itens.
    grupo: "CMV",
    icone: "grafico",
    itens: [
      { href: "/cmv", nome: "CMV", icone: "grafico", chave: "cmv.painel" },
    ],
  },
  {
    // 🔑 **Precificação** (05/10/2026, `docs/precificacao-estudo.md`; o grupo se chamou
    // "Preços" por um dia — o dono pediu o nome do módulo). Três telas: a que analisa e
    // aplica, a evolução de preço × custo e a configuração da loja.
    // ⚠️ Fora do grupo do CMV de propósito: o dono pediu o CMV direto no menu, e um segundo
    // item ali o transformaria de volta numa pasta.
    // ⚠️ "Preço × custo" continua aceitando as chaves do CMV: a tela nasceu com elas, e quem
    // a usava não pode perdê-la no deploy.
    grupo: "Precificação",
    icone: "preco",
    itens: [
      { href: "/precificacao", nome: "Precificação", icone: "preco", chave: "precificacao.analisar" },
      {
        href: "/precos", nome: "Preço × custo", icone: "grafico",
        chave: ["precificacao.analisar", "cmv.painel", "cmv.relatorios"],
      },
      {
        href: "/precificacao/configuracao", nome: "Configuração", icone: "config",
        chave: ["precificacao.configurar", "precificacao.analisar"],
      },
    ],
  },
  {
    // 🔑 **"Portal de Clientes"** (pedido do dono, 24/09/2026: *"alterar o
    // módulo Reservas para Portal de Clientes. No menu: Portal de Clientes —
    // Configuração — Reservas, e dentro dois submenus, Agenda e Salão; no mesmo
    // nível de Reservas, Catálogos."*). O módulo cresceu além da mesa: é tudo o
    // que o cliente vê no site — reserva, cardápios, cadastro e contato.
    // ⚠️ **O grupo inteiro só existe com o módulo ligado** nesta loja (migração
    // 068). O `soComReservas` vai em CADA item, não no grupo: o filtro do menu é
    // por item, e grupo que fica sem item some sozinho.
    // ⚠️ As chaves (`reservas.*`, `catalogos.*`) e as rotas (`/reservas/...`)
    // NÃO mudaram de nome: renomear chave de permissão reescreveria papéis, e
    // rota nova quebraria atalho e favorito de quem já usa.
    grupo: "Portal de Clientes",
    icone: "pessoa",
    itens: [
      // 🔑 **A ordem do Portal** (pedido do dono, 14/10/2026): Clientes, QR codes,
      // Reservas (Agenda, Salão, Configuração), Fidelidade (Painel, Códigos, Prêmios,
      // Configuração), Catálogos (Cadastro) e Pedidos (Painel, Lista de pedidos).
      // A Configuração que era solta é a da reserva e foi para dentro de Reservas.
      {
        // 🔑 **Clientes** (pedido do dono, 24/09/2026: *"dentro do Portal do
        // Cliente, criar o menu e a página para listar os clientes
        // cadastrados"*). Mesmo nível de Reservas e Catálogos: o cadastro serve
        // aos dois. `reservas.ver` basta — a agenda já mostra nome e telefone.
        href: "/reservas/clientes",
        nome: "Clientes",
        icone: "usuarios",
        chave: "reservas.ver",
        soComReservas: true,
      },
      {
        // 🔑 **QR codes** (pedido do dono, 27/09/2026): site, reserva, cardápio de mesa e
        // fidelidade — todos os QR da casa num lugar só, com a impressão.
        href: "/reservas/qrcodes",
        nome: "QR codes",
        icone: "etiqueta",
        chave: "reservas.configurar",
        soComReservas: true,
      },
      {
        // 🔑 A agenda vem PRIMEIRO dentro de Reservas: é a tela que a recepção
        // abre todo dia. O salão se monta no começo e quase nunca mais.
        href: "/reservas/agenda",
        nome: "Agenda",
        icone: "agenda",
        chave: ["reservas.ver", "reservas.editar"],
        soComReservas: true,
        subgrupo: "Reservas",
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
        subgrupo: "Reservas",
      },
      {
        href: "/reservas/configuracoes",
        nome: "Configuração",
        icone: "config",
        chave: "reservas.configurar",
        soComReservas: true,
        subgrupo: "Reservas",
      },
      {
        // 🔑 **Painel** (pedido do dono, 27/09/2026: *"visualizar tudo que diz respeito ao
        // plano de fidelidade em uma só tela"*). Primeiro do subgrupo: é a visão geral.
        href: "/fidelidade/painel",
        nome: "Painel",
        icone: "presente",
        chave: "fidelidade.operar",
        soComReservas: true,
        subgrupo: "Fidelidade",
      },
      {
        // 🔑 **Códigos** (pedido do dono, 27/09/2026): a tela do caixa no método
        // "código de confirmação" — o cliente lê o QR do caixa e o código aparece aqui.
        href: "/fidelidade/codigos",
        nome: "Códigos",
        icone: "chave",
        chave: "fidelidade.operar",
        soComReservas: true,
        subgrupo: "Fidelidade",
      },
      {
        // 🔑 **Fidelidade** (pedido do dono, 24/09/2026: *"no menu podemos ter um
        // Fidelidade — Configuração"*). O cartão de visitas com check-in por QR.
        href: "/fidelidade/premios",
        nome: "Prêmios",
        icone: "etiqueta",
        chave: "fidelidade.operar",
        soComReservas: true,
        subgrupo: "Fidelidade",
      },
      {
        href: "/fidelidade/configuracao",
        nome: "Configuração",
        icone: "config",
        chave: "fidelidade.configurar",
        soComReservas: true,
        subgrupo: "Fidelidade",
      },
      {
        // 🔑 Catálogos no MESMO nível de Reservas (pedido do dono): é o que o
        // site apresenta, não uma parte da agenda.
        href: "/catalogos",
        nome: "Cadastro",
        icone: "vendas",
        // ⚠️ `ver` basta para OLHAR; criar é que exige `editar`, e quem decide
        // é o servidor — a tela só esconde os controles.
        chave: ["catalogos.ver", "catalogos.editar"],
        soComReservas: true,
        subgrupo: "Catálogos",
        manterSubgrupo: true,
      },
      {
        // 🔑 **Cardápio Vivo** (pedido do dono, 14/10/2026): o cardápio da mesa como feed.
        // A configuração da loja e o acesso das mesas (QR e NFC).
        href: "/cardapio-vivo",
        nome: "Cardápio Vivo",
        icone: "mesas",
        chave: ["catalogos.ver", "catalogos.editar"],
        soComReservas: true,
        subgrupo: "Catálogos",
      },
      {
        // 🔑 **Anúncios** (121, pedido do dono, 16/10/2026): da casa ou de outra marca, no meio do
        // Cardápio Vivo, com o ritmo da casa e o relatório para apresentar ao parceiro.
        href: "/cardapio-vivo/anuncios",
        nome: "Anúncios",
        icone: "grafico",
        chave: ["catalogos.ver", "catalogos.editar"],
        soComReservas: true,
        subgrupo: "Catálogos",
      },
      {
        // 🔑 **Atenção × Vendas** (fase 2, 115): a atenção do feed cruzada com venda e margem.
        href: "/cardapio-vivo/atencao",
        nome: "Atenção × Vendas",
        icone: "grafico",
        chave: "cardapio.atencao",
        soComReservas: true,
        subgrupo: "Catálogos",
      },
      {
        // 🔑 **Testes A/B** (fase 3, 116): vídeo × foto e ordem atual × sugerida.
        href: "/cardapio-vivo/testes",
        nome: "Testes A/B",
        icone: "grafico",
        chave: "cardapio.atencao",
        soComReservas: true,
        subgrupo: "Catálogos",
      },
      {
        // 🔑 **Pedidos pelo catálogo** (pedido do dono, 28/09/2026: *"uma tela com pedidos
        // e um painel para acompanhar"*). O painel primeiro: é a tela que o balcão deixa aberta.
        href: "/pedidos/painel",
        nome: "Painel",
        icone: "grafico",
        chave: ["pedidos.ver", "pedidos.operar"],
        soComReservas: true,
        subgrupo: "Pedidos",
      },
      {
        href: "/pedidos",
        nome: "Lista de pedidos",
        icone: "nota",
        chave: ["pedidos.ver", "pedidos.operar"],
        soComReservas: true,
        subgrupo: "Pedidos",
      },
    ],
  },
  {
    // 🔑 **Etiquetas** (pedido do dono, 28/09/2026: *"um novo módulo, o de Etiquetas,
    // para controlar validade, quantidade e demais coisas úteis, em produtos produzidos
    // e abertos para consumo"*). Imprimir primeiro: é o gesto da bancada, várias vezes
    // por dia; o painel é a checagem da manhã.
    grupo: "Etiquetas",
    icone: "etiqueta",
    itens: [
      { href: "/etiquetas", nome: "Imprimir", icone: "etiqueta", chave: "etiquetas.imprimir" },
      { href: "/etiquetas/painel", nome: "Painel de validades", icone: "calendario",
        chave: "etiquetas.imprimir" },
      { href: "/etiquetas/configuracao", nome: "Configuração", icone: "config",
        chave: "etiquetas.configurar" },
    ],
  },
  {
    grupo: "Administração",
    icone: "predio",
    itens: [
      { href: "/empresa", nome: "Empresa", icone: "predio", chave: "admin.empresa" },
      { href: "/lojas", nome: "Lojas", icone: "loja", chave: "admin.unidades" },
      // Veio do grupo CMV (28/09/2026): o CMV passou a ser item direto.
      { href: "/rede", nome: "Visão da rede", icone: "rede", chave: "cmv.painel", soComVariasLojas: true },
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

/** Um pedaço do grupo já aberto: um item solto, ou um subgrupo com os seus. */
export type Bloco =
  | { tipo: "item"; item: ItemMenu }
  | { tipo: "sub"; nome: string; icone: NomeIcone; itens: ItemMenu[] };

/**
 * Os itens de um grupo, com os de mesmo `subgrupo` juntos.
 *
 * ⚠️ **Subgrupo que sobra com UM item vira item** — a mesma regra do grupo em
 * `montarMenu`: um título para abrir e achar uma tela só é um clique à toa.
 */
export function blocosDoGrupo(itens: ItemMenu[]): Bloco[] {
  const blocos: Bloco[] = [];
  for (const i of itens) {
    if (!i.subgrupo) {
      blocos.push({ tipo: "item", item: i });
      continue;
    }
    const ja = blocos.find((b) => b.tipo === "sub" && b.nome === i.subgrupo);
    if (ja && ja.tipo === "sub") ja.itens.push(i);
    else blocos.push({ tipo: "sub", nome: i.subgrupo, icone: i.icone, itens: [i] });
  }
  return blocos.map((b) => (b.tipo === "sub" && b.itens.length === 1 && !b.itens[0].manterSubgrupo
    ? { tipo: "item", item: b.itens[0] } : b));
}
