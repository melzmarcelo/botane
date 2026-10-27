"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Aviso, Cartao, Etiqueta } from "@/components/ui";
import { COR_PREVENTIVA, doProduto, type DoProduto } from "@/lib/patrimonio";

/**
 * Os bens de um produto do tipo Patrimônio: cada item físico cadastrado, onde está e a
 * preventiva — e quantos ainda faltam cadastrar.
 *
 * 🔑 **Pedido do dono (27/10/2026)**: *"caso entre um produto novo como patrimônio, o
 * usuário deverá cadastrar ele como um novo bem — aí vinculamos todo o sistema"*. A régua
 * é o saldo do produto: 3 no estoque e 1 bem = faltam 2. "Cadastrar bem" abre o Novo bem
 * já com o produto e a última entrada dele.
 */
export default function BensDoProduto({ idProduto, podeCadastrar }: {
  idProduto: number;
  podeCadastrar: boolean;
}) {
  const [d, setD] = useState<DoProduto | null>(null);

  useEffect(() => {
    let vivo = true;
    doProduto(idProduto).then((x) => vivo && setD(x)).catch(() => {});
    return () => { vivo = false; };
  }, [idProduto]);

  if (!d) return null;
  const novo = `/patrimonio/novo?produto=${idProduto}`;
  return (
    <Cartao
      titulo="Bens deste produto"
      descricao={`${d.ativos} bem(ns) cadastrado(s) · ${d.saldo} no estoque desta loja`}
      acao={podeCadastrar ? <Link href={novo} className="btn btn-secundario" id="produto-novo-bem">Cadastrar bem</Link> : undefined}
    >
      {d.faltam > 0 && (
        <div className="mb-3">
          <Aviso tipo="erro">
            Faltam <b>{d.faltam}</b> bem(ns): o estoque tem {d.saldo}
            {d.onde ? ` (${d.onde})` : ""} e só {d.ativos} {d.ativos === 1 ? "está cadastrado" : "estão cadastrados"}.
            Cada item precisa do cadastro dele para ter plaqueta e manutenção.
          </Aviso>
        </div>
      )}
      {!d.bens.length ? (
        <p className="text-[14px] text-suave">Nenhum bem ligado a este produto ainda.</p>
      ) : (
        <div className="grid-rolante">
          <table className="tabela" id="produto-bens">
            <thead><tr><th>Plaqueta</th><th>Setor · local</th><th>Situação</th><th>Preventiva</th></tr></thead>
            <tbody>
              {d.bens.map((b) => (
                <tr key={b.id}>
                  <td className="mono">
                    <Link href={`/patrimonio/${b.id}`} className="link-registro font-semibold">{b.codigo}</Link>
                    {b.numero_serie && <span className="block text-[12px] text-suave">série {b.numero_serie}</span>}
                  </td>
                  <td>{b.setor ?? "—"}{b.local && <span className="text-suave"> · {b.local}</span>}</td>
                  <td>{b.situacao_txt}</td>
                  <td>
                    {b.status_preventiva === "FORA" ? "—" : (
                      <Etiqueta cor={COR_PREVENTIVA[b.status_preventiva] ?? "neutro"}>{b.preventiva_txt}</Etiqueta>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Cartao>
  );
}
