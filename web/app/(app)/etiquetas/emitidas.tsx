"use client";

import Link from "next/link";

import { useAviso } from "@/components/aviso-flutuante";
import { Cartao } from "@/components/ui";
import { dataHora, imprimir, numero, type Etiqueta } from "@/lib/etiquetas";

/** O que acabou de sair — com o código de cada uma, e a reimpressão se o rolo falhou. */
export default function Emitidas({ etiquetas }: { etiquetas: Etiqueta[] }) {
  const aviso = useAviso();
  const reimprimir = (ids: number[]) =>
    imprimir(ids, true).catch((e) => aviso.erro(e instanceof Error ? e.message : "Falha ao imprimir"));

  return (
    <Cartao
      titulo="Acabaram de sair"
      acao={<button className="btn btn-secundario" onClick={() => void reimprimir(etiquetas.map((e) => e.id))}>
        Imprimir de novo
      </button>}
    >
      <div className="grid-rolante">
        <table className="tabela">
          <thead>
            <tr><th>Código</th><th>Produto</th><th>Vence</th><th>Qtd</th><th /></tr>
          </thead>
          <tbody>
            {etiquetas.map((e) => (
              <tr key={e.id}>
                <td className="mono"><Link className="link-acao" href={`/etiquetas/e/${e.codigo}`}>{e.codigo}</Link></td>
                <td>{e.produto}</td>
                <td className="mono">{dataHora(e.vence_em)}</td>
                <td className="mono">{e.quantidade ? `${numero(e.quantidade)} ${e.um ?? ""}` : "—"}</td>
                <td className="text-right">
                  <button className="link-acao" onClick={() => void reimprimir([e.id])}>reimprimir</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Cartao>
  );
}
