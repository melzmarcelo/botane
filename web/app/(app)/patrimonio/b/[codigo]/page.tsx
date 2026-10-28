"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Aviso, Carregando } from "@/components/ui";
import Voltar from "@/components/voltar";
import { definirUnidade, unidadeAtual } from "@/lib/api";
import { conferindoAqui, lerPlaqueta, porCodigo, type Leitura } from "@/lib/patrimonio";
import { useSessao } from "@/lib/sessao";

/**
 * O que a plaqueta abre: o QR leva a `/patrimonio/b/PAT-0001`, e daqui à ficha do bem.
 *
 * ⚠️ **Vale a loja DO BEM**: quem lê a plaqueta pelo celular pode estar com outra loja
 * escolhida — a ficha seria "não encontrado". Troca o seletor para a loja do bem antes.
 * ⚠️ Precisa de login: a plaqueta não é pública.
 *
 * 🔑 **Na conferência (140), a plaqueta CONTA em vez de abrir a ficha** — mas só no
 * aparelho que está conferindo (`conferindoAqui()`, marcado na tela da conferência) e só
 * se a conferência aberta é a que procura este bem. É o caminho do celular cuja câmera
 * não lê dentro da tela (iPhone): câmera comum → link → leitura contada → volta.
 */
export default function BemPeloCodigo() {
  const { codigo } = useParams<{ codigo: string }>();
  const router = useRouter();
  const { pode } = useSessao();
  const [erro, setErro] = useState("");
  const [leitura, setLeitura] = useState<{ r: Leitura; idc: number; idBem: number } | null>(null);
  const podeConferir = pode("patrimonio.conferir");

  useEffect(() => {
    const cod = decodeURIComponent(codigo);
    porCodigo(cod)
      .then(async (r) => {
        if (unidadeAtual() !== String(r.id_unidade)) {
          // Recarrega a página inteira: a sessão relê a loja escolhida, como no seletor.
          // ⚠️ Recarrega ESTA página (não a ficha): a leitura da conferência acontece depois.
          definirUnidade(r.id_unidade);
          window.location.reload();
          return;
        }
        const idc = conferindoAqui();
        if (podeConferir && idc && r.conferencia_aberta === idc) {
          setLeitura({ r: await lerPlaqueta(idc, cod), idc, idBem: r.id });
          return;
        }
        router.replace(`/patrimonio/${r.id}`);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Nenhum bem com este código"));
  }, [codigo, router, podeConferir]);

  if (erro) {
    return (
      <div className="flex flex-col gap-4">
        <Voltar href="/patrimonio">patrimônio</Voltar>
        <Aviso tipo="erro">{erro}</Aviso>
      </div>
    );
  }
  if (leitura) {
    const { r, idc, idBem } = leitura;
    return (
      <div className="flex flex-col gap-4" id="plaqueta-conferida">
        <p className="rotulo">Conferência nº {idc}</p>
        <Aviso tipo={r.ja_lido ? "info" : "ok"}>{r.message}</Aviso>
        <p className="text-[15px]">
          <b>{r.contagem.lidos}</b> de <b>{r.contagem.esperados}</b> lidos · <b>{r.contagem.faltam}</b> faltam
        </p>
        <div className="flex flex-wrap gap-2">
          <Link href={`/patrimonio/conferencias/${idc}`} className="btn btn-primario">Voltar à conferência</Link>
          <Link href={`/patrimonio/${idBem}`} className="btn btn-secundario">Abrir a ficha do bem</Link>
        </div>
        <p className="text-[13px] text-suave">Pode ler a próxima plaqueta com a câmera.</p>
      </div>
    );
  }
  return <Carregando>Abrindo o bem…</Carregando>;
}
