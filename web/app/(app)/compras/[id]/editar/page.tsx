"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Local, ProdutoResumo } from "@/lib/cadastros";
import { Aviso, Carregando } from "@/components/ui";
import NotaManual, { NotaParaEditar } from "../../nota-manual";
import { NotaDetalhe } from "../../tipos";

/**
 * Corrigir uma nota digitada, antes de ela virar estoque.
 *
 * ⚠️ **Só a nota MANUAL se edita.** A que veio do XML ou do Omie é o documento
 * do fornecedor: mudar valor ali faria o sistema divergir da nota fiscal sem
 * rastro. E só antes de lançar — depois disso o razão já registrou, e correção
 * é estorno.
 */
export default function PaginaCorrigirNota() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const aviso = useAviso();
  const [editando, setEditando] = useState<NotaParaEditar | null>(null);
  const [produtos, setProdutos] = useState<ProdutoResumo[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    try {
      const [n, p, l] = await Promise.all([
        api.get<NotaDetalhe>(`/notas/${id}`),
        api.get<ProdutoResumo[]>("/produtos"),
        api.get<Local[]>("/locais"),
      ]);
      if (n.origem !== "MANUAL") {
        setErro(
          "Só a nota digitada se corrige. Esta veio do " +
            (n.origem === "XML" ? "XML da NF-e" : "Omie") +
            " — é o documento do fornecedor, e mudá-lo aqui faria o sistema divergir da nota " +
            "fiscal sem deixar rastro.",
        );
        return;
      }
      if (n.status === "LANCADA") {
        setErro(
          "Esta nota já foi lançada no estoque. Correção depois do lançamento é estorno, não " +
            "edição — o razão não se reescreve.",
        );
        return;
      }
      setProdutos(p.filter((x) => x.controla_estoque));
      setLocais(l);
      setEditando({
        id: n.id,
        id_fornecedor: n.id_fornecedor ?? null,
        numero: n.numero,
        serie: n.serie ?? null,
        data_emissao: n.data_emissao,
        valor_frete: Number(n.valor_frete ?? 0),
        valor_desconto: Number(n.valor_desconto ?? 0),
        valor_outros: Number(n.valor_outros ?? 0),
        id_local: n.id_local,
        itens: n.itens.map((i) => ({
          id_produto: i.id_produto,
          descricao_fornecedor: i.descricao_fornecedor,
          quantidade: Number(i.quantidade),
          valor_unitario: Number(i.valor_unitario),
          lote_nf: i.lote_nf ?? null,
          validade_nf: i.validade_nf ?? null,
          um_nota: i.um_nota ?? null,
          valor_desconto: Number(i.valor_desconto ?? 0),
          valor_acrescimo: Number(i.valor_acrescimo ?? 0),
        })),
      });
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a nota");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href={`/compras/${id}`} className="link-voltar">
          NF
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Corrigir a nota {editando?.numero ?? ""}
        </h1>
        <p className="mt-2 max-w-[70ch] text-suave">
          Ela ainda não virou estoque: dá para mexer em tudo antes de lançar.
        </p>
      </header>

      {erro ? (
        <Aviso tipo="erro">{erro}</Aviso>
      ) : !editando ? (
        <Carregando />
      ) : (
        <NotaManual
          produtos={produtos}
          locais={locais}
          editando={editando}
          aoFechar={() => router.push(`/compras/${id}`)}
          aoGravar={() => {
            aviso.sucesso("Nota corrigida. Confira e lance no estoque.");
            router.push(`/compras/${id}`);
          }}
        />
      )}
    </div>
  );
}
