"use client";

/**
 * As variações do TEXTO de um anúncio (125, fase 3) — na janela do anúncio.
 *
 * 🔑 Pedido do dono (16/10/2026, a proposta em três fases): "variações, com a vencedora". O texto
 * do próprio anúncio é a original; cada variação muda o título, o texto e o botão. As visitas se
 * dividem entre elas, sempre a mesma para a mesma visita, e o relatório diz qual faz mais gente
 * tocar. ⚠️ A mídia e o destino são os do anúncio — o teste é do que se diz.
 */

import { useCallback, useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import Traducoes from "@/components/traducoes";
import { AnunciosService, type Anuncio, type GravarVariante, type Variante } from "@/lib/anuncios";

const MAXIMO = 3;
const vazia = (): GravarVariante => ({ titulo: null, texto: null, acao_rotulo: null, ativo: true });

export default function VariantesDoAnuncio({ anuncio, podeEditar, aoMudar }: {
  anuncio: Anuncio; podeEditar: boolean; aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [lista, setLista] = useState<Variante[] | null>(null);
  const [editando, setEditando] = useState<{ id: number | null; f: GravarVariante } | null>(null);
  const [traduzindo, setTraduzindo] = useState<number | null>(null);
  const [gravando, setGravando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setLista(await AnunciosService.variantes(anuncio.id));
    } catch {
      setLista([]);
    }
  }, [anuncio.id]);
  useEffect(() => { void carregar(); }, [carregar]);

  async function gravar() {
    if (!editando) return;
    setGravando(true);
    try {
      if (editando.id) await AnunciosService.atualizarVariante(editando.id, editando.f);
      else await AnunciosService.criarVariante(anuncio.id, editando.f);
      setEditando(null);
      await carregar();
      aoMudar();
      aviso.sucesso("Variação gravada.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar a variação.");
    } finally {
      setGravando(false);
    }
  }

  async function remover(v: Variante) {
    try {
      await AnunciosService.removerVariante(v.id);
      await carregar();
      aoMudar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível remover.");
    }
  }

  if (!lista) return null;
  const txt = (s: string) => s || null;
  const mudar = (m: Partial<GravarVariante>) => setEditando((x) => (x ? { ...x, f: { ...x.f, ...m } } : x));
  return (
    <section aria-label="variações do texto" id="anuncio-variantes">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rotulo-campo">Variações do texto</span>
        {podeEditar && lista.length < MAXIMO && !editando && (
          <button type="button" className="link-acao" id="variante-nova" onClick={() => setEditando({ id: null, f: vazia() })}>
            + variação
          </button>
        )}
      </div>
      <p className="mt-1 text-[12.5px] text-suave">
        Teste outro título ou texto: as visitas se dividem entre a original e as variações, e o relatório diz qual faz
        mais gente tocar. A foto, o vídeo e o destino do botão são os mesmos. No máximo {MAXIMO} — cada uma divide as
        visitas, e o teste demora mais.
      </p>
      {lista.length > 0 && (
        <ul className="mt-2 flex flex-col gap-px bg-linha">
          {lista.map((v, n) => (
            <li key={v.id} className="bg-superficie2 px-3 py-2 text-[13.5px]" data-variante={v.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono text-[12px] text-suave">{String.fromCharCode(66 + n)}</span>
                <span className="min-w-0 flex-1 truncate font-semibold">{v.titulo || v.texto}</span>
                {!v.ativo && <span className="text-[12px] text-suave">desligada</span>}
                {podeEditar && (
                  <>
                    <button type="button" className="link-acao"
                            onClick={() => setEditando({ id: v.id, f: { titulo: v.titulo, texto: v.texto, acao_rotulo: v.acao_rotulo, ativo: v.ativo } })}>
                      editar
                    </button>
                    <button type="button" className="link-acao" onClick={() => setTraduzindo(traduzindo === v.id ? null : v.id)}>
                      traduções
                    </button>
                    <button type="button" className="link-acao link-acao-erro" onClick={() => void remover(v)}>tirar</button>
                  </>
                )}
              </div>
              {traduzindo === v.id && (
                <div className="mt-2">
                  <Traducoes key={`${v.titulo}|${v.texto}`} tipo="anuncio_variante" id={v.id}
                             rotulos={{ nome: "Título", descricao: "Texto" }} maxNome={120} maxDescricao={500} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {editando && (
        <div className="mt-3 flex flex-col gap-2 rounded-lg border border-linha p-3">
          <input id="variante-titulo" className="campo" maxLength={120} placeholder={`Título (o original: ${anuncio.titulo ?? "—"})`}
                 value={editando.f.titulo ?? ""} onChange={(e) => mudar({ titulo: txt(e.target.value) })} />
          <textarea id="variante-texto" className="campo" rows={2} maxLength={500} placeholder="Texto"
                    value={editando.f.texto ?? ""} onChange={(e) => mudar({ texto: txt(e.target.value) })} />
          <input className="campo" maxLength={40} placeholder={`Texto do botão (vazio = ${anuncio.acao_rotulo ?? "o do anúncio"})`}
                 value={editando.f.acao_rotulo ?? ""} onChange={(e) => mudar({ acao_rotulo: txt(e.target.value) })} />
          <label className="flex items-center gap-2 text-[13.5px]">
            <input type="checkbox" checked={editando.f.ativo} onChange={(e) => mudar({ ativo: e.target.checked })} /> Ligada
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secundario" onClick={() => setEditando(null)}>Cancelar</button>
            <button type="button" id="variante-gravar" className="btn btn-primario" aria-busy={gravando}
                    disabled={gravando || !(editando.f.titulo || editando.f.texto)} onClick={() => void gravar()}>
              Gravar variação
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
