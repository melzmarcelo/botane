/**
 * O catálogo — o cabeçalho do que a casa publica para o cliente.
 *
 * 🔑 **Camada de service, e não `api.get` solto na página** — regra da casa. A
 * tela conhece `listar`, `salvar` e `excluir`; a forma das rotas é assunto
 * daqui, e o dia em que ela mudar a página não fica sabendo.
 */
import { api } from "@/lib/api";

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
