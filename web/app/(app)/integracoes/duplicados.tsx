"use client";

import Link from "next/link";
import { useSessao } from "@/lib/sessao";
import { Cartao } from "@/components/ui";

/**
 * Os cadastros que as importações criaram em duplicidade.
 *
 * 🔑 **Não é do Omie NEM do PDV — é das duas juntas**, e foi por isso que ganhou
 * aba própria (09/09/2026). O catálogo do Omie cria um cadastro por CÓDIGO (o
 * mesmo abacate uma vez por fornecedor que já o vendeu) e o cardápio do PDV cria
 * o dele. Pendurar este cartão na aba do Omie diria que o Omie os causou
 * sozinho, e quem fosse procurar depois de importar o cardápio não o acharia.
 *
 * ⚠️ A permissão é a do ENDPOINT (`cadastros.produtos`), não a de integração:
 * mostrar o cartão a quem só configura credencial daria um 403 depois do clique.
 */
export default function Duplicados() {
  const { pode } = useSessao();
  if (!pode("cadastros.produtos")) return null;

  return (
    <Cartao
      titulo="Cadastros com o mesmo nome"
      descricao="O mesmo produto cadastrado mais de uma vez pelas importações — juntados num só."
      acao={
        <Link href="/produtos/duplicados" className="btn btn-secundario">
          Mesmo nome
        </Link>
      }
    >
      <p className="max-w-[70ch] text-[14px] text-suave">
        O catálogo do Omie cria um cadastro por código, então o mesmo abacate aparece uma vez
        para cada fornecedor que já o vendeu — e o cardápio do PDV traz o dele. A tela põe os
        repetidos lado a lado, com os códigos à vista, e junta o grupo num clique.{" "}
        <b>Nome igual não é prova</b>: confira antes, porque a fusão não tem desfazer.
      </p>
    </Cartao>
  );
}
