"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Cartao } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { pct, qtd } from "@/lib/numeros";
import { filaDeFichas, type FilaDeFichas, type ItemDaFila } from "@/lib/fichas";

/**
 * Por onde começar: os produtos mais VENDIDOS que ainda não sabem o próprio custo.
 *
 * 🔑 **Por que existe (05/10/2026).** Com centenas de produtos sem ficha, a
 * pendência era uma lista alfabética do cadastro. Quem tem uma tarde para fazer
 * fichas precisa saber que cinco delas cobrem um terço do faturamento — a ordem
 * aqui é a da receita, e cada linha diz a cobertura a que ela leva.
 *
 * ⚠️ **Some sozinha quando não há o que fazer** (ou quando a rota falha): é
 * ajuda, e ajuda vazia ou fora do ar não ocupa a tela nem esconde a lista.
 * ⚠️ **A frase do rodapé não é enfeite**: o custo do item vendido é congelado,
 * então a ficha de hoje custeia as vendas de amanhã — sem dizer isso, quem faz a
 * ficha e volta ao painel acha que não funcionou.
 */
export default function FilaDeFichasCartao({ podeEditar }: { podeEditar: boolean }) {
  const [fila, setFila] = useState<FilaDeFichas | null>(null);

  useEffect(() => {
    let vivo = true;
    filaDeFichas()
      .then((f) => vivo && setFila(f))
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, []);

  if (!fila || fila.itens.length === 0) return null;

  return (
    <Cartao
      titulo="Por onde começar"
      descricao={
        `Os mais vendidos dos últimos ${fila.dias} dias que ainda não têm custo` +
        (fila.cobertura_pct !== null
          ? ` — hoje ${pct(fila.cobertura_pct)} da receita está coberta`
          : "")
      }
    >
      <div className="grid-rolante">
        <table className="tabela">
          <thead>
            <tr>
              <th>Produto</th>
              <th>O que falta</th>
              <th className="num">Vendido</th>
              {fila.receita !== null && <th className="num">Receita</th>}
              <th className="num">Peso</th>
              <th className="num">Cobertura até aqui</th>
            </tr>
          </thead>
          <tbody>
            {fila.itens.map((i) => (
              <tr key={i.id_produto}>
                <td>
                  <Link href={`/produtos/${i.id_produto}`} className="link-registro">
                    {i.nome}
                  </Link>
                  {i.codigo && <span className="mono block text-[12px] text-suave">{i.codigo}</span>}
                </td>
                <td>
                  <OQueFalta item={i} podeEditar={podeEditar} />
                </td>
                <td className="num tabular-nums">{qtd(i.quantidade)}</td>
                {fila.receita !== null && (
                  <td className="num tabular-nums">{i.receita !== null ? reais(i.receita) : "—"}</td>
                )}
                <td className="num tabular-nums">{pct(i.participacao_pct)}</td>
                <td className="num tabular-nums font-semibold">{pct(i.cobertura_acumulada_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="prosa mt-3 text-[13.5px] text-suave">
        {fila.produtos > fila.itens.length &&
          `Mostrando os ${fila.itens.length} que mais pesam, de ${fila.produtos} vendidos sem custo. `}
        A ficha passa a custear as vendas feitas a partir de agora; as que já aconteceram
        guardam o custo que se sabia no dia.
      </p>
    </Cartao>
  );
}

/** O próximo passo de cada linha — e o caminho até ele, para quem pode fazer. */
function OQueFalta({ item, podeEditar }: { item: ItemDaFila; podeEditar: boolean }) {
  if (item.falta === "sem_ficha") {
    return podeEditar ? (
      <Link href={`/fichas/nova?produto=${item.id_produto}`} className="link-acao">
        criar a ficha
      </Link>
    ) : (
      <span>Ficha técnica</span>
    );
  }
  if (item.falta === "ficha_sem_custo") {
    return item.id_ficha ? (
      <Link href={`/fichas/${item.id_ficha}`} className="link-acao">
        custo de algum ingrediente
      </Link>
    ) : (
      <span>Custo de algum ingrediente</span>
    );
  }
  return (
    <Link href={`/produtos/${item.id_produto}`} className="link-acao">
      custo de compra
    </Link>
  );
}
