/**
 * O catálogo — o cabeçalho do que a casa publica para o cliente.
 *
 * 🔑 **Camada de service, e não `api.get` solto na página** — regra da casa. A
 * tela conhece `listar`, `salvar` e `excluir`; a forma das rotas é assunto
 * daqui, e o dia em que ela mudar a página não fica sabendo.
 */
import { api, BASE_API } from "@/lib/api";

export type Situacao = "RASCUNHO" | "ATIVO" | "INATIVO";

export type Catalogo = {
  id: number;
  nome: string;
  origem: string;
  publica_de: string | null;
  publica_ate: string | null;
  situacao: Situacao;
  observacao: string | null;
  /** 🔑 O cliente se identifica (telefone e, se novo, cadastro) antes de abrir.
   *  Quem garante é o servidor — o site nem recebe o conteúdo sem isso. */
  exige_cadastro: boolean;
  /** 🔑 As lojas em que o CLIENTE vê este catálogo no site (migração 087). */
  lojas: number[];
  /** 🔑 Está no ar HOJE — não é o mesmo que estar ATIVO: um ativo cujo período
   *  já passou não está publicado. Quem responde é o servidor, porque é ele que
   *  sabe que dia é hoje na loja. */
  publicado_hoje: boolean;
  criado_por: string | null;
  /** 🔑 O PDF que o site de reservas exibe. Nulo = ainda não subiu. */
  arquivo_url: string | null;
  /** O nome ORIGINAL — a URL leva sufixo aleatório e não diz mais qual PDF é. */
  arquivo_nome: string | null;
  arquivo_bytes: number | null;
  arquivo_em: string | null;
  /** O resumo do cardápio montado — pratos distintos e o que falta neles. */
  resumo: { pratos: number; sem_foto: number; sem_descricao: number; inativos: number } | null;
  /** É o Cardápio Vivo (o feed da mesa) de alguma loja. */
  cardapio_vivo: boolean;
};

/** O vocabulário vem do SERVIDOR: manter a lista aqui seria a segunda cópia. */
export type Opcoes = {
  origens: string[];
  situacoes: Situacao[];
  /** As lojas que o "Visível nas lojas" oferece: ativas e com Reservas ligado. */
  lojas: { id: number; nome: string }[];
};

/** ⚠️ Só o rótulo é daqui. O valor é do servidor, e é ele que manda. */
export const ROTULO_SITUACAO: Record<Situacao, string> = {
  RASCUNHO: "Rascunho",
  ATIVO: "Ativo",
  INATIVO: "Inativo",
};

/**
 * Como cada ORIGEM se apresenta na escolha do tipo.
 * ⚠️ Só o texto é daqui: os valores vêm de `/catalogos/opcoes`, e uma origem que
 * o servidor mandar sem rótulo aparece com o próprio código, em vez de sumir.
 */
export const APRESENTA_ORIGEM: Record<string, { titulo: string; curto: string; explica: string }> = {
  PRODUTOS: {
    titulo: "Montar com os produtos do PDV",
    curto: "Montado com produtos",
    explica: "Seções e pratos escolhidos aqui, com foto, preço e descrição. Serve ao site, ao Cardápio Vivo da mesa e aos pedidos.",
  },
  PDF: {
    titulo: "Enviar um PDF pronto",
    curto: "PDF",
    explica: "O cardápio já diagramado, em arquivo. O site o mostra como ele é.",
  },
};

export const opcoes = () => api.get<Opcoes>("/catalogos/opcoes");

export const listar = (situacao?: Situacao | "") =>
  api.get<Catalogo[]>(`/catalogos${situacao ? `?situacao=${situacao}` : ""}`);

export const obter = (id: number) => api.get<Catalogo>(`/catalogos/${id}`);

/** O que a tela manda ao gravar. Tudo opcional na edição: campo ausente não é
 *  campo nulo, e o servidor salva só o que veio. */
export type Gravar = {
  nome?: string;
  origem?: string;
  publica_de?: string | null;
  publica_ate?: string | null;
  situacao?: Situacao;
  observacao?: string | null;
  exige_cadastro?: boolean;
  lojas?: number[];
};

export const criar = (corpo: Gravar) => api.post<Catalogo>("/catalogos", corpo);

export const atualizar = (id: number, corpo: Gravar) =>
  api.put<Catalogo>(`/catalogos/${id}`, corpo);

export const excluir = (id: number) =>
  api.delete<{ message: string }>(`/catalogos/${id}`);

/**
 * Envia o PDF que o site de reservas vai exibir.
 *
 * ⚠️ **`FormData`, e sem `content-type` à mão.** O navegador põe o cabeçalho
 * com o `boundary` que ele mesmo sorteou; escrevê-lo aqui manda um boundary
 * que não existe, e o servidor lê um corpo vazio.
 */
