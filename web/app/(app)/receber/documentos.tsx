"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { documentosEmAberto, gerarLotes } from "@/lib/receber";
import type { LinhaDocumento } from "../vendas/por-pessoa/tabelas-documento";
import { dataBr } from "../vendas/tipos";

/**
 * Os documentos em aberto de UMA pessoa — para conferir e gerar o lote só com os
 * marcados (o "desmarcar algum" da proposta aceita pelo dono, 22/10/2026).
 *
 * ⚠️ Mesma consulta do relatório e do arquivo do lote (`consumo_pessoa.apurar`): o que
 * se marca aqui é o que o PDF mandado à pessoa vai mostrar.
 */
export default function DocumentosDaPessoa({
  pessoa,
  de,
  ate,
  gerir,
  aoFechar,
  aoGerar,
}: {
  pessoa: { id: number; nome: string };
  de: string;
  ate: string;
  gerir: boolean;
  aoFechar: () => void;
  aoGerar: () => void;
}) {
  const aviso = useAviso();
  const [docs, setDocs] = useState<LinhaDocumento[] | null>(null);
  const [erro, setErro] = useState("");
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    let vivo = true;
    setDocs(null);
    documentosEmAberto(pessoa.id, de || undefined, ate)
      .then((r) => {
        if (!vivo) return;
        setDocs(r.documentos);
        setMarcados(new Set(r.documentos.map((d) => d.id_venda)));
      })
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar"));
    return () => {
      vivo = false;
    };
  }, [pessoa.id, de, ate]);

  const escolhidos = (docs ?? []).filter((d) => marcados.has(d.id_venda));
  const total = escolhidos.reduce((s, d) => s + Number(d.total), 0);

  function marcar(id: number) {
    setMarcados((m) => {
      const n = new Set(m);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  async function gerar() {
    setOcupado(true);
    try {
      const r = await gerarLotes({
        ate,
        de: de || null,
        ids_pessoa: [pessoa.id],
        ids_venda: escolhidos.map((d) => d.id_venda),
      });
      aviso.sucesso(r.message);
      aoGerar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar o lote");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao
      titulo={`Documentos em aberto — ${pessoa.nome}`}
      descricao={`Até ${dataBr(ate)}${de ? `, desde ${dataBr(de)}` : ""}. Desmarque o que não deve entrar no lote.`}
      acao={
        <button className="link-acao text-[13px]" onClick={aoFechar}>
          fechar
        </button>
      }
    >
      {erro ? (
        <Aviso tipo="erro">{erro}</Aviso>
      ) : !docs ? (
        <Carregando />
      ) : !docs.length ? (
        <Vazio>Nada em aberto até esta data.</Vazio>
      ) : (
        <div className="flex flex-col gap-4" id="receber-documentos">
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  {gerir && <th className="w-8"></th>}
                  <th>Data</th>
                  <th>Documento</th>
                  <th>Itens</th>
                  <th className="num">Cheio</th>
                  <th className="num">A cobrar</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.id_venda}>
                    {gerir && (
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Incluir ${d.documento ?? d.id_venda}`}
                          data-doc={d.id_venda}
                          checked={marcados.has(d.id_venda)}
                          onChange={() => marcar(d.id_venda)}
                        />
                      </td>
                    )}
                    <td className="whitespace-nowrap">
                      <Link href={`/vendas/${d.id_venda}`} className="link-registro">
                        {dataBr(d.data)}
                      </Link>
                    </td>
                    <td className="mono">{d.documento || "—"}</td>
                    <td className="text-[13px] text-suave">
                      {(d.itens_do_documento ?? [])
                        .map((i) => `${Number(i.quantidade)} × ${i.produto ?? "—"}`)
                        .join(", ")}
                    </td>
                    <td className="num tabular-nums text-suave">{reais(d.total_cheio)}</td>
                    <td className="num font-semibold tabular-nums">{reais(d.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {gerir && (
            <div className="flex flex-wrap items-center gap-3">
              <button
                id="receber-gerar-marcados"
                className="btn btn-primario"
                disabled={!escolhidos.length || ocupado}
                aria-busy={ocupado}
                onClick={gerar}
              >
                Gerar lote com {escolhidos.length} documento(s)
              </button>
              <span className="text-[14px] text-suave">
                total <b className="tabular-nums">{reais(total)}</b>
              </span>
            </div>
          )}
        </div>
      )}
    </Cartao>
  );
}
