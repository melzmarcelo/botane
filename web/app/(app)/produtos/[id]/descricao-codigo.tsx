"use client";

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { renomearCodigo } from "@/lib/produto-codigos";
import type { CodigoExterno } from "./codigos";

/**
 * A célula "O que é lá" de Vinculados: a descrição gravada no vínculo, o que a nota
 * mais nova diz desse código e — para quem edita — a correção do texto.
 *
 * 🔑 **O caso do PÃO BOTANE** (23/10/2026, relatado pelo dono): o recebimento no Omie
 * veio associado a "COSTELA PONTA DESOSSADA KG". O vínculo ao pão estava certo, o
 * rótulo não, e ficava preso: a descrição congela na nota em que se vinculou.
 * ⚠️ **Só o texto muda.** A conciliação casa pelo código, nunca pela descrição.
 */
export default function DescricaoDoCodigo({
  idProduto,
  c,
  podeEditar,
  aoMudar,
}: {
  idProduto: number;
  c: CodigoExterno;
  podeEditar: boolean;
  aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [texto, setTexto] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const recente =
    c.descricao_recente && c.descricao_recente.trim() !== (c.descricao_externa ?? "").trim()
      ? c.descricao_recente
      : null;

  async function gravar() {
    const t = (texto ?? "").trim();
    if (!t) {
      aviso.erro("Escreva o que este código é.");
      return;
    }
    setSalvando(true);
    try {
      const r = await renomearCodigo(idProduto, c, t);
      aviso.sucesso(r.message);
      setTexto(null);
      aoMudar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar a descrição");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      {texto === null ? (
        <>
          {c.descricao_externa ?? "—"}
          {podeEditar && (
            <button
              type="button"
              className="link-acao ml-2 text-[12.5px]"
              aria-label={`corrigir a descrição de ${c.codigo}`}
              onClick={() => setTexto(c.descricao_externa ?? "")}
            >
              corrigir
            </button>
          )}
        </>
      ) : (
        <span className="flex items-center gap-2">
          <input
            className="campo"
            aria-label={`descrição de ${c.codigo}`}
            maxLength={200}
            autoFocus
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            // ⚠️ **preventDefault no Enter**: a tabela mora dentro do <form> do
            // cadastro, e o Enter daqui SALVAVA o produto inteiro junto.
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); void gravar(); }
              if (e.key === "Escape") { e.preventDefault(); setTexto(null); }
            }}
          />
          <button type="button" className="btn btn-secundario" disabled={salvando}
                  aria-busy={salvando} onClick={() => void gravar()}>
            {salvando ? "…" : "Gravar"}
          </button>
          <button type="button" className="link-acao" onClick={() => setTexto(null)}>
            cancelar
          </button>
        </span>
      )}
      {c.fornecedor && <span className="block text-[12.5px] text-suave">{c.fornecedor}</span>}
      {recente && (
        <span className="block text-[12.5px] text-suave">
          Na última nota ({c.descricao_recente_em?.split("-").reverse().join("/")}): {recente}
        </span>
      )}
    </>
  );
}
