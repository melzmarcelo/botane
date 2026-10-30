"use client";

/**
 * A aba Publicação do editor: a CAPA do catálogo e o que decide se o cliente o vê.
 *
 * 🔑 **Reforma de 15/10/2026**: publicar ficava na lista, longe de onde se monta
 * o cardápio — a página do catálogo dizia "publique em Catálogos" e mandava a
 * pessoa embora. E qual catálogo é o Cardápio Vivo da loja só se escolhia na tela
 * do Cardápio Vivo. Agora as duas coisas moram aqui, ao lado do conteúdo.
 * ⚠️ A tela do Cardápio Vivo continua ligando também: as duas gravam o MESMO
 * `cardapio_vivos` (117) com a mesma janela, então não há duas verdades.
 */

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import JanelaCardapioVivo from "@/components/janela-cardapio-vivo";
import { Campo, Cartao, Etiqueta } from "@/components/ui";
import { CardapioVivoService, type RespostaConfig } from "@/lib/cardapio-vivo";
import * as cat from "@/lib/catalogos";
import JanelaExcluirCatalogo from "./janela-excluir-catalogo";

type Props = { capa: cat.Catalogo; podeEditar: boolean; aoMudar: () => Promise<void> };

export default function AbaPublicacao({ capa, podeEditar, aoMudar }: Props) {
  const aviso = useAviso();
  const router = useRouter();
  const [op, setOp] = useState<cat.Opcoes | null>(null);
  const [f, setF] = useState(() => formDa(capa));
  const [salvando, setSalvando] = useState(false);
  const [apagando, setApagando] = useState(false);
  const [vivo, setVivo] = useState<RespostaConfig | null>(null);
  const [configVivo, setConfigVivo] = useState(false);
  const [zaps, setZaps] = useState<cat.WhatsappDaLoja[]>([]);
  const produtos = capa.origem === cat.ORIGEM_PRODUTOS;

  useEffect(() => setF(formDa(capa)), [capa]);
  useEffect(() => {
    cat.opcoes().then(setOp).catch(() => setOp(null));
    // ⚠️ Só no catálogo de produtos: o feed não sabe mostrar um PDF.
    if (capa.origem === cat.ORIGEM_PRODUTOS) {
      CardapioVivoService.config().then(setVivo).catch(() => setVivo(null));
      cat.whatsapps(capa.id).then(setZaps).catch(() => setZaps([]));
    }
  }, [capa.origem, capa.id]);

  async function gravar(corpo: cat.Gravar, mensagem: string) {
    setSalvando(true);
    try {
      await cat.atualizar(capa.id, corpo);
      await aoMudar();
      aviso.sucesso(mensagem);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  function salvar(e: FormEvent) {
    e.preventDefault();
    // ⚠️ **Data vazia vira `null`, não `""`**: o servidor lê nulo como "sem prazo".
    void gravar({
      nome: f.nome.trim(),
      publica_de: f.publica_de || null,
      publica_ate: f.publica_ate || null,
      observacao: f.observacao.trim() || null,
      exige_cadastro: f.exige_cadastro,
      lojas: f.lojas,
      ...(produtos ? { id_whatsapp: f.id_whatsapp, permite_contato: f.permite_contato } : {}),
    }, "Publicação salva.");
  }

  async function desligarVivo() {
    try {
      const r = await CardapioVivoService.removerVivo(capa.id);
      setVivo(r);
      aviso.sucesso(r.message ?? "Deixou de ser Cardápio Vivo.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar");
    }
  }

  // 🔑 Vários Cardápios Vivos por loja (117): este catálogo pode ser um deles.
  const meuVivo = vivo?.vivos.find((v) => v.id_catalogo === capa.id) ?? null;
  const outrosVivos = (vivo?.vivos ?? []).filter((v) => v.id_catalogo !== capa.id);

  return (
    <div className="flex flex-col gap-5">
      <Cartao titulo="Situação" descricao="Rascunho não aparece para o cliente. Publicado, aparece dentro do período abaixo.">
        <div className="flex flex-wrap items-center gap-3">
          <Etiqueta cor={capa.situacao === "ATIVO" ? "erva" : capa.situacao === "RASCUNHO" ? "alerta" : "neutro"}>
            {cat.ROTULO_SITUACAO[capa.situacao]}
          </Etiqueta>
          <span className="text-[14px]">
            {capa.publicado_hoje ? (
              <b className="text-erva">No ar hoje.</b>
            ) : capa.situacao === "ATIVO" ? (
              "Ativo, mas fora do período — o cliente não o vê hoje."
            ) : (
              "O cliente não o vê."
            )}
          </span>
          {podeEditar && (
            <span className="ml-auto flex flex-wrap gap-2">
              {capa.situacao === "ATIVO" ? (
                <button type="button" className="btn btn-secundario" disabled={salvando}
                        onClick={() => void gravar({ situacao: "INATIVO" }, "Catálogo tirado do ar.")}>
                  Tirar do ar
                </button>
              ) : (
                <button type="button" className="btn btn-primario" disabled={salvando}
                        onClick={() => void gravar({ situacao: "ATIVO" }, "Catálogo publicado.")}>
                  {capa.situacao === "RASCUNHO" ? "Publicar" : "Publicar de novo"}
                </button>
              )}
              {/* 🔑 20/10/2026: o rascunho e o INATIVO se excluem (o inativo, com o nome digitado);
                  o que está no ar, primeiro sai do ar. 🔑 30/10/2026 (pedido do dono): o ATIVO
                  fora do período também — não está publicado. Se for Cardápio Vivo, ele continua
                  na mesa, e a janela diz por que não dá (a regra é do servidor). */}
              {!capa.publicado_hoje && (
                <button type="button" id="catalogo-excluir" className="btn btn-secundario text-erro" onClick={() => setApagando(true)}>
                  {capa.situacao === "RASCUNHO" ? "Excluir rascunho" : "Excluir catálogo"}
                </button>
              )}
            </span>
          )}
        </div>
        {capa.origem === cat.ORIGEM_PRODUTOS && (
          <p className="mt-3 text-[13.5px]">
            <a href={`/c/previa/${capa.id}`} target="_blank" rel="noreferrer" className="link-registro">
              Ver como o cliente vê ↗
            </a>
            <span className="text-suave"> — a prévia mostra também o que ainda é rascunho.</span>
          </p>
        )}
      </Cartao>

      {capa.origem === cat.ORIGEM_PRODUTOS && vivo && (
        <Cartao titulo="Cardápio Vivo"
                descricao="O cardápio no celular do cliente, prato a prato. A loja pode ter vários: o principal abre na mesa, os outros pelo link.">
          {meuVivo ? (
            <div className="flex flex-col gap-2 text-[14px]">
              <p>
                <b>É um Cardápio Vivo</b>
                {meuVivo.principal ? " — o principal: o QR code da mesa abre este." : " — abre pelo link."}
                <span className="text-suave"> {meuVivo.modo === "PEDIDO" ? "Pedido na mesa." : meuVivo.selecao ? "Vitrine." : "Só consulta."}</span>
              </p>
              <p className="mono break-all text-[12.5px] text-suave" id="vivo-link">{meuVivo.link}</p>
              {podeEditar && (
                <span className="flex gap-2">
                  <button type="button" className="link-acao" onClick={() => setConfigVivo(true)}>configurar</button>
                  <button type="button" className="link-acao link-acao-erro" onClick={() => void desligarVivo()}>
                    deixar de ser
                  </button>
                </span>
              )}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3 text-[14px]">
              <span className="text-suave">
                {outrosVivos.length
                  ? `A loja já tem ${outrosVivos.length === 1 ? `“${outrosVivos[0].nome}”` : `${outrosVivos.length} Cardápios Vivos`}. Este pode ser mais um — pelo link, ou como o da mesa.`
                  : "A loja ainda não tem Cardápio Vivo. O primeiro vira o da mesa."}
              </span>
              {podeEditar && (
                <button type="button" className="btn btn-secundario" id="vivo-ligar" onClick={() => setConfigVivo(true)}>
                  Tornar Cardápio Vivo
                </button>
              )}
            </div>
          )}
          <p className="mt-3 text-[13px] text-suave">Aparência e mesas ficam em Cardápio Vivo ▸ Configuração.</p>
        </Cartao>
      )}
      {configVivo && (
        <JanelaCardapioVivo idCatalogo={capa.id} nomeCatalogo={capa.nome} atual={meuVivo}
                            temOutros={outrosVivos.length > 0}
                            aoFechar={() => setConfigVivo(false)} aoGravar={setVivo} />
      )}

      <Cartao titulo="Capa" descricao="O nome que o cliente lê e quando o catálogo vale.">
        <form id="form-publicacao" onSubmit={salvar} className="flex flex-col gap-4">
          <Campo rotulo="Nome no site do cliente" dica="É o que o cliente lê.">
            <input className="campo" id="catalogo-nome" required minLength={2} maxLength={120}
                   disabled={!podeEditar} value={f.nome}
                   onChange={(e) => setF({ ...f, nome: e.target.value })} />
          </Campo>
          {/* ⚠️ As duas pontas são opcionais, e a dica diz o que o vazio quer dizer. */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo="Publica de" dica="Em branco: vale desde já.">
              <input className="campo" id="catalogo-de" type="date" disabled={!podeEditar}
                     value={f.publica_de} onChange={(e) => setF({ ...f, publica_de: e.target.value })} />
            </Campo>
            <Campo rotulo="Publica até" dica="Em branco: vale sem prazo.">
              <input className="campo" id="catalogo-ate" type="date" disabled={!podeEditar}
                     value={f.publica_ate} onChange={(e) => setF({ ...f, publica_ate: e.target.value })} />
            </Campo>
          </div>
          {(op?.lojas.length ?? 0) > 1 && (
            <Campo rotulo="Visível nas lojas" dica="Em que casas o cliente vê este catálogo no site.">
              <div className="flex flex-wrap gap-x-5 gap-y-2 pt-1">
                {op!.lojas.map((l) => (
                  <label key={l.id} className="flex items-center gap-2 text-[14px]">
                    <input type="checkbox" disabled={!podeEditar} checked={f.lojas.includes(l.id)}
                           onChange={(e) => setF({ ...f, lojas: e.target.checked
                             ? [...f.lojas, l.id] : f.lojas.filter((x) => x !== l.id) })} />
                    {l.nome}
                  </label>
                ))}
              </div>
            </Campo>
          )}
          <label className="flex items-start gap-3">
            <input type="checkbox" className="mt-1" id="catalogo-exige-cadastro" disabled={!podeEditar}
                   checked={f.exige_cadastro} onChange={(e) => setF({ ...f, exige_cadastro: e.target.checked })} />
            <span className="text-[14px]">
              Exigir cadastro do cliente para abrir
              <span className="block text-[13px] text-suave">
                Ligado, o site pede o telefone antes de mostrar o catálogo.
              </span>
            </span>
          </label>
          {/* 🔑 143 (pedido do dono, 30/10/2026): o número que atende este catálogo e o botão
              "entre em contato" no cabeçalho dele, no site e no Cardápio Vivo. */}
          {produtos && (<>
            <Campo rotulo="WhatsApp deste catálogo"
                   dica={zaps.length
                     ? "Atende o botão de contato e o “combinar o pagamento” dos pedidos. Os números ficam no cadastro da loja."
                     : "A loja não tem WhatsApp próprio: vale o da empresa. Os números se cadastram em Lojas."}>
              <select className="campo" id="catalogo-whatsapp" disabled={!podeEditar}
                      value={f.id_whatsapp ?? ""}
                      onChange={(e) => setF({ ...f, id_whatsapp: e.target.value ? Number(e.target.value) : null })}>
                <option value="">O principal da loja</option>
                {zaps.map((z) => (
                  <option key={z.id} value={z.id}>{z.rotulo} · {z.numero}{z.principal ? " (principal)" : ""}</option>
                ))}
              </select>
            </Campo>
            <label className="flex items-start gap-3">
              <input type="checkbox" className="mt-1" id="catalogo-permite-contato" disabled={!podeEditar}
                     checked={f.permite_contato} onChange={(e) => setF({ ...f, permite_contato: e.target.checked })} />
              <span className="text-[14px]">
                Permite entrar em contato
                <span className="block text-[13px] text-suave">
                  Ligado, o cabeçalho do catálogo ganha um botão de WhatsApp, no site e no Cardápio Vivo.
                </span>
              </span>
            </label>
          </>)}
          <Campo rotulo="Observação" dica="Para a casa, não para o cliente.">
            <input className="campo" id="catalogo-observacao" maxLength={500} disabled={!podeEditar}
                   value={f.observacao} onChange={(e) => setF({ ...f, observacao: e.target.value })} />
          </Campo>
          {podeEditar && (
            <div className="flex justify-end">
              <button type="submit" className="btn btn-primario" aria-busy={salvando} disabled={salvando}>
                {salvando ? "Salvando…" : "Salvar"}
              </button>
            </div>
          )}
        </form>
      </Cartao>

      {apagando && (
        <JanelaExcluirCatalogo capa={capa} aoFechar={() => setApagando(false)}
                               aoExcluir={() => router.replace("/catalogos")} />
      )}
    </div>
  );
}

function formDa(c: cat.Catalogo) {
  return {
    nome: c.nome,
    publica_de: c.publica_de ?? "",
    publica_ate: c.publica_ate ?? "",
    observacao: c.observacao ?? "",
    exige_cadastro: c.exige_cadastro,
    lojas: c.lojas,
    id_whatsapp: c.id_whatsapp ?? null,
    permite_contato: c.permite_contato ?? false,
  };
}
