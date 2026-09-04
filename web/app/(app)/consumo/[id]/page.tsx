"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Cartao, Etiqueta, Vazio } from "@/components/ui";
import { dataBr } from "../../vendas/tipos";

/**
 * Um ciclo de consumo: o recibo por pessoa.
 *
 * ⚠️ **Ciclo FECHADO mostra o recibo CONGELADO**, não um recálculo. Recalcular
 * faria o documento do pagamento mudar quando alguém corrigisse uma venda
 * antiga — e o valor cobrado na época deixaria de ser respondível. Ciclo aberto
 * mostra o que está caindo agora, que por definição ainda muda.
 */

type Linha = {
  id_pessoa: number;
  pessoa: string;
  cupons: number;
  itens: number;
  total_cheio: number;
  desconto: number;
  total: number;
};

type Resposta = {
  periodo: {
    id: number; nome: string | null; inicio: string; fim: string;
    status: "ABERTO" | "FECHADO"; fechado_em: string | null; observacao: string | null;
  };
  linhas: Linha[];
  total: number;
  total_cheio: number;
  desconto: number;
};

export default function PaginaPeriodoConsumo() {
  const { id } = useParams<{ id: string }>();
  const [dados, setDados] = useState<Resposta | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    api
      .get<Resposta>(`/consumo/periodos/${id}`)
      .then(setDados)
      .finally(() => setCarregando(false));
  }, [id]);

  if (carregando) return <p className="text-suave">carregando…</p>;
  if (!dados) return <Vazio>Período não encontrado.</Vazio>;

  const { periodo, linhas } = dados;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/consumo" className="link-voltar">
          períodos de consumo
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          {periodo.nome || `${dataBr(periodo.inicio)} a ${dataBr(periodo.fim)}`}
        </h1>
        <p className="mt-1 text-suave">
          {dataBr(periodo.inicio)} a {dataBr(periodo.fim)} ·{" "}
          {periodo.status === "ABERTO" ? (
            <Etiqueta cor="erva">aberto</Etiqueta>
          ) : (
            <Etiqueta cor="neutro">fechado</Etiqueta>
          )}
        </p>
        {periodo.status === "ABERTO" && (
          <p className="mt-1 text-[13px] text-suave">
            Os números abaixo ainda mudam: é o que está em aberto agora.
          </p>
        )}
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Cartao titulo="Valor cheio">
          <p className="text-[26px] font-bold tabular-nums">{reais(dados.total_cheio)}</p>
        </Cartao>
        <Cartao titulo="Desconto">
          <p className="text-[26px] font-bold tabular-nums">{reais(dados.desconto)}</p>
        </Cartao>
        <Cartao titulo={periodo.status === "FECHADO" ? "Cobrado" : "A cobrar"}>
          <p className="text-[26px] font-bold tabular-nums">{reais(dados.total)}</p>
        </Cartao>
      </div>

      <Cartao titulo={`${linhas.length} pessoa(s)`}>
        {!linhas.length ? (
          <Vazio>Nenhum consumo neste ciclo.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Pessoa</th>
                  <th className="num">Cupons</th>
                  <th className="num">Itens</th>
                  <th className="num">Cheio</th>
                  <th className="num">Desconto</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {linhas.map((l) => (
                  <tr key={l.id_pessoa}>
                    <td>
                      <Link href={`/fornecedores/${l.id_pessoa}`} className="link-registro">
                        {l.pessoa}
                      </Link>
                    </td>
                    <td className="num tabular-nums">{l.cupons}</td>
                    <td className="num tabular-nums">{l.itens}</td>
                    <td className="num tabular-nums text-suave">{reais(l.total_cheio)}</td>
                    <td className="num tabular-nums">{reais(l.desconto)}</td>
                    <td className="num font-semibold tabular-nums">{reais(l.total)}</td>
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
