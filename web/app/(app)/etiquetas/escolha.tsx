"use client";

import { CONSERVACOES, EVENTOS, type Conservacao, type Evento, type Regra } from "@/lib/etiquetas";

/**
 * O que aconteceu e como vai ser guardado — dois toques, os botões grandes da bancada.
 *
 * 🔑 A conservação que o produto tem regra aparece com o prazo ("3 dias"); a que não
 * tem continua escolhível, e aí a tela pede a validade.
 */
export default function EscolhaDoEvento({
  evento,
  aoEvento,
  conservacao,
  aoConservacao,
  regras,
  travado,
}: {
  evento: Evento;
  aoEvento: (e: Evento) => void;
  conservacao: Conservacao | null;
  aoConservacao: (c: Conservacao) => void;
  regras: Regra[];
  travado: boolean;
}) {
  const prazo = (c: Conservacao) => {
    const r = regras.find((x) => x.conservacao === c);
    if (!r) return "sem regra";
    return `${r.prazo} ${r.unidade === "HORAS" ? (r.prazo > 1 ? "horas" : "hora") : (r.prazo > 1 ? "dias" : "dia")}`;
  };
  const botao = (ativo: boolean) =>
    `rounded-[10px] border px-3 py-3 text-left ${ativo
      ? "border-[var(--color-erva)] bg-[var(--color-erva-claro)]"
      : "border-[var(--color-linha)] hover:border-[var(--color-erva)]"}`;

  return (
    <div className="flex flex-col gap-4">
      <fieldset disabled={travado}>
        <legend className="rotulo-campo mb-1.5">O que aconteceu</legend>
        <div className="grid grid-cols-3 gap-2" role="radiogroup">
          {EVENTOS.map((e) => (
            <button key={e.v} type="button" role="radio" aria-checked={evento === e.v}
                    className={botao(evento === e.v)} onClick={() => aoEvento(e.v)}>
              <b className="block text-[15px]">{e.verbo}</b>
              <span className="text-[12px] text-suave">{e.r}</span>
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className="rotulo-campo mb-1.5">Conservação</legend>
        <div className="grid grid-cols-3 gap-2" role="radiogroup">
          {CONSERVACOES.map((c) => (
            <button key={c.v} type="button" role="radio" aria-checked={conservacao === c.v}
                    className={botao(conservacao === c.v)} onClick={() => aoConservacao(c.v)}>
              <b className="block text-[15px]">{c.r}</b>
              <span className="text-[12px] text-suave">{prazo(c.v)}</span>
            </button>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
