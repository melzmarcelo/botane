"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { baixarLotesAbertos, lotes as buscarLotes, ROTULO_SITUACAO, type Formas, type Lote,
         type SituacaoLote } from "@/lib/receber";
import { dataBr } from "../vendas/tipos";

const FILTROS: { valor: SituacaoLote | ""; nome: string }[] = [
  { valor: "ABERTO", nome: "Em cobrança" },
  { valor: "RECEBIDO", nome: "Recebidos" },
  { valor: "CANCELADO", nome: "Cancelados" },
  { valor: "", nome: "Todos" },
];

export function EtiquetaDoLote({ status }: { status: SituacaoLote }) {
  return (
    <Etiqueta cor={status === "ABERTO" ? "alerta" : status === "RECEBIDO" ? "erva" : "neutro"}>
      {ROTULO_SITUACAO[status]}
    </Etiqueta>
  );
}

/**
 * Os lotes de cobrança, o mais novo primeiro. Abre em "em cobrança": é o que se
 * acompanha — o que já foi mandado e ainda não voltou.
 */
export default function ListaDeLotes({ versao }: { versao: number }) {
  const [filtro, setFiltro] = useState<SituacaoLote | "">("ABERTO");
  const [dados, setDados] = useState<{ lotes: Lote[]; formas: Formas } | null>(null);
  const [erro, setErro] = useState("");
  const [baixando, setBaixando] = useState(false);
  const aviso = useAviso();

  useEffect(() => {
    let vivo = true;
    setErro("");
    buscarLotes(filtro || undefined)
      .then((r) => vivo && setDados(r))
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar os lotes"));
    return () => {
      vivo = false;
    };
  }, [filtro, versao]);

  const lista = dados?.lotes ?? [];

  // 🔑 Todos os em cobrança num PDF só, cada lote na sua página (23/10/2026).
  async function baixarTodos() {
    setBaixando(true);
    try {
      await baixarLotesAbertos();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar o PDF dos lotes");
    } finally {
      setBaixando(false);
    }
  }

  return (
    <Cartao
      titulo="Lotes de cobrança"
      descricao="Um por pessoa. Abra o lote para imprimir o relatório, dar baixa ou tirar um documento."
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap gap-2" role="tablist">
            {FILTROS.map((f) => (
              <button
                key={f.valor || "todos"}
                role="tab"
                aria-selected={filtro === f.valor}
                data-filtro-lote={f.valor || "todos"}
                className={`btn ${filtro === f.valor ? "btn-primario" : "btn-secundario"}`}
                onClick={() => setFiltro(f.valor)}
              >
                {f.nome}
              </button>
            ))}
          </div>
          {filtro === "ABERTO" && lista.length > 0 && (
            <button
              id="receber-pdf-abertos"
              className="btn btn-secundario sm:ml-auto"
              disabled={baixando}
              onClick={baixarTodos}
            >
              {baixando ? "Gerando…" : `PDF dos ${lista.length} lote(s) em cobrança`}
            </button>
          )}
        </div>
        {erro ? (
          <Aviso tipo="erro">{erro}</Aviso>
        ) : !dados ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>Nenhum lote nesta situação.</Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela" id="receber-lotes">
              <thead>
                <tr>
                  <th>Lote</th>
                  <th>Pessoa</th>
                  <th>Documentos</th>
                  <th className="num">Docs</th>
                  <th className="num">Total</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((l) => (
                  <tr key={l.id} data-lote={l.id}>
                    <td className="whitespace-nowrap">
                      <Link href={`/receber/lotes/${l.id}`} className="link-registro">
                        Nº {l.id}
                      </Link>
                      <span className="block text-[12.5px] text-suave">
                        {dataBr(l.criado_em.slice(0, 10))}
                      </span>
                    </td>
                    <td className="min-w-[160px]">{l.pessoa}</td>
                    <td className="whitespace-nowrap text-suave">
                      {l.desde ? `${dataBr(l.desde)} a ` : "até "}{dataBr(l.ate)}
                    </td>
                    <td className="num tabular-nums">{l.cupons}</td>
                    <td className="num font-semibold tabular-nums">{reais(l.total)}</td>
                    <td className="whitespace-nowrap">
                      <EtiquetaDoLote status={l.status} />
                      {l.status === "RECEBIDO" && l.recebido_em && (
                        <span className="block text-[12.5px] text-suave">
                          {dataBr(l.recebido_em)}
                          {l.forma_pagamento ? ` · ${dados.formas[l.forma_pagamento]}` : ""}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Cartao>
  );
}
