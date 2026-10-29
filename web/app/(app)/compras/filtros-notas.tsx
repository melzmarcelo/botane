"use client";

import { useEstadoNaUrl } from "@/lib/estado-na-url";

/**
 * Os filtros da lista de notas (pedido do dono, 21/10/2026: "nas notas de entrada
 * poderia ter mais filtros: período, situação...").
 *
 * 🔑 **Tudo na URL**, como a busca: abrir uma nota e voltar devolve a lista filtrada.
 * 🔑 **"A lançar" é UMA escolha e DUAS situações** (importada + conciliada): é a
 * pergunta que se faz de verdade — o que ainda falta pôr no estoque.
 * ⚠️ O período é pela data de ENTRADA, e pela de emissão quando a nota não tem
 * entrada — a mesma regra do servidor (`coalesce`), que é quem filtra.
 */
export const SITUACOES: { valor: string; nome: string; status: string[] }[] = [
  { valor: "abertas", nome: "a lançar", status: ["IMPORTADA", "CONCILIADA"] },
  { valor: "IMPORTADA", nome: "importada", status: ["IMPORTADA"] },
  { valor: "CONCILIADA", nome: "conciliada", status: ["CONCILIADA"] },
  { valor: "LANCADA", nome: "lançada", status: ["LANCADA"] },
  { valor: "CANCELADA", nome: "cancelada", status: ["CANCELADA"] },
  { valor: "NAO_ENCONTRADA", nome: "não encontrada no Omie", status: ["NAO_ENCONTRADA"] },
];

const ORIGENS = [
  { valor: "OMIE", nome: "Omie" },
  { valor: "XML", nome: "XML" },
  { valor: "MANUAL", nome: "digitada" },
];

export function useFiltrosNotas() {
  const [situacao, setSituacao] = useEstadoNaUrl<string>("situacao", "");
  const [origem, setOrigem] = useEstadoNaUrl<string>("origem", "");
  const [de, setDe] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
  const [pendentes, setPendentes] = useEstadoNaUrl<boolean>("pendentes", false);

  /** Acrescenta os filtros a uma query — a da lista e a do total são a mesma. */
  function aplicar(q: URLSearchParams) {
    for (const s of SITUACOES.find((x) => x.valor === situacao)?.status ?? []) q.append("status", s);
    if (origem) q.set("origem", origem);
    if (de) q.set("inicio", de);
    if (ate) q.set("fim", ate);
    if (pendentes) q.set("pendentes", "true");
    return q;
  }

  const ativos = !!(situacao || origem || de || ate || pendentes);
  function limpar() {
    setSituacao("");
    setOrigem("");
    setDe("");
    setAte("");
    setPendentes(false);
  }

  return {
    situacao, setSituacao, origem, setOrigem, de, setDe, ate, setAte, pendentes, setPendentes,
    aplicar, ativos, limpar,
    /** O que muda o QUE a lista mostra — volta a paginação para a primeira página. */
    chaves: [situacao, origem, de, ate, pendentes],
  };
}

export type FiltrosNotas = ReturnType<typeof useFiltrosNotas>;

const LARGURA = { width: "auto" } as const;

export default function BarraDeFiltros({ f }: { f: FiltrosNotas }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 text-[13.5px]" id="notas-filtros">
      <select className="campo py-1" style={LARGURA} id="notas-situacao" aria-label="situação"
              value={f.situacao} onChange={(e) => f.setSituacao(e.target.value)}>
        <option value="">todas as situações</option>
        {SITUACOES.map((s) => <option key={s.valor} value={s.valor}>{s.nome}</option>)}
      </select>
      <select className="campo py-1" style={LARGURA} id="notas-origem" aria-label="origem"
              value={f.origem} onChange={(e) => f.setOrigem(e.target.value)}>
        <option value="">todas as origens</option>
        {ORIGENS.map((o) => <option key={o.valor} value={o.valor}>{o.nome}</option>)}
      </select>
      {/* ⚠️ `flex-wrap` (auditoria de 29/10/2026): os dois campos de data lado a lado passavam
          da largura do celular (427 px numa tela de 390). */}
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-suave">de</span>
        <input type="date" className="campo py-1" style={LARGURA} id="notas-de" aria-label="entrada de"
               value={f.de} max={f.ate || undefined} onChange={(e) => f.setDe(e.target.value)} />
        <span className="text-suave">até</span>
        <input type="date" className="campo py-1" style={LARGURA} id="notas-ate" aria-label="entrada até"
               value={f.ate} min={f.de || undefined} onChange={(e) => f.setAte(e.target.value)} />
      </span>
      <label className="flex items-center gap-1.5">
        <input type="checkbox" id="notas-pendentes" checked={f.pendentes}
               onChange={(e) => f.setPendentes(e.target.checked)} />
        só com item sem produto
      </label>
      {f.ativos && (
        <button type="button" className="link-acao text-[13px]" id="notas-limpar-filtros" onClick={f.limpar}>
          limpar filtros
        </button>
      )}
    </div>
  );
}
