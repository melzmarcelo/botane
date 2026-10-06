import Link from "next/link";

/**
 * De um movimento de estoque para o documento que o gerou.
 *
 * 🔑 **Pedido do dono (06/10/2026):** *"da movimentação, com o número do
 * documento, a partir dali ir lá, ver, e voltar, continuando no mesmo
 * contexto"*. O razão já guardava de onde cada movimento veio (`origem_tipo` e
 * `origem_id`); a tela mostrava só o número, e achar a nota era copiar "NF
 * 6947", ir a Compras e buscar.
 *
 * ⚠️ **Só os tipos que TÊM tela própria.** Transferência entre prateleiras
 * aponta para o movimento do outro lado, o estorno para o movimento estornado e
 * o ajuste para o lote — nenhum deles tem página que se abra pelo número.
 * Produção também fica de fora: a tela `/producao/[id]` é a do item da AGENDA,
 * e o `origem_id` é o da produção feita.
 */
const TELAS: Record<string, { caminho: string; nome: string }> = {
  NOTA: { caminho: "/compras", nome: "nota" },
  VENDA: { caminho: "/vendas", nome: "venda" },
  INVENTARIO: { caminho: "/inventario", nome: "contagem" },
  REMESSA: { caminho: "/transferencias", nome: "remessa" },
};

/** O endereço do documento de origem, ou nulo quando não há tela para ele. */
export function hrefDaOrigem(tipo: string | null | undefined,
                             id: number | null | undefined): string | null {
  const tela = tipo ? TELAS[tipo] : undefined;
  return tela && id ? `${tela.caminho}/${id}` : null;
}

export default function LinkOrigem({
  tipo,
  id,
  documento,
}: {
  tipo: string | null | undefined;
  id: number | null | undefined;
  /** O número que a pessoa reconhece ("NF 6947"). Sem ele, o link diz o que abre. */
  documento: string | null | undefined;
}) {
  const href = hrefDaOrigem(tipo, id);
  const tela = tipo ? TELAS[tipo] : undefined;
  if (!href || !tela) {
    return documento ? <>{documento}</> : <span className="text-suave">—</span>;
  }
  return (
    <Link href={href} className="link-registro" title={`abrir a ${tela.nome}`}>
      {documento || `ver ${tela.nome}`}
    </Link>
  );
}
