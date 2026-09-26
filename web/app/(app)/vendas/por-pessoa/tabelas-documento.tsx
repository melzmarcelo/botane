"use client";

import { Fragment } from "react";
import Link from "next/link";

import { reais } from "@/lib/cadastros";
import { dataBr } from "../tipos";

/**
 * Consumo por pessoa AGRUPADO POR DOCUMENTO — um cupom por linha, ou cada cupom com os
 * itens embaixo.
 *
 * 🔑 **Pedido do dono (26/09/2026):** *"criar mais opção de impressão, agrupado por
 * documento, agrupado por documento e destacando os itens; ter estas possibilidades na
 * tela também."* É como o funcionário confere a cobrança: "este cupom é meu".
 * ⚠️ Os números vêm prontos do servidor (`services/consumo_pessoa`), a MESMA consulta do
 * arquivo — a tela e o PDF entregue não podem discordar.
 */

export type ItemDoDocumento = {
  produto: string | null;
  produto_codigo: string | null;
  quantidade: number;
  unitario_cheio: number;
  unitario: number;
  total_cheio: number;
  desconto: number;
  total: number;
};

export type LinhaDocumento = {
  id_venda: number;
  data: string;
  hora: string | null;
  documento: string | null;
  id_pessoa: number;
  pessoa: string;
  itens: number;
  total_cheio: number;
  desconto: number;
  total: number;
  /** Só no "com os itens". */
  itens_do_documento?: ItemDoDocumento[];
};

function Cabecalho({ comItens }: { comItens: boolean }) {
  return (
    <thead>
      <tr>
        <th>Data</th>
        <th>Documento</th>
        <th>{comItens ? "Pessoa / Produto" : "Pessoa"}</th>
        <th className="num">{comItens ? "Qtd" : "Itens"}</th>
        {comItens && <th className="num">Cobrado un.</th>}
        <th className="num">Cheio</th>
        <th className="num">Desconto</th>
        <th className="num">A cobrar</th>
      </tr>
    </thead>
  );
}

function LinhaDoCupom({ d, comItens }: { d: LinhaDocumento; comItens: boolean }) {
  return (
    <tr className={comItens ? "bg-[var(--color-superficie2)] font-semibold" : ""}>
      <td className="whitespace-nowrap">
        <Link href={"/vendas/" + d.id_venda} className="link-registro">
          {dataBr(d.data)}
        </Link>
        {d.hora && <span className="block text-[12px] font-normal text-suave">{d.hora.slice(0, 5)}</span>}
      </td>
      <td className="mono">{d.documento || "—"}</td>
      <td>{d.pessoa}</td>
      <td className="num tabular-nums">{d.itens}</td>
      {comItens && <td />}
      <td className="num tabular-nums text-suave">{reais(d.total_cheio)}</td>
      <td className="num tabular-nums">{reais(d.desconto)}</td>
      <td className="num tabular-nums">{reais(d.total)}</td>
    </tr>
  );
}

export function TabelaPorDocumento({
  linhas,
  comItens,
}: {
  linhas: LinhaDocumento[];
  comItens: boolean;
}) {
  return (
    <div className="grid-rolante">
      <table className="tabela">
        <Cabecalho comItens={comItens} />
        <tbody>
          {linhas.map((d) => (
            <Fragment key={d.id_venda}>
              <LinhaDoCupom d={d} comItens={comItens} />
              {comItens &&
                (d.itens_do_documento ?? []).map((i, n) => (
                  <tr key={d.id_venda + "-" + n}>
                    <td />
                    <td />
                    {/* O recuo diz "este item é do cupom de cima", sem repetir o cupom. */}
                    <td className="pl-6">
                      {i.produto ?? "—"}
                      {i.produto_codigo && (
                        <span className="ml-1 text-[12px] text-suave">{i.produto_codigo}</span>
                      )}
                    </td>
                    <td className="num tabular-nums">{Number(i.quantidade)}</td>
                    <td className="num tabular-nums">{reais(i.unitario)}</td>
                    <td className="num tabular-nums text-suave">{reais(i.total_cheio)}</td>
                    <td className="num tabular-nums">{reais(i.desconto)}</td>
                    <td className="num tabular-nums">{reais(i.total)}</td>
                  </tr>
                ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
