"use client";

/**
 * A aba Publicação do editor: a CAPA do catálogo e o que decide se o cliente o vê.
 *
 * 🔑 **Reforma de 15/10/2026**: publicar ficava na lista, longe de onde se monta
 * o cardápio — a página do catálogo dizia "publique em Catálogos" e mandava a
 * pessoa embora. E qual catálogo é o Cardápio Vivo da loja só se escolhia na tela
 * do Cardápio Vivo. Agora as duas coisas moram aqui, ao lado do conteúdo.
 * ⚠️ A tela do Cardápio Vivo continua escolhendo também: as duas gravam o MESMO
 * `cardapio_config.id_catalogo`, então não há duas verdades.
 */

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Cartao, Confirmacao, Etiqueta } from "@/components/ui";
import { CardapioVivoService, type RespostaConfig } from "@/lib/cardapio-vivo";
import * as cat from "@/lib/catalogos";

type Props = { capa: cat.Catalogo; podeEditar: boolean; aoMudar: () => Promise<void> };

export default function AbaPublicacao({ capa, podeEditar, aoMudar }: Props) {
  const aviso = useAviso();
  const router = useRouter();
  const [op, setOp] = useState<cat.Opcoes | null>(null);
  const [f, setF] = useState(() => formDa(capa));
  const [salvando, setSalvando] = useState(false);
  const [apagando, setApagando] = useState(false);
  const [vivo, setVivo] = useState<RespostaConfig | null>(null);

  useEffect(() => setF(formDa(capa)), [capa]);
  useEffect(() => {
    cat.opcoes().then(setOp).catch(() => setOp(null));
    // ⚠️ Só no catálogo de produtos: o feed não sabe mostrar um PDF.
    if (capa.origem === cat.ORIGEM_PRODUTOS) {
      CardapioVivoService.config().then(setVivo).catch(() => setVivo(null));
    }
  }, [capa.origem]);

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
    }, "Publicação salva.");
  }

  async function marcarVivo(ligar: boolean) {
    if (!vivo) return;
    try {
      // ⚠️ A configuração do Cardápio Vivo é gravada INTEIRA (é um PUT só): troca
      // o catálogo e devolve o resto como estava.
      const r = await CardapioVivoService.salvarConfig({
        ...vivo.config,
        id_catalogo: ligar ? capa.id : null,
      });
      setVivo(r);
      aviso.sucesso(ligar ? "Este passa a ser o Cardápio Vivo da loja." : "A loja ficou sem Cardápio Vivo.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar");
    }
  }

  async function excluir() {
    try {
      const r = await cat.excluir(capa.id);
      aviso.sucesso(r.message);
      router.replace("/catalogos");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível excluir");
    }
  }

  const ehVivo = vivo?.config.id_catalogo === capa.id;
  const outroVivo = vivo?.config.id_catalogo && !ehVivo
    ? vivo.catalogos.find((c) => c.id === vivo.config.id_catalogo)?.nome ?? "outro catálogo"
    : null;

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
              {/* ⚠️ Só RASCUNHO se apaga: o que já esteve no ar se inativa. */}
              {capa.situacao === "RASCUNHO" && (
                <button type="button" className="btn btn-secundario text-erro" onClick={() => setApagando(true)}>
                  Excluir rascunho
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
        <Cartao titulo="Cardápio Vivo" descricao="O cardápio da mesa, que o cliente abre pelo QR code. Cada loja usa um catálogo.">
          <label className="flex items-start gap-3">
            <input type="checkbox" className="mt-1" id="catalogo-vivo" disabled={!podeEditar}
                   checked={ehVivo} onChange={(e) => void marcarVivo(e.target.checked)} />
            <span className="text-[14px]">
              Usar este catálogo como o Cardápio Vivo desta loja
              <span className="block text-[13px] text-suave">
                {ehVivo
                  ? "É ele que a mesa abre hoje."
                  : outroVivo
                    ? `Hoje a mesa abre “${outroVivo}”. Marcar aqui troca.`
                    : "A loja ainda não tem Cardápio Vivo."}{" "}
                Aparência, modo e mesas ficam em Cardápio Vivo ▸ Configuração.
              </span>
            </span>
          </label>
        </Cartao>
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
        <Confirmacao titulo={`Excluir “${capa.nome}”?`} rotuloConfirmar="Excluir" perigo
                     aoConfirmar={() => void excluir()} aoCancelar={() => setApagando(false)}>
          Ele ainda é rascunho, então nunca esteve no ar. As seções e os vínculos saem junto;
          os produtos continuam cadastrados. Isto não se desfaz.
        </Confirmacao>
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
  };
}
