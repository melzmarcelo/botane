"use client";

/**
 * A janela de UM anúncio do Cardápio Vivo (121): o que diz, o que o botão faz, quando e onde.
 *
 * 🔑 Pedido do dono (16/10/2026): da casa (o catálogo do Dia dos Namorados) ou de outra marca
 * ("Patrocinado"), com período e dias, e links. Criar deixa a janela aberta para a mídia.
 * ⚠️ O quê e quando aparecem aqui; o RITMO (5º prato, 8 de distância, máximo) é da casa, na tela.
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Confirmacao, Modal } from "@/components/ui";
import { AnunciosService, type AcaoAnuncio, type Anuncio, type CanalAnuncio, type GravarAnuncio } from "@/lib/anuncios";
import MidiaDoAnuncio from "./midia-do-anuncio";
import VariantesDoAnuncio from "./variantes-do-anuncio";

export type Opcoes = {
  /** Os Cardápios Vivos da loja (onde o anúncio pode aparecer). */
  vivos: { id_catalogo: number; nome: string }[];
  /** Os catálogos da casa (o botão pode abrir um deles). */
  catalogos: { id: number; nome: string }[];
  /** Os pratos de cada Cardápio Vivo (o botão pode levar a um). */
  pratos: { id: number; nome: string; cardapio: string }[];
  /** 125: as seções de cada Cardápio Vivo (onde o anúncio combina). */
  secoes: { id: number; nome: string; cardapio: string }[];
};

const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const vazio = (): GravarAnuncio => ({
  nome: "", origem: "CASA", anunciante: null, titulo: null, texto: null, acao: "NENHUMA", acao_catalogo: null,
  acao_item: null, acao_url: null, acao_rotulo: null, inicio: null, fim: null, dias: null, hora_de: null,
  hora_ate: null, horario_especial: false, cardapios: null, canal: "AMBOS", peso: 1, ativo: true, secoes: null,
});