export const enviarArquivo = (id: number, arquivo: File) => {
  const corpo = new FormData();
  corpo.append("arquivo", arquivo);
  return api.upload<Catalogo>(`/catalogos/${id}/arquivo`, corpo);
};

export const removerArquivo = (id: number) =>
  api.delete<Catalogo>(`/catalogos/${id}/arquivo`);

/** ⚠️ O endereço do PDF é do SERVIDOR, não do web: a URL vem relativa
 *  (`/arquivos/...`) e precisa do prefixo da API para o navegador achar. */
export const enderecoDoArquivo = (url: string) => `${BASE_API}${url}`;

/* ===========================================================================
   O catálogo de origem PRODUTOS — o cardápio montado aqui dentro
   ---------------------------------------------------------------------------
   🔑 **Pedido do dono (22/09/2026):** *"vamos adicionar a Origem Produtos.
   Quando for esta origem, ao listar os catálogos, ao clicar sobre vai abrir uma
   nova página para configuração. Neste, podemos criar Categorias e suas
   SubCategorias, cada item terá o Nome, Descrição e uma foto. Após isto,
   podemos vincular os produtos disponíveis no PDV para a subcategoria. Somente
   produtos ativos."*
   =========================================================================== */

/** 🔑 A constante em vez do literal: é ela que decide se a linha da lista abre
 *  a página de configuração ou o envio de PDF. */
export const ORIGEM_PRODUTOS = "PRODUTOS";

export type ItemDoCatalogo = {
  id: number;
  id_categoria: number;
  id_subcategoria: number | null;
  id_produto: number;
  produto: string;
  /** 🔑 O nome que o CLIENTE lê, quando a casa escreveu um. Nulo = o de cima. */
  nome_catalogo: string | null;
  codigo: string;
  /** 🔑 **O produto pode ter sido desativado DEPOIS de entrar no cardápio.** A
   *  tela precisa marcá-lo — senão a casa não descobre que publicou algo que
   *  saiu de linha. */
  ativo: boolean;
  foto_url: string | null;
  informacao_adicional: string | null;
  um_estoque: string | null;
  ordem: number;
  /** Cardápio Vivo (113): marcas DESTE cardápio, e o que vem do produto. */
  destaque: boolean;
  esgotado: boolean;
  tem_video: boolean;
  restricoes: string[];
  /** Fase 2 (115): o objetivo de negócio e o ajuste manual do nível de margem. */
  objetivo: string | null;
  margem_nivel: string | null;
  /** O preço que o cliente vê (loja → casa). Nulo = sem preço, nunca zero. */
  preco: number | null;
};

export type Secao = {
  id: number;
  nome: string;
  descricao: string | null;
  foto_url: string | null;
  foto_nome: string | null;
  ordem: number;
  /** Cardápio Vivo (113): quando a seção aparece. Tudo nulo = sempre. */
  dias: number[] | null;
  hora_de: string | null;
  hora_ate: string | null;
  horario_especial: boolean;
  /** 120: o vídeo da abertura da seção no Cardápio Vivo (ganha da foto). */
  video_url?: string | null;
  video_capa_url?: string | null;
  /** 121: a seção abre com tela própria no Cardápio Vivo. */
  abertura?: boolean;
};

export type Subcategoria = Secao & { id_categoria: number; itens: ItemDoCatalogo[] };

export type Categoria = Secao & {
  subcategorias: Subcategoria[];
  /** Os produtos pendurados DIRETO na categoria — subcategoria é opcional. */
  itens: ItemDoCatalogo[];
};

export type Conteudo = { id_catalogo: number; categorias: Categoria[] };

export type ProdutoDisponivel = {
  id: number;
  codigo: string;
  nome: string;
  um_estoque: string | null;
  foto_url: string | null;
  informacao_adicional: string | null;
};

export const conteudo = (id: number) =>
  api.get<Conteudo>(`/catalogos/${id}/conteudo`);

/** ⚠️ **Só ativos e vendidos no PDV** — quem filtra é o servidor. */
export const produtosDisponiveis = (busca: string) =>
  api.get<ProdutoDisponivel[]>(
    `/catalogos/produtos-disponiveis${busca ? `?busca=${encodeURIComponent(busca)}` : ""}`,
  );

export type GravarSecao = { nome: string; descricao: string | null; ordem: number };

export const criarCategoria = (idCatalogo: number, corpo: GravarSecao) =>
  api.post<Categoria>(`/catalogos/${idCatalogo}/categorias`, corpo);

