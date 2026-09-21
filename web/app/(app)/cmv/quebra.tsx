"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { pct } from "@/lib/numeros";
import { Carregando, Cartao, Vazio } from "@/components/ui";

/**
 * O CMV do período quebrado pelo recorte que a pessoa escolheu.
 *
 * 🔑 **Protótipo aprovado pelo dono (16/09/2026):** *"podendo ter a opção de ser
 * pela empresa, por loja, por local de estoque, setor, categoria, produto"*. Era
 * "Onde o custo pesa", com dois eixos e escondido dentro da aba dos relatórios
 * do dono; passa a ser aba própria, com seis eixos, comandada pelo "Ver por" do
 * alto da tela.
 *
 * 🔑 **Não é rateio — é a MESMA conta restrita a cada linha**, e a soma FECHA
 * com o CMV do período. É essa propriedade que dá sentido ao corte: sem ela, a
 * tabela seria uma divisão arbitrária de um total, e ninguém poderia agir sobre
 * uma linha. A bateria cobra isso em todos os eixos.
 *
 * ⚠️ **A barra é proposital**: a participação se lê de relance e o número exato
 * fica ao lado, para quem quiser conferir. Um número sozinho obriga a comparar
 * quatro casas decimais de cabeça.
 */
type Linha = {
  grupo: string;
  estoque_inicial: number;
  compras: number;
  estoque_final: number;
  cmv: number;
  perdas: number;
  produtos: number;
  participacao_pct: number;
};

export const EIXOS = {
  loja: "loja",
  local: "prateleira",
  setor: "setor",
  categoria: "categoria",
  grupo: "grupo do CMV",
  produto: "produto",
} as const;

export type Eixo = keyof typeof EIXOS;

export default function Quebra({
  inicio,
  fim,
  eixo,
  escopo,
  cmvDoPeriodo,
}: {
  inicio: string;
  fim: string;
  eixo: Eixo;
  escopo: "loja" | "empresa";
  /** Para dizer, ao pé, que a soma fecha — é a prova de que o corte é corte. */
  cmvDoPeriodo: number;
}) {
  const [linhas, setLinhas] = useState<Linha[] | null>(null);
  const [erro, setErro] = useState("");
  // ⚠️ O eixo `produto` traz mais de mil linhas nesta base. Cresce em blocos:
  // quem investiga lê de cima para baixo, e trocar de página perde o fio.
  const [quantas, setQuantas] = useState(40);

  const carregar = useCallback(async () => {
    setLinhas(null);
    setErro("");
    try {
      setLinhas(
        await api.get<Linha[]>(
          `/cmv/por-grupo?inicio=${inicio}&fim=${fim}&agrupar=${eixo}&escopo=${escopo}`,
        ),
      );
      setQuantas(40);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [inicio, fim, eixo, escopo]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const soma = (linhas ?? []).reduce((s, l) => s + Number(l.cmv), 0);
  const maior = Math.max(1, ...(linhas ?? []).map((l) => Math.abs(Number(l.cmv))));

  return (
    <Cartao
      titulo={`CMV por ${EIXOS[eixo]}`}
      descricao="A mesma conta do período, restrita a cada linha — não é rateio."
    >
      {erro ? (
        <p className="text-[14px] text-erro">{erro}</p>
      ) : !linhas ? (
        <Carregando />
      ) : !linhas.length ? (
        <Vazio>Nenhum movimento no período para este recorte.</Vazio>
      ) : (
        <>
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th className="capitalize">{EIXOS[eixo]}</th>
                  <th className="num">Estoque inicial</th>
                  <th className="num">Compras</th>
                  <th className="num">Estoque final</th>
                  <th className="num">CMV</th>
                  <th>Participação</th>
                  <th className="num">%</th>
                </tr>
              </thead>
              <tbody>
                {linhas.slice(0, quantas).map((l) => (
                  <tr key={l.grupo}>
                    <td>
                      <span className="font-medium">{l.grupo}</span>
                      <span className="block text-[12.5px] text-suave">
                        {l.produtos} produto(s)
                        {Number(l.perdas) > 0 && ` · ${reais(l.perdas)} de perda`}
                      </span>
                    </td>
                    <td className="num text-suave">{reais(l.estoque_inicial)}</td>
                    <td className="num text-suave">{reais(l.compras)}</td>
                    <td className="num text-suave">{reais(l.estoque_final)}</td>
                    <td className="num font-semibold">{reais(l.cmv)}</td>
                    <td>
                      {/* A barra usa o MAIOR da lista como régua, não o total:
                          com cem linhas, todas somem contra o total. */}
                      <span className="block h-2 min-w-[90px] overflow-hidden rounded-full bg-superficie2">
                        <span
                          className="block h-full rounded-full bg-erva"
                          style={{
                            width: `${Math.min(
                              100,
                              (Math.abs(Number(l.cmv)) / maior) * 100,
                            )}%`,
                          }}
                        />
                      </span>
                    </td>
                    <td className="num">{pct(l.participacao_pct)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-linha2 font-semibold">
                  <td>Total</td>
                  <td colSpan={3}></td>
                  <td className="num">{reais(soma)}</td>
                  <td></td>
                  <td className="num">100%</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3 text-[13px] text-suave">
            {linhas.length > quantas && (
              <button
                type="button"
                className="link-acao"
                onClick={() => setQuantas((n) => n + 60)}
              >
                ver mais {linhas.length - quantas} linha(s)
              </button>
            )}
            {/* 🔑 **A prova, escrita.** A soma das linhas ser o CMV do período é
                o que separa este corte de um rateio — e é a primeira coisa que
                alguém confere ao desconfiar do número. */}
            <span className="ml-auto">
              {Math.abs(soma - cmvDoPeriodo) < 0.05 ? (
                <>
                  a soma das linhas fecha com o CMV do período (
                  <b className="mono text-tinta">{reais(cmvDoPeriodo)}</b>)
                </>
              ) : (
                <span className="text-alerta">
                  a soma das linhas difere do CMV do período em{" "}
                  <b className="mono">{reais(soma - cmvDoPeriodo)}</b>
                </span>
              )}
            </span>
          </div>
        </>
      )}
    </Cartao>
  );
}
