"use client";

import { type ColunaBI, formatar } from "@/lib/bi";

/**
 * 🔑 **A prévia em FOLHA** (layout novo, fase 3 — 05/11/2026): o relatório como sai no papel, antes
 * de imprimir. Serve aos dois tipos — o do catálogo (já vem formatado pelo servidor, igual ao PDF)
 * e o personalizado do Estúdio BI (formatado aqui pelo `formato` de cada coluna).
 */
export default function Folha({
  titulo, subtitulo, colunas, linhas, resumo, rodape,
}: {
  titulo: string;
  subtitulo?: string;
  colunas: { rotulo: string; num?: boolean }[];
  linhas: string[][];
  resumo?: [string, string][];
  rodape?: string;
}) {
  return (
    <div className="bg-superficie2 p-4 sm:p-6" id="folha-relatorio">
      <div className="mx-auto max-w-[920px] rounded-md bg-superficie px-5 py-6 shadow-[0_2px_10px_rgba(0,0,0,.06)] sm:px-9 sm:py-8">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b-2 border-tinta pb-4">
          <div>
            <p className="rotulo text-erva">Relatório</p>
            <h2 className="mt-1 text-[20px] font-extrabold">{titulo}</h2>
            {subtitulo && <p className="mt-0.5 text-[13px] text-suave">{subtitulo}</p>}
          </div>
          {!!resumo?.length && (
            <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 text-right text-[12.5px]">
              {resumo.map(([k, v]) => (
                <div key={k} className="contents"><dt className="text-suave">{k}</dt><dd className="mono font-semibold">{v}</dd></div>
              ))}
            </dl>
          )}
        </div>
        {!linhas.length ? (
          <p className="py-8 text-center text-[14px] text-suave">Nenhuma linha neste recorte.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela tabela-compacta">
              <thead>
                <tr>{colunas.map((c, i) => <th key={i} className={c.num ? "num" : undefined}>{c.rotulo}</th>)}</tr>
              </thead>
              <tbody>
                {linhas.map((l, i) => (
                  <tr key={i}>{l.map((v, j) => <td key={j} className={colunas[j]?.num ? "num mono" : undefined}>{v}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rodape && <p className="mt-4 text-[12.5px] text-suave">{rodape}</p>}
      </div>
    </div>
  );
}

/** As colunas e linhas de um resultado do BI, já como texto para a folha. */
export function folhaDoBI(colunas: ColunaBI[], linhas: (string | number | null)[][]) {
  return {
    colunas: colunas.map((c) => ({ rotulo: c.rotulo, num: c.tipo === "med" })),
    linhas: linhas.map((l) => l.map((v, i) => formatar(v, colunas[i].formato))),
  };
}
