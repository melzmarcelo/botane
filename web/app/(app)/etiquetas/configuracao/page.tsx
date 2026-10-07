"use client";

import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso } from "@/components/ui";
import { useSessao } from "@/lib/sessao";

import ModeloDaEtiqueta from "./modelo";
import ProdutosComValidade from "./produtos";

/**
 * Etiquetas → Configuração: como a etiqueta sai nesta loja.
 *
 * 🔑 **As validades saíram daqui e foram para o cadastro do PRODUTO** (06/10/2026,
 * pedido do dono: *"hoje já temos os dias de validade no cadastro de produto.
 * Podemos transferir esta configuração para o cadastro de produto, aí deixamos
 * tudo centralizado no produto"*). Esta tela tinha um editor com busca de produto
 * para as regras — enquanto o "Validade (dias)" do mesmo produto morava no
 * cadastro. Duas telas para a mesma pergunta.
 * ⚠️ **A lista de quem tem regra ficou**, só de leitura: é o panorama que o
 * cadastro, produto a produto, não dá — e cada linha leva ao cadastro.
 * ⚠️ O MODELO continua aqui: é a impressora da loja, não um dado do produto.
 */
export default function ConfiguracaoDeEtiquetas() {
  const { pode } = useSessao();
  const podeEditar = pode("etiquetas.configurar");

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Etiquetas"
        titulo="Configuração"
        explica="O modelo da etiqueta desta loja — o tamanho do rolo e o que aparece nela. A validade de cada produto se cadastra no próprio produto."
      />
      <ModeloDaEtiqueta podeEditar={podeEditar} />
      <Aviso tipo="info">
        <b>A validade de cada produto agora fica no cadastro dele</b>, na aba Estoque: o
        campo “Validade (dias)” e, logo abaixo, as regras por situação (depois de produzir,
        abrir ou descongelar). A lista abaixo mostra quem já tem regra e leva direto para lá.
      </Aviso>
      <ProdutosComValidade />
    </div>
  );
}
