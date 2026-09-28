"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro from "@/components/busca-cadastro";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Campo, Cartao } from "@/components/ui";
import { fonteProdutos } from "@/lib/busca-cadastro";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import {
  daProducao, emitir, imprimir, porCodigo, sugestao,
  type Conservacao, type DaProducao, type Etiqueta, type Evento, type Sugestao,
} from "@/lib/etiquetas";
import { useSessao } from "@/lib/sessao";

import Emitidas from "./emitidas";
import EscolhaDoEvento from "./escolha";
import Previa from "./previa";

/**
 * Etiquetas → Imprimir: a bancada da cozinha.
 *
 * 🔑 **Pedido do dono (28/09/2026):** *"algo integrado, que controlamos de forma simples
 * e rápida"*. Produto, o que aconteceu (produzi, abri, descongelei), a conservação e
 * quantas — a validade, o lote, o responsável e os alergênicos vêm prontos.
 * ⚠️ Chega aqui de três jeitos: direto (menu), da PRODUÇÃO (`?producao=`, com o lote
 * dela) e do QR de um pote (`?origem=`, para descongelar ou reetiquetar).
 */
const PRODUTOS = fonteProdutos();

export default function ImprimirEtiquetas() {
  const aviso = useAviso();
  const { eu } = useSessao();
  const [idProducao, setIdProducao] = useEstadoNaUrl<string>("producao", "");
  const [codigoOrigem, setCodigoOrigem] = useEstadoNaUrl<string>("origem", "");
  const [produto, setProduto] = useState<{ id: number; rotulo: string } | null>(null);
  const [evento, setEvento] = useState<Evento>("PRODUCAO");
  const [conservacao, setConservacao] = useState<Conservacao | null>(null);
  const [sug, setSug] = useState<Sugestao | null>(null);
  const [producao, setProducao] = useState<DaProducao | null>(null);
  const [origem, setOrigem] = useState<Etiqueta | null>(null);
  const [copias, setCopias] = useState(1);
  const [quantidade, setQuantidade] = useState("");
  const [lote, setLote] = useState("");
  const [fabricante, setFabricante] = useState("");
  const [venceManual, setVenceManual] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [emitidas, setEmitidas] = useState<Etiqueta[]>([]);

  // Vindo da produção: produto, lote e quantidade saem dela.
  useEffect(() => {
    if (!idProducao) return setProducao(null);
    daProducao(Number(idProducao))
      .then((p) => {
        setProducao(p);
        setProduto({ id: p.id_produto, rotulo: p.produto });
        setEvento("PRODUCAO");
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Produção não encontrada"));
  }, [idProducao]);

  // Vindo do QR de um pote: descongelar ou reetiquetar.
  useEffect(() => {
    if (!codigoOrigem) return setOrigem(null);
    porCodigo(codigoOrigem)
      .then((e) => {
        setOrigem(e);
        setProduto({ id: e.id_produto, rotulo: e.produto });
        setEvento("DESCONGELAMENTO");
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Etiqueta não encontrada"));
  }, [codigoOrigem]);

  useEffect(() => {
    if (!produto) return setSug(null);
    sugestao(produto.id, evento, conservacao)
      .then((s) => {
        setSug(s);
        if (!conservacao) setConservacao(s.conservacao);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao calcular a validade"));
  }, [produto, evento, conservacao]);

  function trocarProduto(p: { id: number; rotulo: string } | null) {
    setProduto(p);
    setConservacao(null);
    setVenceManual("");
    setEmitidas([]);
  }

  async function imprimirAgora() {
    if (!produto) return;
    setOcupado(true);
    setErro("");
    try {
      const r = await emitir({
        id_produto: producao || origem ? null : produto.id,
        evento, conservacao, copias,
        quantidade: quantidade ? Number(quantidade.replace(",", ".")) : null,
        id_producao: producao?.id ?? null,
        id_origem: origem?.id ?? null,
        lote: lote || null,
        validade_fabricante: fabricante || null,
        vence_em: venceManual ? new Date(venceManual).toISOString() : null,
        responsavel: responsavel || null,
      });
      setEmitidas(r.etiquetas);
      aviso.sucesso(r.message);
      await imprimir(r.ids);
      if (origem) setCodigoOrigem("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível imprimir");
    } finally {
      setOcupado(false);
    }
  }

  const fixo = !!(producao || origem);
  const precisaData = !!sug && !sug.vence_em && !venceManual && !fabricante;

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Etiquetas"
        titulo="Imprimir etiquetas"
        explica={<>Escolha o produto, diga o que aconteceu e imprima. A validade sai da regra do
          produto (em <Link className="link-acao" href="/etiquetas/configuracao">Configuração</Link>);
          o lote, o responsável e os alergênicos vêm sozinhos.</>}
        acoes={<Link href="/etiquetas/painel" className="btn btn-secundario">Painel de validades</Link>}
      />
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Cartao>
          <div className="flex flex-col gap-5">
            {producao && (
              <Aviso tipo="info">
                Produção #{producao.id}: {Number(producao.quantidade).toLocaleString("pt-BR")}{" "}
                {producao.um_estoque} de {producao.produto}
                {producao.lote ? ` · lote ${producao.lote}` : ""}
                {producao.etiquetas ? ` · ${producao.etiquetas} etiqueta(s) já impressa(s)` : ""}.{" "}
                <button className="link-acao" onClick={() => { setIdProducao(""); trocarProduto(null); }}>
                  soltar
                </button>
              </Aviso>
            )}
            {origem && (
              <Aviso tipo="info">
                Nova etiqueta para o pote {origem.codigo} ({origem.produto}) — a antiga deixa de valer.
                {evento === "DESCONGELAMENTO"
                  ? " Descongelado começa um prazo novo, nunca maior que o do pote."
                  : " Reetiquetar (dividir o pote, trocar de lugar) mantém a validade dele."}{" "}
                <button className="link-acao" onClick={() => { setCodigoOrigem(""); trocarProduto(null); }}>
                  cancelar
                </button>
              </Aviso>
            )}
            <Campo rotulo="Produto">
              <BuscaCadastro fonte={PRODUTOS} selecionado={produto} disabled={fixo} autoFocus={!fixo}
                             aoEscolher={(i) => trocarProduto(i ? { id: i.id, rotulo: i.nome } : null)} />
            </Campo>
            <EscolhaDoEvento
              evento={evento} aoEvento={(e) => { setEvento(e); setConservacao(null); }}
              conservacao={conservacao} aoConservacao={setConservacao}
              regras={sug?.regras ?? []} travado={!!producao}
            />
            <div className="grid gap-4 sm:grid-cols-3">
              <Campo rotulo="Quantas etiquetas" dica="uma por pote">
                <input className="campo mono" type="number" min={1} max={60} value={copias}
                       onChange={(e) => setCopias(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} />
              </Campo>
              <Campo rotulo={`Quantidade por pote${sug?.produto.um_estoque ? ` (${sug.produto.um_estoque})` : ""}`}
                     opcional dica={producao ? "vazio = a produção dividida pelos potes" : undefined}>
                <input className="campo mono" inputMode="decimal" value={quantidade}
                       onChange={(e) => setQuantidade(e.target.value)} />
              </Campo>
              <Campo rotulo="Responsável" opcional dica={`vazio = ${eu?.nome ?? "quem está logado"}`}>
                <input className="campo" value={responsavel} maxLength={120}
                       onChange={(e) => setResponsavel(e.target.value)} />
              </Campo>
            </div>
            {evento === "ABERTURA" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Campo rotulo="Validade do fabricante" opcional dica="aberto nunca vale mais que ela">
                  <input className="campo mono" type="date" value={fabricante}
                         onChange={(e) => setFabricante(e.target.value)} />
                </Campo>
                <Campo rotulo="Lote do fabricante" opcional>
                  <input className="campo mono" value={lote} maxLength={40}
                         onChange={(e) => setLote(e.target.value)} />
                </Campo>
              </div>
            )}
            <Campo rotulo="Validade informada" opcional={!precisaData}
                   dica={precisaData ? "este produto não tem regra — informe a validade"
                                     : "só para trocar a que a regra calculou"}>
              <input className="campo mono" type="datetime-local" value={venceManual}
                     onChange={(e) => setVenceManual(e.target.value)} />
            </Campo>
            <div className="flex justify-end">
              <button className="btn btn-primario" disabled={!produto || ocupado || precisaData}
                      aria-busy={ocupado} onClick={() => void imprimirAgora()}>
                {ocupado ? "…" : `Imprimir ${copias} etiqueta${copias > 1 ? "s" : ""}`}
              </button>
            </div>
          </div>
        </Cartao>
        <Previa sug={sug} evento={evento} conservacao={conservacao} venceManual={venceManual}
                fabricante={fabricante} responsavel={responsavel || eu?.nome || ""}
                lote={producao?.lote ?? origem?.lote ?? lote} />
      </div>

      {emitidas.length > 0 && <Emitidas etiquetas={emitidas} />}
    </div>
  );
}
