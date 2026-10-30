"use client";

/**
 * Uma linha de prato no editor do cardápio.
 *
 * 🔑 **Enxuta de propósito** (reforma de 15/10/2026). A linha antiga tinha até
 * oito controles — destaque, esgotado, dois seletores, subir, descer, tirar e o
 * link —, e num cardápio de sessenta pratos o nome, que é o que se procura,
 * sumia no meio dos botões. Agora ela MOSTRA (foto, nome de vitrine, preço, as
 * marcas e o que falta) e só deixa à mão o que se faz em sequência: subir e
 * descer. Todo o resto mora na gaveta, que abre no clique.
 */

import { urlArquivo } from "@/lib/api";
import { reais } from "@/lib/numeros";
import type { ItemDoCatalogo } from "@/lib/catalogos";

type Props = {
  item: ItemDoCatalogo;
  primeiro: boolean;
  ultimo: boolean;
  podeEditar: boolean;
  aoAbrir: () => void;
  aoMover: (passo: number) => void;
};

/** O que falta para o prato sair bem no cardápio — o que a linha avisa. */
export function faltasDo(i: ItemDoCatalogo): string[] {
  const f: string[] = [];
  if (!i.ativo) f.push("produto inativo");
  if (!i.foto_url && !i.tem_video) f.push("sem foto");
  if (!i.informacao_adicional?.trim()) f.push("sem descrição");
  if (i.preco === null) f.push("sem preço");
  return f;
}

export default function LinhaDoPrato({ item: i, primeiro, ultimo, podeEditar, aoAbrir, aoMover }: Props) {
  const nome = i.nome_catalogo || i.produto;
  const faltas = faltasDo(i);
  return (
    <li className="flex items-center gap-3 bg-superficie py-2">
      {/* 🔑 A linha INTEIRA abre a gaveta (foto e nome): é o alvo grande do toque. */}
      <button type="button" onClick={aoAbrir} aria-label={`abrir ${nome}`}
              className="flex min-w-0 flex-1 items-center gap-3 text-left">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded border border-linha bg-superficie2">
          {i.foto_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={urlArquivo(i.foto_url) ?? undefined} alt="" className="h-full w-full object-cover" />
          ) : (
            <span className="text-[10px] text-suave">{i.tem_video ? "vídeo" : "sem"}</span>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14.5px] font-medium hover:text-erva">
            {i.destaque && <span className="text-alerta" title="em destaque">★ </span>}
            {nome}
          </span>
          {/* ⚠️ O nome do cadastro em cinza: quem veio procurar o produto
              reconhece por ele, mas o cardápio mostra o de vitrine. */}
          <span className="block truncate text-[12.5px] text-suave">
            {i.tipo === "ESCOLHA"
              ? `item de escolha: ${(i.escolhas ?? []).map((o) => o.nome).join(", ")}`
              : <>{i.nome_catalogo ? `${i.produto} · ` : ""}{i.codigo}</>}
            {i.esgotado && <span className="font-semibold text-erro"> · esgotado{i.esgotado_ate ? " (volta sozinho)" : ""}</span>}
            {faltas.length > 0 && <span className="text-alerta"> · ⚠ {faltas.join(", ")}</span>}
          </span>
        </span>
        <span className="mono shrink-0 text-[13.5px]">
          {i.preco !== null ? `${i.tipo === "ESCOLHA" ? "a partir de " : ""}${reais(i.preco)}` : ""}
        </span>
      </button>
      {/* 🔑 **Subir e descer, não arrastar** — no toque o arrasto disputa com a
          rolagem. ⚠️ O primeiro não sobe e o último não desce: botão que não faz
          nada ensina a duvidar dos outros. */}
      {podeEditar && (
        <span className="flex shrink-0 gap-1">
          <button type="button" className="link-acao" disabled={primeiro}
                  aria-label={`subir ${nome}`} onClick={() => aoMover(-1)}>↑</button>
          <button type="button" className="link-acao" disabled={ultimo}
                  aria-label={`descer ${nome}`} onClick={() => aoMover(1)}>↓</button>
        </span>
      )}
    </li>
  );
}
