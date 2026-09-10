"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Fornecedor } from "@/lib/cadastros";
import { Aviso, Carregando, Etiqueta } from "@/components/ui";
import FormularioFornecedor, { doFornecedor } from "../formulario";
import ProdutosDaPessoa from "./produtos-da-pessoa";
import Voltar from "@/components/voltar";

/** Corrigir um fornecedor — a mesma forma da criação, para o olho reconhecer. */
export default function PaginaFornecedor() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [x, setX] = useState<Fornecedor | null>(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    try {
      // ⚠️ Não há `GET /fornecedores/{id}`: a lista é a fonte, e a busca vai ao
      // SERVIDOR. Procurar na página carregada acharia só quem já estivesse na
      // tela — numa base com 817 fornecedores, quase nunca.
      const r = await api.listar<Fornecedor>(
        `/fornecedores?busca=&incluir_inativos=true&limite=1000`,
      );
      const achado = r.itens.find((f) => String(f.id) === String(id));
      if (!achado) {
        setErro("Fornecedor não encontrado.");
        return;
      }
      setX(achado);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!x) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/fornecedores">
          pessoas
        </Voltar>
        <h1 className="mt-1 break-words text-[24px] font-bold tracking-tight sm:text-[30px]">
          {x.nome}
        </h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {!x.ativo && <Etiqueta cor="alerta">inativo</Etiqueta>}
          {!!x.produtos && <Etiqueta cor="erva">{x.produtos} produto(s)</Etiqueta>}
        </div>
      </header>

      <FormularioFornecedor
        inicial={doFornecedor(x)}
        id={x.id}
        aoGravar={() => router.push("/fornecedores")}
      />

      {/* 🔑 **O que esta pessoa fornece** (09/09/2026, pedido do dono). A etiqueta
          lá em cima já dizia QUANTOS; o número sozinho não responde "o que a
          gente compra deste aqui?", e descobrir exigia ir à lista de produtos e
          filtrar um por um.
          ⚠️ **Depois do formulário, não antes.** A ficha existe para editar a
          pessoa; a lista é consulta. Pôr a tabela primeiro empurraria os campos
          para baixo da dobra em quem tem doze produtos. */}
      <ProdutosDaPessoa id={x.id} />
    </div>
  );
}
