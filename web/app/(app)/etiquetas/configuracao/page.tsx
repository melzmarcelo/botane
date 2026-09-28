"use client";

import { useState } from "react";

import CabecalhoTela from "@/components/cabecalho-tela";
import { useSessao } from "@/lib/sessao";

import ModeloDaEtiqueta from "./modelo";
import ProdutosComValidade from "./produtos";
import ValidadesDoProduto from "./validades";

/**
 * Etiquetas → Configuração: quanto cada produto dura, e como a etiqueta sai.
 *
 * 🔑 **A validade depende do que aconteceu e de como se guarda**: o mesmo molho dura
 * 3 dias refrigerado e 60 congelado; o creme de leite, 3 dias depois de aberto. A tabela
 * de validades da responsável técnica mora aqui, produto por produto.
 */
export default function ConfiguracaoDeEtiquetas() {
  const { pode } = useSessao();
  const podeEditar = pode("etiquetas.configurar");
  const [produto, setProduto] = useState<{ id: number; rotulo: string } | null>(null);
  const [versao, setVersao] = useState(0);

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Etiquetas"
        titulo="Configuração"
        explica="As validades de cada produto (por evento e conservação) e o modelo da etiqueta desta loja — o tamanho do rolo e o que aparece nela."
      />
      <ValidadesDoProduto produto={produto} aoProduto={setProduto} podeEditar={podeEditar}
                          aoSalvar={() => setVersao((v) => v + 1)} />
      <ProdutosComValidade versao={versao} aoEscolher={setProduto} />
      <ModeloDaEtiqueta podeEditar={podeEditar} />
    </div>
  );
}
