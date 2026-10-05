"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Aviso, Etiqueta } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import {
  conferirFechamento,
  type ConferenciaDoFechamento,
  type PendenciaDoFechamento,
} from "@/lib/cmv";

/**
 * A lista das pendências — uma LINHA por ponto, com o detalhe recolhido.
 * Serve à janela de fechar e à faixa do painel: a mesma lista em dois lugares
 * tem de ter a mesma cara, senão parece que são duas conferências.
 */
export function ListaDePendencias({ itens }: { itens: PendenciaDoFechamento[] }) {
  return (
    <ul className="mt-2 flex flex-col gap-px overflow-hidden rounded-xl border border-linha bg-linha">
      {itens.map((i) => (
        <li key={i.chave} className="bg-superficie px-3.5 py-2.5">
          <details>
            <summary className="flex cursor-pointer flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-[14px]">
              <span className="font-semibold">
                <Etiqueta cor={i.peso === "distorce" ? "alerta" : "neutro"}>{i.quantidade}</Etiqueta>{" "}
                {i.titulo}
              </span>
              <span className="flex items-baseline gap-3">
                {i.valor !== null && <span className="tabular-nums">{reais(i.valor)}</span>}
                <Link href={i.href} className="link-acao text-[13.5px]">
                  resolver
                </Link>
              </span>
            </summary>
            <p className="mt-1.5 text-[13.5px] leading-snug text-suave">{i.detalhe}</p>
          </details>
        </li>
      ))}
    </ul>
  );
}

/**
 * A conferência que aparece ANTES do botão de fechar o período.
 *
 * 🔑 **Por que existe (05/10/2026).** Fechar congela a apuração e a
 * movimentação que vai ao contador — e congelava o que estivesse lá. No ar,
 * um mês com R$ 235 mil de receita mostrava CMV de R$ 3 mil porque 94 notas
 * não tinham sido lançadas, e nada no caminho de quem clicava em "Fechar"
 * dizia isso.
 *
 * ⚠️ **Avisa, não impede.** Fechar com pendência é decisão de quem fecha; o
 * que não pode é ser decisão tomada sem ver. O servidor registra na auditoria
 * com que pendências o período foi fechado.
 * ⚠️ **Falha ao conferir não esconde o botão**: a conferência é ajuda, e uma
 * ajuda fora do ar não pode impedir o fechamento.
 */
export default function ConferenciaDoFechamentoLista({
  competencia,
  aoSaber,
}: {
  competencia: string;
  /** Quantas pendências distorcem o número — a tela muda o rótulo do botão. */
  aoSaber: (distorcem: number) => void;
}) {
  const [r, setR] = useState<ConferenciaDoFechamento | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let vivo = true;
    conferirFechamento(competencia)
      .then((d) => {
        if (!vivo) return;
        setR(d);
        aoSaber(d.distorcem);
      })
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar a conferência"));
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [competencia]);

  if (erro) {
    return (
      <Aviso tipo="erro">
        Não foi possível conferir o período antes de fechar ({erro}). Dá para fechar assim
        mesmo, mas sem a lista do que está pendente.
      </Aviso>
    );
  }
  if (!r) return <p className="rotulo mt-4">conferindo o período…</p>;
  if (r.limpo) {
    return <Aviso tipo="ok">Nada pendente neste período: a conta está pronta para congelar.</Aviso>;
  }

  return (
    <div className="mt-4">
      <p className="text-[14px] font-semibold">
        Antes de fechar — {r.itens.length} ponto(s) neste período
      </p>
      {/* ⚠️ Uma LINHA por ponto, com o detalhe recolhido: a janela de confirmar
          tem os botões no fim do corpo, e uma lista aberta os empurrava para
          baixo da dobra — botão que rolou para fora é botão que não existe. */}
      <ListaDePendencias itens={r.itens} />
      {r.distorcem > 0 && (
        <p className="mt-3 text-[13.5px] text-suave">
          Os pontos em destaque <b className="text-tinta">mudam o CMV deste período</b>. Fechar
          assim congela o número como está; resolver depois exige reabrir.
        </p>
      )}
    </div>
  );
}
