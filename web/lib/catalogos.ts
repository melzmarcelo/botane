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
};

/** O vocabulário vem do SERVIDOR: manter a lista aqui seria a segunda cópia. */
export type Opcoes = { origens: string[]; situacoes: Situacao[] };

/** ⚠️ Só o rótulo é daqui. O valor é do servidor, e é ele que manda. */
export const ROTULO_SITUACAO: Record<Situacao, string> = {
  RASCUNHO: "Rascunho",
  ATIVO: "Ativo",
  INATIVO: "Inativo",
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
  codigo: string;
  /** 🔑 **O produto pode ter sido desativado DEPOIS de entrar no cardápio.** A
   *  tela precisa marcá-lo — senão a casa não descobre que publicou algo que
   *  saiu de linha. */
  ativo: boolean;
  foto_url: string | null;
  informacao_adicional: string | null;
  um_estoque: string | null;
  ordem: number;
};

export type Secao = {
  id: number;
  nome: string;
  descricao: string | null;
  foto_url: string | null;
  foto_nome: string | null;
  ordem: number;
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

export const desvincularProduto = (id: number) =>
  api.delete<{ message: string }>(`/catalogos/itens/${id}`);
