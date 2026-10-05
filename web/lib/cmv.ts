/**
 * CMV — camada de service (regra da casa: página não chama `api`).
 * O painel nasceu chamando a API direto; o que entra novo mora aqui.
 */
import { api } from "@/lib/api";

export type PendenciaDoFechamento = {
  chave: string;
  /** `distorce` muda o CMV do período; `atencao` só pede conferência. */
  peso: "distorce" | "atencao";
  titulo: string;
  quantidade: number;
  detalhe: string;
  /** Onde se resolve. */
  href: string;
  valor: number | null;
};

export type ConferenciaDoFechamento = {
  inicio: string;
  fim: string;
  rotulo: string;
  itens: PendenciaDoFechamento[];
  /** Quantas das pendências mudam o número do período. */
  distorcem: number;
  limpo: boolean;
};

/**
 * O que ainda distorce o CMV real do recorte que o PAINEL mostra — a mesma
 * lista, para quem lê o número (permissão do painel, não a de fechar).
 */
export const conferirPeriodo = (inicio: string, fim: string) =>
  api.get<Omit<ConferenciaDoFechamento, "rotulo">>(
    `/cmv/conferencia?inicio=${inicio}&fim=${fim}`,
  );

/**
 * O que ainda distorce o período que se vai fechar. `competencia` é qualquer
 * dia dentro dele — o tamanho do período é o servidor quem diz, como no
 * fechamento.
 */
export const conferirFechamento = (competencia: string) =>
  api.get<ConferenciaDoFechamento>(
    `/cmv/fechamentos/conferencia?competencia=${encodeURIComponent(competencia)}`,
  );
