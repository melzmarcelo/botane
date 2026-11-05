"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { pct, qtd, reais } from "@/lib/numeros";

/**
 * 🔑 **O Resumo ao lado do cadastro** (05/11/2026, pedido do dono: *"gostei como no protótipo
 * ficou o cadastro de produtos… com o resumo"*). O que se quer saber de relance ao abrir um
 * produto, sem trocar de aba: margem, custo, preço, saldo e mínimo, e se ele vai ao PDV.
 *
 * ⚠️ O PREÇO vem do formulário (o que está sendo digitado): a margem mexe enquanto se digita,
 * como no protótipo. O custo e o saldo vêm do servidor e se refazem a cada salvar (`recarga`).
 * ⚠️ Custo só para quem tem `estoque.saldos` — a mesma régua do bloco de custo da tela; sem a
 * chave, margem e custo nem aparecem (e a rota nem é chamada).
 * ⚠️ A margem é BRUTA (preço − custo) ÷ preço, antes de impostos e taxas: a de verdade, com a
 * configuração da loja, é a da Precificação.
 */
type Custo = { atual: number | null; provisorio: { custo_por_porcao: number } | null };
type Local = { quantidade: number };

export default function ResumoDoProduto({
  idProduto, preco, minimo, um, controlaEstoque, podeVerCusto, vaiAoPdv, recarga,
}: {
  idProduto: number;
  preco: number | null;
  minimo: number | null;
  um: string | null;
  controlaEstoque: boolean;
  podeVerCusto: boolean;
  vaiAoPdv: boolean;
  recarga: number;
}) {
  const [custo, setCusto] = useState<number | null>(null);
  const [provisorio, setProvisorio] = useState(false);
  const [saldo, setSaldo] = useState<number | null>(null);

  useEffect(() => {
    let vivo = true;
    if (podeVerCusto) {
      api.get<Custo>(`/produtos/${idProduto}/custo`).then((c) => {
        if (!vivo) return;
        // Sem custo apurado, o da ficha (por porção), como o bloco de custo já mostra.
        setCusto(c.atual ?? c.provisorio?.custo_por_porcao ?? null);
        setProvisorio(c.atual === null && !!c.provisorio);
      }).catch(() => {});
    }
    if (controlaEstoque) {
      api.get<Local[]>(`/produtos/${idProduto}/locais`).then((l) => {
        if (vivo) setSaldo(l.reduce((t, x) => t + Number(x.quantidade || 0), 0));
      }).catch(() => {});
    }
    return () => { vivo = false; };
  }, [idProduto, podeVerCusto, controlaEstoque, recarga]);

  const margem = preco && preco > 0 && custo !== null ? (preco - custo) / preco : null;
  const abaixo = controlaEstoque && saldo !== null && minimo !== null && minimo > 0 && saldo < minimo;
  const unidade = um ? ` ${um}` : "";

  return (
    <aside className="cartao flex flex-col gap-4 p-5" aria-label="Resumo do produto" id="resumo-produto">
      <h2 className="text-[15px] font-bold">Resumo</h2>
      {podeVerCusto && (
        <div>
          <div className="text-[12.5px] text-suave">Margem bruta</div>
          <div className={`mono text-[28px] font-extrabold leading-tight ${
            margem === null ? "text-suave" : margem < 0 ? "text-erro" : "text-erva"}`} data-resumo="margem">
            {margem === null ? "—" : pct(margem * 100)}
          </div>
          <div className="text-[12px] text-suave">antes de impostos e taxas</div>
        </div>
      )}
      <dl className="grid grid-cols-2 gap-3">
        {podeVerCusto && (
          <div>
            <dt className="text-[12.5px] text-suave">Custo{provisorio ? " (ficha)" : ""}</dt>
            <dd className="mono text-[16px] font-bold" data-resumo="custo">{custo === null ? "—" : reais(custo)}</dd>
          </div>
        )}
        <div>
          <dt className="text-[12.5px] text-suave">Preço</dt>
          <dd className="mono text-[16px] font-bold" data-resumo="preco">{preco === null ? "—" : reais(preco)}</dd>
        </div>
        {controlaEstoque && (
          <>
            <div>
              <dt className="text-[12.5px] text-suave">Saldo</dt>
              <dd className="mono text-[16px] font-bold" data-resumo="saldo">{saldo === null ? "—" : `${qtd(saldo)}${unidade}`}</dd>
            </div>
            <div>
              <dt className="text-[12.5px] text-suave">Mínimo</dt>
              <dd className="mono text-[16px] font-bold">{minimo ? `${qtd(minimo)}${unidade}` : "—"}</dd>
            </div>
          </>
        )}
      </dl>
      {abaixo && (
        <p className="flex gap-2.5 rounded-xl bg-alerta-claro p-3 text-[13px] font-semibold leading-snug text-alerta" data-resumo="abaixo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
               strokeLinecap="round" strokeLinejoin="round" aria-hidden className="flex-none">
            <path d="M12 3 2 20h20z M12 10v4 M12 17h.01" />
          </svg>
          Saldo abaixo do mínimo. Inclua no próximo pedido de compra.
        </p>
      )}
      <div className="h-px bg-linha" />
      {/* ⚠️ A cor nunca vai sozinha: o texto diz sim ou não. */}
      <p className="flex items-center gap-2 text-[13.5px]" data-resumo="pdv">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${vaiAoPdv ? "bg-erva" : "bg-linha2"}`} aria-hidden />
        {vaiAoPdv ? "Vende no PDV" : "Não vai ao PDV"}
      </p>
    </aside>
  );
}
