"use client";

import Link from "next/link";

import { Carregando, Etiqueta as Selo, Vazio } from "@/components/ui";
import {
  COR_SITUACAO, ROTULO_SITUACAO, dataHora, numero, rotuloConservacao, rotuloEvento,
  type Etiqueta,
} from "@/lib/etiquetas";

/** A grade do painel. Ações só nas ativas: a baixada já disse o que aconteceu. */
export default function TabelaDeEtiquetas({
  lista, podeDescartar, aoUsar, aoUsarParte, aoDescartar, aoReimprimir,
}: {
  lista: Etiqueta[] | null;
  podeDescartar: boolean;
  aoUsar: (e: Etiqueta) => void;
  aoUsarParte: (e: Etiqueta) => void;
  aoDescartar: (e: Etiqueta) => void;
  aoReimprimir: (e: Etiqueta) => void;
}) {
  if (!lista) return <Carregando />;
  if (!lista.length) return <Vazio>Nenhuma etiqueta aqui.</Vazio>;
  return (
    <div className="grid-rolante">
      <table className="tabela">
        <thead>
          <tr>
            <th className="w-[90px]">Código</th>
            <th>Produto</th>
            <th className="w-[130px]">Vence</th>
            <th>Onde</th>
            <th className="w-[110px]">Qtd</th>
            <th className="w-[130px]">Situação</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {lista.map((e) => (
            <tr key={e.id}>
              <td className="mono">
                <Link className="link-acao" href={`/etiquetas/e/${e.codigo}`}>{e.codigo}</Link>
              </td>
              <td>
                {e.produto}
                <span className="block text-[12px] text-suave">
                  {rotuloEvento(e.evento)} {dataHora(e.feito_em)} · {rotuloConservacao(e.conservacao)}
                  {e.lote ? ` · lote ${e.lote}` : ""} · {e.responsavel}
                </span>
              </td>
              <td className="mono text-[13px]">{dataHora(e.vence_em)}</td>
              <td className="text-[13px]">{e.local ?? "—"}</td>
              <td className="mono text-[13px]">
                {e.quantidade ? `${numero(e.quantidade)} ${e.um ?? ""}` : "—"}
                {/* Pote já mexido: diz de quanto era. */}
                {e.quantidade && e.quantidade_inicial
                  && Number(e.quantidade_inicial) !== Number(e.quantidade) && (
                  <span className="block text-[11.5px] text-suave">
                    de {numero(e.quantidade_inicial)}
                  </span>
                )}
              </td>
              <td>
                <Selo cor={COR_SITUACAO[e.situacao]}>{ROTULO_SITUACAO[e.situacao]}</Selo>
                {e.status !== "ATIVA" && (
                  <span className="block text-[12px] text-suave">
                    {dataHora(e.baixada_em)}{e.baixada_por ? ` · ${e.baixada_por}` : ""}
                    {e.motivo ? ` · ${e.motivo}` : ""}
                  </span>
                )}
              </td>
              <td className="whitespace-nowrap text-right text-[13px]">
                {e.status === "ATIVA" && (
                  <span className="inline-flex gap-3">
                    {e.quantidade && Number(e.quantidade) > 0 && (
                      <button className="link-acao" onClick={() => aoUsarParte(e)}>usei parte</button>
                    )}
                    <button className="link-acao" onClick={() => aoUsar(e)}>usei tudo</button>
                    {podeDescartar && (
                      <button className="link-acao" onClick={() => aoDescartar(e)}>descartar</button>
                    )}
                    <button className="link-acao" onClick={() => aoReimprimir(e)}>reimprimir</button>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
