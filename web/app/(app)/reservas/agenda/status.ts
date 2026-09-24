/**
 * O que cada status da reserva diz e permite — num lugar só, porque a lista, a
 * linha do tempo e o detalhe mostram a mesma reserva e têm de falar igual.
 */

/** O que cada status permite fazer em seguida — espelha `TRANSICOES` no servidor.
 *  ⚠️ Quem DECIDE é o servidor: isto só escolhe que botões mostrar. Oferecer um
 *  caminho que ele recusa seria pior que não oferecer nenhum. */
export const ADIANTE: Record<string, { para: string; rotulo: string; perigo?: boolean }[]> = {
  PENDENTE: [
    { para: "CONFIRMADA", rotulo: "confirmar" },
    { para: "CANCELADA", rotulo: "cancelar", perigo: true },
  ],
  CONFIRMADA: [
    { para: "CHEGOU", rotulo: "chegou" },
    { para: "NAO_COMPARECEU", rotulo: "não veio", perigo: true },
    { para: "CANCELADA", rotulo: "cancelar", perigo: true },
  ],
  CHEGOU: [{ para: "ENCERRADA", rotulo: "encerrar" }],
  ENCERRADA: [],
  CANCELADA: [],
  NAO_COMPARECEU: [],
};

export const ROTULO: Record<string, string> = {
  PENDENTE: "aguardando", CONFIRMADA: "confirmada", CHEGOU: "chegou",
  ENCERRADA: "encerrada", CANCELADA: "cancelada", NAO_COMPARECEU: "não veio",
};

export const COR: Record<string, "neutro" | "erva" | "alerta"> = {
  PENDENTE: "alerta", CONFIRMADA: "erva", CHEGOU: "erva",
  ENCERRADA: "neutro", CANCELADA: "neutro", NAO_COMPARECEU: "alerta",
};

/** Remarcar é para quem ainda não sentou — ver o comentário na lista. */
export const podeRemarcar = (status: string) => status === "PENDENTE" || status === "CONFIRMADA";
