import type { Metadata } from "next";
import { notFound } from "next/navigation";
import CardapioVivo from "@/components/cardapio-vivo/cardapio-vivo";

/**
 * A pré-visualização do Cardápio Vivo, aberta num iframe da tela de gestão.
 * ⚠️ Com login (a rota da API exige `catalogos.ver`): o token vem do mesmo navegador.
 * `previa` é segmento ESTÁTICO, e por isso ganha de `/c/[loja]`.
 */
export const metadata: Metadata = { title: "Pré-visualização", robots: { index: false, follow: false } };

export default async function Previa({ params }: { params: Promise<{ catalogo: string }> }) {
  const id = Number((await params).catalogo);
  if (!Number.isInteger(id) || id <= 0) notFound();
  return <CardapioVivo loja={0} token={null} idCatalogoPrevia={id} />;
}
