"use client";

import Link from "next/link";
import type { ReactNode } from "react";

/**
 * O nome do produto como caminho para o cadastro dele.
 *
 * 🔑 **Pedido do dono (06/10/2026):** *"estou na precificação e quero ver o
 * cadastro de produto, tenho que copiar o nome, ir lá, voltar, buscar"*. O nome
 * já estava na tela e o `id` já vinha na linha; faltava só o caminho. Em
 * dezesseis grades o nome era texto, e em outras tantas já era link — cada uma
 * escrita à mão.
 *
 * ⚠️ **A volta é a do navegador** (o botão Voltar do cadastro usa o histórico):
 * a tela de origem reabre com o filtro e a página que estavam na URL, e a
 * rolagem é devolvida por `components/rolagem.tsx`.
 *
 * ⚠️ **Sem `id`, vira texto.** Linha de venda sem vínculo e item de nota ainda
 * não conciliado não têm cadastro para abrir — um link que leva a "produto
 * não encontrado" é pior que nenhum.
 */
export default function LinkProduto({
  id,
  children,
  className = "",
}: {
  id: number | null | undefined;
  children: ReactNode;
  /** Classes de peso/tamanho do lugar onde ele está. */
  className?: string;
}) {
  if (!id) return <span className={className}>{children}</span>;
  return (
    <Link href={`/produtos/${id}`} className={`link-registro ${className}`.trim()}
          title="abrir o cadastro do produto"
          // ⚠️ Há grades em que a LINHA inteira é clicável (a precificação abre a
          // simulação). O clique no nome é para ir ao cadastro, não para as duas coisas.
          onClick={(e) => e.stopPropagation()}>
      {children}
    </Link>
  );
}
