import { AbaOrdem, rotuloUrgencia, Urgencia } from "@/lib/ordens-compra";

/**
 * Os selos da lista (modelo "versão didática" do dono, 24/11/2026). Só com as cores da casa:
 * urgente no tom de erro, esta semana na erva, pode esperar neutro; e a situação no tom de alerta
 * enquanto espera compra.
 */

const pilula = "inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold";

const COR_URGENCIA: Record<Urgencia, string> = {
  HOJE: "bg-erro-claro text-erro",
  SEMANA: "bg-erva-claro text-erva",
  PODE_ESPERAR: "bg-superficie2 text-suave",
};

export function SeloUrgencia({ urgencia }: { urgencia: Urgencia }) {
  return (
    <span className={`${pilula} ${COR_URGENCIA[urgencia] ?? COR_URGENCIA.SEMANA}`} data-selo-urgencia={urgencia}>
      {rotuloUrgencia(urgencia)}
    </span>
  );
}

// 🔑 Aprovação (165): "Aguardando aprovação" neutro (ainda não é tarefa de quem compra),
// "Aguardando compra" no alerta, comprado na erva e recusado no tom de erro.
const SITUACAO: Record<AbaOrdem, [string, string]> = {
  AGUARDANDO: ["Aguardando aprovação", "bg-superficie2 text-tinta"],
  A_COMPRAR: ["Aguardando compra", "bg-alerta-claro text-alerta"],
  COMPRADO: ["Comprado", "bg-erva-claro text-erva"],
  RECUSADO: ["Recusado", "bg-erro-claro text-erro"],
};

export function SeloSituacao({ status }: { status: AbaOrdem }) {
  const [rotulo, cor] = SITUACAO[status] ?? SITUACAO.A_COMPRAR;
  return <span className={`${pilula} ${cor}`} data-selo-situacao={status}>{rotulo}</span>;
}
