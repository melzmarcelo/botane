"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Cartao, Etiqueta, Vazio } from "@/components/ui";

/**
 * Os lotes em estoque, **na ordem em que vão sair**.
 *
 * A ordem é a informação: quem separa a mercadoria precisa saber qual pote
 * pegar primeiro, e é exatamente a fila que o sistema segue sozinho na baixa.
 * Lote sem validade fica no fim — não se gasta o que não tem data na frente do
 * que vence.
 */

type Lote = {
  id: number;
  lote: string | null;
  validade: string | null;
  quantidade: number;
  produto: string;
  um_estoque: string | null;
  local: string;
  dias_restantes: number | null;
};

const qtd = (n: number | string) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

export default function LotesEmEstoque() {
  const [lotes, setLotes] = useState<Lote[] | null>(null);

  useEffect(() => {
    void api
      .get<Lote[]>("/estoque/lotes")
      .then(setLotes)
      .catch(() => setLotes([]));
  }, []);

  if (!lotes?.length) return null;

  return (
    <Cartao
      titulo="Lotes em estoque"
      descricao="Na ordem em que vão sair: o que vence antes sai antes."
    >
      <div className="overflow-x-auto">
        <table className="tabela">
          <thead>
            <tr>
              <th>Produto</th>
              <th>Lote</th>
              <th>Validade</th>
              <th className="num">Saldo</th>
              <th>Local</th>
            </tr>
          </thead>
          <tbody>
            {lotes.map((l) => {
              const dias = l.dias_restantes;
              return (
                <tr key={l.id}>
                  <td className="font-semibold">{l.produto}</td>
                  <td className="mono text-[13px]">{l.lote ?? "—"}</td>
                  <td>
                    {l.validade ? (
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="mono text-[13px]">
                          {new Date(l.validade + "T00:00").toLocaleDateString("pt-BR")}
                        </span>
                        {dias !== null && dias < 0 && <Etiqueta cor="alerta">vencido</Etiqueta>}
                        {dias !== null && dias >= 0 && dias <= 7 && (
                          <Etiqueta cor="alerta">{dias}d</Etiqueta>
                        )}
                      </span>
                    ) : (
                      <span className="text-suave">sem data — sai por último</span>
                    )}
                  </td>
                  <td className="num mono">
                    {qtd(l.quantidade)} {l.um_estoque ?? ""}
                  </td>
                  <td className="text-suave">{l.local}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!lotes.length && <Vazio>Nenhum lote identificado em estoque.</Vazio>}
    </Cartao>
  );
}
