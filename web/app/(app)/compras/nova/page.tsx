"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Local, ProdutoResumo } from "@/lib/cadastros";
import { Aviso, Carregando } from "@/components/ui";
import NotaManual from "../nota-manual";

/**
 * Digitar uma nota de entrada — a compra que não tem XML nenhum.
 *
 * Tem página própria porque o formulário é longo: cabeçalho, uma tabela de
 * itens que cresce, e o rodapé de frete e desconto. Aberto dentro da lista, ele
 * empurrava as notas para fora da tela e quem digitava perdia a referência do
 * que estava fazendo.
 */
export default function PaginaNotaNova() {
  const router = useRouter();
  const aviso = useAviso();
  const [produtos, setProdutos] = useState<ProdutoResumo[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  const [erro, setErro] = useState("");
  const [pronto, setPronto] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [p, l] = await Promise.all([
        api.get<ProdutoResumo[]>("/produtos"),
        api.get<Local[]>("/locais"),
      ]);
      setProdutos(p.filter((x) => x.controla_estoque));
      setLocais(l);
      setPronto(true);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/compras" className="link-voltar">
          notas de entrada
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Digitar nota de entrada
        </h1>
        <p className="mt-2 max-w-[70ch] text-suave">
          Para a compra que não tem XML: mercado, feira, açougue. Depois de gravar, a nota abre
          para conferência — ela só vira estoque quando for lançada.
        </p>
      </header>

      {!pronto ? (
        <Carregando />
      ) : (
        <NotaManual
          produtos={produtos}
          locais={locais}
          aoFechar={() => router.push("/compras")}
          aoGravar={(id) => {
            aviso.sucesso("Nota registrada. Confira os itens e lance no estoque.");
            router.push(`/compras/${id}`);
          }}
        />
      )}
    </div>
  );
}