export default function JanelaAnuncio({ atual: inicial, opcoes, podeEditar, aoFechar, aoMudar }: {
  atual: Anuncio | null; opcoes: Opcoes; podeEditar: boolean; aoFechar: () => void; aoMudar: () => Promise<void>;
}) {
  const aviso = useAviso();
  const [atual, setAtual] = useState<Anuncio | null>(inicial);
  const [f, setF] = useState<GravarAnuncio>(() => (inicial ? { ...vazio(), ...inicial } : vazio()));
  const [gravando, setGravando] = useState(false);
  const [apagando, setApagando] = useState(false);
  const mudar = (m: Partial<GravarAnuncio>) => setF((x) => ({ ...x, ...m }));
  const txt = (v: string) => v || null;

  async function gravar() {
    setGravando(true);
    try {
      const corpo = { ...f, hora_de: f.hora_de || null, hora_ate: f.hora_ate || null,
                      inicio: f.inicio || null, fim: f.fim || null };
      if (atual) {
        setAtual(await AnunciosService.atualizar(atual.id, corpo));
        await aoMudar();
        aviso.sucesso("Anúncio gravado.");
        aoFechar();
      } else {
        setAtual(await AnunciosService.criar(corpo));
        await aoMudar();
        aviso.sucesso("Anúncio criado. Se quiser, ponha agora a foto ou o vídeo.");
      }
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar o anúncio.");
    } finally {
      setGravando(false);
    }
  }

  async function excluir() {
    if (!atual) return;
    try {
      await AnunciosService.remover(atual.id);
      setApagando(false);
      aoFechar();
      await aoMudar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível remover.");
    }
  }

  const dias = f.dias ?? [];
  const alternarDia = (d: number) => mudar({ dias: dias.includes(d) ? dias.filter((x) => x !== d) : [...dias, d].sort() });
  const cardapios = f.cardapios ?? [];
  const secoes = f.secoes ?? [];
  const alternarSecao = (id: number) => {
    const nova = secoes.includes(id) ? secoes.filter((x) => x !== id) : [...secoes, id];
    mudar({ secoes: nova.length ? nova : null });
  };
  return (
    <Modal titulo={atual ? `Anúncio — ${atual.nome}` : "Novo anúncio"} largura="720px" aoFechar={aoFechar}
           descricao="Aparece no Cardápio Vivo entre os pratos, no ritmo que a casa definiu. Só no feed."
           rodape={
             <div className="flex flex-wrap items-center justify-end gap-2">
               {atual && podeEditar && (
                 <button type="button" className="link-acao link-acao-erro mr-auto" onClick={() => setApagando(true)}>excluir anúncio</button>
               )}
               <button type="button" className="btn btn-secundario" onClick={aoFechar}>{atual ? "Fechar" : "Cancelar"}</button>
               {podeEditar && (
                 <button type="button" id="anuncio-gravar" className="btn btn-primario" aria-busy={gravando}
                         disabled={gravando || f.nome.trim().length < 2} onClick={() => void gravar()}>
                   {atual ? "Gravar" : "Criar anúncio"}
                 </button>
               )}
             </div>
           }>
      <fieldset disabled={!podeEditar} className="flex flex-col gap-4">
        <Campo rotulo="Nome do anúncio" dica="Para a casa achar na lista — o cliente não vê. Ex.: “Cerveja X — outubro”.">
          <input id="anuncio-nome" className="campo" maxLength={120} autoFocus value={f.nome}
                 onChange={(e) => mudar({ nome: e.target.value })} />
        </Campo>
        <div className="flex flex-wrap gap-4 text-[14px]">
          {([["CASA", "Da casa — um catálogo ou prato nosso"], ["EXTERNO", "De outra marca — sai como “Patrocinado”"]] as const).map(([v, r]) => (
            <label key={v} className="flex items-center gap-2">
              <input type="radio" name="origem" checked={f.origem === v} onChange={() => mudar({ origem: v })} /> {r}
            </label>
          ))}
        </div>
        {f.origem === "EXTERNO" && (
          <Campo rotulo="Anunciante" dica="Aparece no anúncio: “Patrocinado · Cervejaria X”, e no relatório.">
            <input id="anuncio-anunciante" className="campo" maxLength={120} value={f.anunciante ?? ""}
                   onChange={(e) => mudar({ anunciante: txt(e.target.value) })} />
          </Campo>
        )}
        <Campo rotulo="Título" opcional>
          <input id="anuncio-titulo" className="campo" maxLength={120} value={f.titulo ?? ""}
                 onChange={(e) => mudar({ titulo: txt(e.target.value) })} />
        </Campo>
        <Campo rotulo="Texto" opcional dica="Curto: é propaganda no meio do cardápio. Traduzido sozinho para inglês e alemão.">
          <textarea id="anuncio-texto" className="campo" rows={3} maxLength={500} value={f.texto ?? ""}
                    onChange={(e) => mudar({ texto: txt(e.target.value) })} />
        </Campo>

        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="O botão">
            <select id="anuncio-acao" className="campo" value={f.acao} onChange={(e) => mudar({ acao: e.target.value as AcaoAnuncio })}>
              <option value="NENHUMA">sem botão</option>
              <option value="CATALOGO">abrir um catálogo da casa</option>
              <option value="PRATO">mostrar um prato</option>
              <option value="LINK">abrir um link</option>
            </select>
          </Campo>
          {f.acao !== "NENHUMA" && (
            <Campo rotulo="Texto do botão" opcional dica="Em branco: “Ver o cardápio ›”, “Ver o prato ›” ou “Saiba mais ›”.">
              <input className="campo" maxLength={40} value={f.acao_rotulo ?? ""} onChange={(e) => mudar({ acao_rotulo: txt(e.target.value) })} />
            </Campo>
          )}
        </div>
        {f.acao === "CATALOGO" && (
          <Campo rotulo="Catálogo">
            <select id="anuncio-catalogo" className="campo" value={f.acao_catalogo ?? ""}
                    onChange={(e) => mudar({ acao_catalogo: e.target.value ? Number(e.target.value) : null })}>
              <option value="">escolha</option>
              {opcoes.catalogos.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
          </Campo>
        )}
        {f.acao === "PRATO" && (
          <Campo rotulo="Prato" dica="O botão só aparece no Cardápio Vivo que tem esse prato.">
            <select className="campo" value={f.acao_item ?? ""} onChange={(e) => mudar({ acao_item: e.target.value ? Number(e.target.value) : null })}>
              <option value="">escolha</option>
              {opcoes.pratos.map((p) => <option key={p.id} value={p.id}>{p.nome} · {p.cardapio}</option>)}
            </select>
          </Campo>
        )}
        {f.acao === "LINK" && (
          <Campo rotulo="Link" dica="Abre em outra aba — o cardápio continua aberto.">
            <input id="anuncio-link" className="campo mono" maxLength={500} placeholder="https://" value={f.acao_url ?? ""}
                   onChange={(e) => mudar({ acao_url: txt(e.target.value) })} />
          </Campo>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="De" opcional><input type="date" className="campo mono" value={f.inicio ?? ""} onChange={(e) => mudar({ inicio: e.target.value || null })} /></Campo>
          <Campo rotulo="Até" opcional><input type="date" className="campo mono" value={f.fim ?? ""} onChange={(e) => mudar({ fim: e.target.value || null })} /></Campo>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[14px]">
          <span className="text-suave">Dias:</span>
          {DIAS.map((d, i) => (
            <label key={d} className="flex items-center gap-1">
              <input type="checkbox" checked={dias.includes(i + 1)} onChange={() => alternarDia(i + 1)} /> {d}
            </label>
          ))}
          <span className="text-[12.5px] text-suave">nenhum = todos</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[14px]">
          Das
          <input type="time" className="campo mono !w-auto" value={(f.hora_de ?? "").slice(0, 5)} onChange={(e) => mudar({ hora_de: e.target.value || null })} />
          às
          <input type="time" className="campo mono !w-auto" value={(f.hora_ate ?? "").slice(0, 5)} onChange={(e) => mudar({ hora_ate: e.target.value || null })} />
          <span className="text-[12.5px] text-suave">vazio = o dia todo</span>
          <label className="ml-2 flex items-center gap-2">
            <input type="checkbox" checked={f.horario_especial} onChange={(e) => mudar({ horario_especial: e.target.checked })} />
            também nos dias especiais
          </label>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="Onde">
            <select className="campo" value={f.canal} onChange={(e) => mudar({ canal: e.target.value as CanalAnuncio })}>
              <option value="AMBOS">na mesa e pelo link</option>
              <option value="MESA">só na mesa</option>
              <option value="LINK">só pelo link (site, catering)</option>
            </select>
          </Campo>
          <Campo rotulo="Peso" dica="Entre os anúncios do momento, o de peso 2 aparece o dobro do de peso 1.">
            <select className="campo" value={f.peso} onChange={(e) => mudar({ peso: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </Campo>
        </div>
        {opcoes.vivos.length > 1 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[14px]">
            <span className="text-suave">Cardápios:</span>
            {opcoes.vivos.map((v) => (
              <label key={v.id_catalogo} className="flex items-center gap-2">
                <input type="checkbox" checked={cardapios.includes(v.id_catalogo)}
                       onChange={() => mudar({ cardapios: cardapios.includes(v.id_catalogo)
                         ? (cardapios.filter((x) => x !== v.id_catalogo).length ? cardapios.filter((x) => x !== v.id_catalogo) : null)
                         : [...cardapios, v.id_catalogo] })} /> {v.nome}
              </label>
            ))}
            <span className="text-[12.5px] text-suave">nenhum = todos</span>
          </div>
        )}
        {opcoes.secoes.length > 0 && (
          <details className="text-[14px]" open={secoes.length > 0}>
            <summary className="cursor-pointer text-suave">Combina com estas seções{secoes.length ? ` (${secoes.length})` : ""}</summary>
            <p className="mt-1 text-[12.5px] text-suave">
              Antes de um prato destas seções, o anúncio pesa o triplo no sorteio — a cerveja perto dos petiscos. Nenhuma =
              vale igual em todo o cardápio. O que mostra um prato já combina com a seção dele.
            </p>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2" id="anuncio-secoes">
              {opcoes.secoes.map((s) => (
                <label key={s.id} className="flex items-center gap-2">
                  <input type="checkbox" checked={secoes.includes(s.id)} onChange={() => alternarSecao(s.id)} />
                  {s.nome}{opcoes.vivos.length > 1 ? <span className="text-suave"> · {s.cardapio}</span> : null}
                </label>
              ))}
            </div>
          </details>
        )}
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" checked={f.ativo} onChange={(e) => mudar({ ativo: e.target.checked })} />
          Ligado
        </label>
      </fieldset>

      <div className="mt-4 border-t border-linha pt-4">
        {atual
          ? <MidiaDoAnuncio anuncio={atual} podeEditar={podeEditar} aoMudar={(a) => { setAtual(a); void aoMudar(); }} />
          : <p className="text-[13px] text-suave">A foto ou o vídeo entram depois de criar o anúncio.</p>}
      </div>
      {atual && (
        <div className="mt-4 border-t border-linha pt-4">
          <VariantesDoAnuncio anuncio={atual} podeEditar={podeEditar} aoMudar={() => void aoMudar()} />
        </div>
      )}

      {apagando && atual && (
        <Confirmacao titulo={`Excluir “${atual.nome}”?`} rotuloConfirmar="Excluir" perigo
                     aoConfirmar={() => void excluir()} aoCancelar={() => setApagando(false)}>
          <p>Ele sai do Cardápio Vivo, com a foto ou o vídeo. O relatório dele deixa de abrir.</p>
        </Confirmacao>
      )}
    </Modal>
  );
}
