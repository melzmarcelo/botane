"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

import { pct as pctDaCasa } from "@/lib/numeros";
/**
 * O relatório de sentar com o fornecedor.
 *
 * Ordena pelo **impacto em reais**, não pelo percentual: 8% num item que entra
 * toda semana dói mais que 60% no que se compra uma vez por trimestre.
 *
 * ⚠️ **"Onde o custo pesa" saiu daqui** (16/09/2026, protótipo aprovado pelo
 * dono). Ele era a mesma conta do CMV quebrada por setor ou categoria, escondido
 * dentro desta aba e com dois eixos; virou a aba **Quebra**, com seis, comandada
 * pelo "Ver por" do alto da tela. Manter os dois seria manter duas telas
 * respondendo à mesma pergunta — e uma delas ficaria para trás.
 */

type Preco = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  compras: number;
  menor: number;
  maior: number;
  quantidade: number;
  primeiro: number;
  ultimo: number;
  variacao_pct: number;
  impacto: number;
  economia_possivel: number;
  data_ultimo: string | null;
  fornecedor_ultimo: string | null;
  fornecedor_mais_barato: string | null;
};

type Compra = {
  data: string;
  numero: string | null;
  fornecedor: string | null;
  quantidade: number;
  preco: number;
  variacao_pct: number | null;
};

// ⚠️ Variação leva SINAL, e o sinal faz parte da leitura: "+3,2%" e "3,2%"
// dizem coisas diferentes. Só o "+" é daqui — as casas vêm da casa.
const pct = (n: number) => `${n > 0 ? "+" : ""}${pctDaCasa(n)}`;
const dataBr = (d: string) => new Date(d + "T00:00").toLocaleDateString("pt-BR");

export default function RelatoriosDono({ inicio, fim }: { inicio: string; fim: string }) {
  const [precos, setPrecos] = useState<Preco[] | null>(null);
  const [aberto, setAberto] = useState<number | null>(null);
  const [serie, setSerie] = useState<Compra[] | null>(null);

  const carregar = useCallback(async () => {
    setPrecos(null);
    setPrecos(
      await api.get<Preco[]>(`/cmv/precos?inicio=${inicio}&fim=${fim}`).catch(() => []));
  }, [inicio, fim]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function abrir(id: number) {
    if (aberto === id) {
      setAberto(null);
      return;
    }
    setAberto(id);
    setSerie(null);
    setSerie(await api.get<Compra[]>(`/cmv/precos/${id}`).catch(() => []));
  }

  return (
    <div className="flex flex-col gap-6">
      <Cartao
        titulo="O que subiu de preço"
        descricao="Ordenado pelo impacto em reais no volume comprado — não pelo percentual."
      >
        {!precos ? (
          <Carregando />
        ) : !precos.length ? (
          <Vazio>
            Nenhum insumo com duas compras ou mais no período — sem duas notas não há variação
            a mostrar.
          </Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th className="num">Compras</th>
                  <th className="num">De</th>
                  <th className="num">Para</th>
                  <th className="num">Variação</th>
                  <th className="num">Impacto</th>
                  <th>Mais barato com</th>
                </tr>
              </thead>
              <tbody>
                {precos.map((p) => (
                  <tr key={p.id_produto}>
                    <td>
                      <button className="text-left" onClick={() => void abrir(p.id_produto)}>
                        <span className="link-registro">{p.produto}</span>
                        <span className="block text-[12.5px] text-suave">
                          {aberto === p.id_produto ? "esconder as compras" : "ver cada compra"}
                        </span>
                      </button>
                      {aberto === p.id_produto && (
                        <div className="mt-2 border-l-2 border-linha pl-3">
                          {!serie ? (
                            <Carregando />
                          ) : (
                            <ul className="flex flex-col gap-1 text-[13px]">
                              {serie.map((c, i) => (
                                <li key={i} className="flex flex-wrap gap-x-3 text-suave">
                                  <span className="mono">{dataBr(c.data)}</span>
                                  <span className="mono">{reais(Number(c.preco))}</span>
                                  <span>{c.fornecedor ?? "—"}</span>
                                  {c.numero && <span className="mono">NF {c.numero}</span>}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="num mono text-suave">{p.compras}</td>
                    <td className="num mono text-suave">{reais(Number(p.primeiro))}</td>
                    <td className="num mono">{reais(Number(p.ultimo))}</td>
                    <td className="num">
                      <Etiqueta cor={Number(p.variacao_pct) > 0 ? "alerta" : "erva"}>
                        {pct(Number(p.variacao_pct))}
                      </Etiqueta>
                    </td>
                    <td
                      className={`num mono font-semibold ${
                        Number(p.impacto) > 0 ? "text-erro" : "text-erva"
                      }`}
                    >
                      {reais(Number(p.impacto))}
                    </td>
                    <td className="text-[13.5px]">
                      {p.fornecedor_mais_barato ?? "—"}
                      {Number(p.economia_possivel) > 0.5 && (
                        <span className="block text-[12.5px] text-suave">
                          daria {reais(Number(p.economia_possivel))} de economia
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>
    </div>
  );
}