export const atualizarCategoria = (id: number, corpo: GravarSecao) =>
  api.put<Secao>(`/catalogos/categorias/${id}`, corpo);

/** 🔑 A resposta diz QUANTOS produtos saíram junto, para a tela avisar antes. */
export const excluirCategoria = (id: number) =>
  api.delete<{ message: string; itens_removidos: number }>(
    `/catalogos/categorias/${id}`,
  );

export const criarSubcategoria = (idCategoria: number, corpo: GravarSecao) =>
  api.post<Subcategoria>(`/catalogos/categorias/${idCategoria}/subcategorias`, corpo);

export const atualizarSubcategoria = (id: number, corpo: GravarSecao) =>
  api.put<Secao>(`/catalogos/subcategorias/${id}`, corpo);

export const excluirSubcategoria = (id: number) =>
  api.delete<{ message: string; itens_removidos: number }>(
    `/catalogos/subcategorias/${id}`,
  );

export type TipoDeSecao = "categoria" | "subcategoria";

export const enviarFotoDaSecao = (tipo: TipoDeSecao, id: number, arquivo: File) => {
  const corpo = new FormData();
  corpo.append("arquivo", arquivo);
  return api.upload<{ foto_url: string; foto_nome: string | null }>(
    `/catalogos/secoes/${tipo}/${id}/foto`, corpo,
  );
};

export const removerFotoDaSecao = (tipo: TipoDeSecao, id: number) =>
  api.delete<{ foto_url: null }>(`/catalogos/secoes/${tipo}/${id}/foto`);

export const vincularProduto = (
  idCategoria: number,
  corpo: { id_produto: number; id_subcategoria?: number | null },
) => api.post<{ id: number; produto: string; message: string }>(
  `/catalogos/categorias/${idCategoria}/itens`, corpo,
);

/** 🔑 Mover não é tirar e pôr: o item leva destaque, esgotado, objetivo e margem. */
export const moverItem = (id: number, lugar: { id_categoria: number; id_subcategoria: number | null }) =>
  api.put<{ message: string }>(`/catalogos/itens/${id}/lugar`, lugar);

export const desvincularProduto = (id: number) =>
  api.delete<{ message: string }>(`/catalogos/itens/${id}`);

/**
 * A nova ordem de uma lista, INTEIRA.
 *
 * 🔑 Mandar só o que se moveu deixaria o servidor adivinhando o resto, e dois
 * cliques rápidos chegariam fora de ordem — a segunda gravação partiria de um
 * estado que a primeira já mudou.
 */
export const reordenarItens = (ordens: { id: number; ordem: number }[]) =>
  api.put<{ message: string }>("/catalogos/itens/ordem", ordens);

/**
 * A ordem das SEÇÕES, renumerada inteira (10, 20, 30…).
 *
 * ⚠️ Não há rota de lote para seção: a ordem viaja na própria gravação dela, que
 * pede nome e descrição junto. As seções de um cardápio são poucas, e uma chamada
 * por seção é o preço de não abrir uma rota nova para o que já existe.
 */
export async function reordenarSecoes(tipo: TipoDeSecao, secoes: Secao[]) {
  const gravar = tipo === "categoria" ? atualizarCategoria : atualizarSubcategoria;
  for (const [n, s] of secoes.entries()) {
    const ordem = (n + 1) * 10;
    if (s.ordem !== ordem) await gravar(s.id, { nome: s.nome, descricao: s.descricao, ordem });
  }
}

/* ===========================================================================
   O PRATO — o que é do PRODUTO e se edita de dentro do cardápio
   ---------------------------------------------------------------------------
   🔑 **Decisão do dono (15/10/2026):** foto, descrição e nome de vitrine são do
   PRODUTO, e valem em todo cardápio em que ele estiver. A gaveta do prato só
   evita a ida e volta ao cadastro; as rotas são as do produto, com a permissão
   dele (`cadastros.produtos`).
   =========================================================================== */

/** ⚠️ Só os dois campos: o PUT do produto grava o que VEIO (`exclude_unset`). */
export const gravarVitrine = (
  idProduto: number,
  corpo: { nome_catalogo: string | null; informacao_adicional: string | null },
) => api.put<{ message: string }>(`/produtos/${idProduto}`, corpo);

export const enviarFotoDoProduto = (idProduto: number, arquivo: File) => {
  const corpo = new FormData();
  corpo.append("arquivo", arquivo);
  return api.upload<{ foto_url: string; foto_nome: string | null }>(
    `/produtos/${idProduto}/foto`, corpo,
  );
};

export const removerFotoDoProduto = (idProduto: number) =>
  api.delete<{ message: string }>(`/produtos/${idProduto}/foto`);
