"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Aviso, Carregando } from "@/components/ui";
import Voltar from "@/components/voltar";
import { definirUnidade, unidadeAtual } from "@/lib/api";
import { porCodigo } from "@/lib/patrimonio";

/**
 * O que a plaqueta abre: o QR leva a `/patrimonio/b/PAT-0001`, e daqui à ficha do bem.
 *
 * ⚠️ **Vale a loja DO BEM**: quem lê a plaqueta pelo celular pode estar com outra loja
 * escolhida — a ficha seria "não encontrado". Troca o seletor para a loja do bem antes.
 * ⚠️ Precisa de login: a plaqueta não é pública.
 */
export default function BemPeloCodigo() {
  const { codigo } = useParams<{ codigo: string }>();
  const router = useRouter();
  const [erro, setErro] = useState("");

  useEffect(() => {
    porCodigo(decodeURIComponent(codigo))
      .then((r) => {
        if (unidadeAtual() !== String(r.id_unidade)) {
          // Recarrega a página inteira: a sessão relê a loja escolhida, como no seletor.
          definirUnidade(r.id_unidade);
          window.location.replace(`/patrimonio/${r.id}`);
          return;
        }
        router.replace(`/patrimonio/${r.id}`);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Nenhum bem com este código"));
  }, [codigo, router]);

  if (erro) {
    return (
      <div className="flex flex-col gap-4">
        <Voltar href="/patrimonio">patrimônio</Voltar>
        <Aviso tipo="erro">{erro}</Aviso>
      </div>
    );
  }
  return <Carregando>Abrindo o bem…</Carregando>;
}
