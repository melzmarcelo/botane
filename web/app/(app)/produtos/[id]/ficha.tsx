"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Etiqueta } from "@/components/ui";
import { FichaDoProduto, fichasDoProduto } from "@/lib/fichas";

/**
 * A ficha técnica de um produto de produção própria: se existe, em que estado
 * está, e o caminho até ela.
 *
 * 🔑 **Pedido do dono (26/10/2026)**: no cadastro do produzido, mostrar quando falta
 * a ficha, quando ela não está homologada e quando está, com acesso direto. Veio da
 * conferência do local PRODUÇÃO: 26 bebidas com saldo negativo porque a venda baixou
 * o produto e não produziu — e a produção na hora só acontece com ficha HOMOLOGADA.
 * Até aqui, só se descobria isso abrindo a lista de fichas e procurando o nome.
 *
 * ⚠️ **Só a homologada vale** (`estoque.produzir`, `producao_agenda.producao_da_venda`):
 * rascunho não produz, não baixa insumo na venda e não entra no custo da produção.
 * Por isso rascunho aparece em ALERTA, igual à falta de ficha, e não em verde.
 */
export default function FichaDoProdutoResumo({
  idProduto,
  naHora,
  podeCriar,
}: {
  idProduto: number;
  naHora: boolean;
  podeCriar: boolean;
}) {
  const [fichas, setFichas] = useState<FichaDoProduto[] | null>(null);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    let vivo = true;
    fichasDoProduto(idProduto)
      .then((l) => vivo && setFichas([...l].sort((a, b) => b.versao - a.versao)))
      .catch(() => vivo && setFalhou(true));
    return () => {
      vivo = false;
    };
  }, [idProduto]);

  // Quem não vê fichas (403) não ganha um aviso sobre o que não pode abrir.
  if (falhou || fichas === null) return null;

  const homologada = fichas.find((f) => f.status === "HOMOLOGADA");
  const rascunho = fichas.find(
    (f) => f.status === "RASCUNHO" && (!homologada || f.versao > homologada.versao),
  );
  const situacao = homologada ? "homologada" : rascunho ? "rascunho" : "sem_ficha";

  // O que a falta de homologada CUSTA, dito no idioma do modo de produção.
  const consequencia = naHora
    ? "A venda baixa o produto, mas não consome os insumos — o saldo fica negativo e o custo da venda fica sem base."
    : "Sem ela não há como produzir nem calcular o custo pela receita.";

  return (
    <div
      id="ficha-do-produto"
      data-situacao={situacao}
      className={`mt-4 rounded border p-3.5 ${
        homologada ? "border-erva/40 bg-erva-claro" : "border-alerta/40"
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="rotulo">Ficha técnica</span>
        {homologada && <Etiqueta cor="erva">homologada · v{homologada.versao}</Etiqueta>}
        {rascunho && <Etiqueta cor="alerta">rascunho · v{rascunho.versao}</Etiqueta>}
        {situacao === "sem_ficha" && <Etiqueta cor="alerta">sem ficha</Etiqueta>}
        <span className="ml-auto flex flex-wrap gap-3">
          {homologada && (
            <Link href={`/fichas/${homologada.id}`} className="link-acao" id="abrir-ficha">
              Abrir a ficha
            </Link>
          )}
          {rascunho && (
            <Link href={`/fichas/${rascunho.id}`} className="link-acao" id="abrir-rascunho">
              {homologada ? "Abrir o rascunho" : "Abrir a ficha"}
            </Link>
          )}
          {situacao === "sem_ficha" && podeCriar && (
            <Link href={`/fichas/nova?produto=${idProduto}`} className="link-acao" id="criar-ficha">
              Criar a ficha
            </Link>
          )}
        </span>
      </div>
      <p className="mt-1.5 text-[13px] leading-snug text-suave">
        {homologada
          ? rascunho
            ? `Vale a v${homologada.versao}. A v${rascunho.versao} ainda é rascunho e só passa a valer quando for homologada.`
            : "É ela que a produção e a venda usam."
          : rascunho
            ? `Ainda não vale: só a ficha homologada produz. ${consequencia}`
            : fichas.length
              ? `Só há versões arquivadas. ${consequencia}`
              : `Este produto ainda não tem ficha. ${consequencia}`}
      </p>
    </div>
  );
}
