"use client";

/**
 * A parte do Cardápio Vivo (113) na aba Catálogo do produto: vídeo, restrições e adicionais.
 *
 * 🔑 **No produto, não no item do catálogo** (decisão do dono, 14/10/2026): o mesmo prato
 * em duas listas tem o mesmo vídeo, as mesmas restrições e os mesmos adicionais.
 * ⚠️ Mora DENTRO do `<form>` do produto, mas grava por rotas próprias: todo botão aqui é
 * `type="button"`, senão salvaria o produto inteiro junto.
 */

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Cartao } from "@/components/ui";
import { api, urlArquivo } from "@/lib/api";
import { ProdutoCardapioService, type CardapioDoProduto, type GrupoAdicionalCadastro } from "@/lib/cardapio-vivo";

type Props = { idProduto: number; podeEditar: boolean };

export default function CardapioVivoDoProduto({ idProduto, podeEditar }: Props) {
  const aviso = useAviso();
  const [dados, setDados] = useState<CardapioDoProduto | null>(null);
  const [grupos, setGrupos] = useState<GrupoAdicionalCadastro[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    ProdutoCardapioService.obter(idProduto)
      .then((d) => { setDados(d); setGrupos(d.adicionais); })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, [idProduto]);

  const falhou = (e: unknown, padrao: string) => aviso.erro(e instanceof Error ? e.message : padrao);

  async function enviarVideo(arquivo: File | undefined) {
    if (!arquivo) return;
    setEnviando(true);
    try {
      const r = await ProdutoCardapioService.enviarVideo(idProduto, arquivo);
      setDados((d) => d && { ...d, video: r.video });
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível enviar o vídeo.");
    } finally {
      setEnviando(false);
    }
  }

  async function tirarVideo() {
    try {
      const r = await ProdutoCardapioService.removerVideo(idProduto);
      setDados((d) => d && { ...d, video: null });
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível tirar o vídeo.");
    }
  }

  async function alternarRestricao(chave: string) {
    if (!dados) return;
    const novas = dados.restricoes.includes(chave)
      ? dados.restricoes.filter((r) => r !== chave) : [...dados.restricoes, chave];
    try {
      const r = await ProdutoCardapioService.restricoes(idProduto, novas);
      setDados({ ...dados, restricoes: r.restricoes });
    } catch (e) {
      falhou(e, "Não foi possível gravar a restrição.");
    }
  }

  async function gravarAdicionais() {
    try {
      const r = await ProdutoCardapioService.adicionais(idProduto, grupos);
      setGrupos(r.adicionais);
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível gravar os adicionais.");
    }
  }

  const mudarGrupo = (n: number, g: Partial<GrupoAdicionalCadastro>) =>
    setGrupos((gs) => gs.map((x, i) => (i === n ? { ...x, ...g } : x)));
  const mudarOpcao = (n: number, o: number, mud: Partial<GrupoAdicionalCadastro["opcoes"][number]>) =>
    mudarGrupo(n, { opcoes: grupos[n].opcoes.map((x, i) => (i === o ? { ...x, ...mud } : x)) });

  async function apontarProduto(n: number, o: number) {
    const busca = prompt("Nome do produto que este adicional representa (vazio = só texto):");
    if (busca === null) return;
    if (!busca.trim()) { mudarOpcao(n, o, { id_produto_ref: null, produto_ref: null }); return; }
    try {
      const achados = await api.get<{ id: number; nome: string }[]>(
        `/catalogos/produtos-disponiveis?busca=${encodeURIComponent(busca.trim())}`);
      if (!achados.length) { aviso.erro("Nenhum produto ativo do PDV com esse nome."); return; }
      const p = achados[0];
      mudarOpcao(n, o, { id_produto_ref: p.id, produto_ref: p.nome, preco: null });
      aviso.sucesso(`Ligado a ${p.nome}${achados.length > 1 ? ` (havia ${achados.length}; refine se não for este)` : ""}.`);
    } catch (e) {
      falhou(e, "Falha ao buscar o produto.");
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return null;
  const v = dados.video;

  return (
    <Cartao titulo="Cardápio Vivo" descricao="O feed da mesa: vídeo, restrições alimentares e adicionais.">
      <div className="flex flex-col gap-6">
        <section>
          <h3 className="text-[14px] font-bold">Vídeo</h3>
          <p className="text-[13px] text-suave">
            Até 15 s, sem som. Convertido no envio para MP4 de ~2 MB; a capa sai do primeiro quadro.
            Com vídeo, ele aparece no lugar da foto.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            {v && (
              <video src={urlArquivo(v.url) ?? undefined} poster={urlArquivo(v.capa) ?? undefined}
                     muted loop playsInline controls className="h-40 rounded-lg border border-linha" />
            )}
            {v && (
              <span className="text-[13px] text-suave">
                {v.nome ?? "vídeo"} · {v.segundos?.toFixed(0)} s · {(v.bytes / 1048576).toFixed(1)} MB
              </span>
            )}
            {podeEditar && (
              <span className="flex gap-3">
                <label className={`btn btn-secundario relative cursor-pointer ${enviando ? "opacity-60" : ""}`}>
                  {enviando ? "Convertendo…" : v ? "Trocar vídeo" : "Enviar vídeo"}
                  <input type="file" accept="video/mp4,video/quicktime,video/webm" className="sr-only"
                         disabled={enviando} onChange={(e) => void enviarVideo(e.target.files?.[0])} />
                </label>
                {v && <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarVideo()}>tirar</button>}
              </span>
            )}
          </div>
        </section>

        <section>
          <h3 className="text-[14px] font-bold">Restrições alimentares</h3>
          <div className="mt-2 flex flex-wrap gap-4 text-[14px]">
            {dados.opcoes_restricoes.map((r) => (
              <label key={r.chave} className="flex items-center gap-2">
                <input type="checkbox" disabled={!podeEditar} checked={dados.restricoes.includes(r.chave)}
                       onChange={() => void alternarRestricao(r.chave)} />
                {r.nome}
              </label>
            ))}
          </div>
        </section>

        <section>
          <h3 className="text-[14px] font-bold">Adicionais e opções</h3>
          <p className="text-[13px] text-suave">
            Grupos com mínimo e máximo de escolhas (ex.: “Ponto da carne”, escolha 1). A opção ligada a um
            produto usa o preço dele na loja.
          </p>
          {grupos.map((g, n) => (
            <div key={n} className="mt-3 rounded-lg border border-linha p-3">
              <div className="flex flex-wrap items-center gap-2">
                <input className="campo !w-auto flex-1" placeholder="Nome do grupo" disabled={!podeEditar}
                       value={g.nome} onChange={(e) => mudarGrupo(n, { nome: e.target.value })} />
                mín <input className="campo mono !w-16" type="number" min={0} disabled={!podeEditar}
                           value={g.minimo} onChange={(e) => mudarGrupo(n, { minimo: Number(e.target.value) })} />
                máx <input className="campo mono !w-16" type="number" min={1} disabled={!podeEditar}
                           value={g.maximo} onChange={(e) => mudarGrupo(n, { maximo: Number(e.target.value) })} />
                {podeEditar && <button type="button" className="link-acao link-acao-erro"
                                       onClick={() => setGrupos((gs) => gs.filter((_, i) => i !== n))}>tirar grupo</button>}
              </div>
              {g.opcoes.map((o, k) => (
                <div key={k} className="mt-2 flex flex-wrap items-center gap-2 pl-3 text-[14px]">
                  <input className="campo !w-auto flex-1" placeholder="Opção" disabled={!podeEditar}
                         value={o.nome} onChange={(e) => mudarOpcao(n, k, { nome: e.target.value })} />
                  {o.id_produto_ref ? (
                    <span className="text-[13px] text-suave">preço de {o.produto_ref}</span>
                  ) : (
                    <input className="campo mono !w-24" type="number" min={0} step="0.01" placeholder="+ R$"
                           disabled={!podeEditar} value={o.preco ?? ""}
                           onChange={(e) => mudarOpcao(n, k, { preco: e.target.value === "" ? null : Number(e.target.value) })} />
                  )}
                  {podeEditar && (
                    <>
                      <button type="button" className="link-acao text-[13px]" onClick={() => void apontarProduto(n, k)}>
                        {o.id_produto_ref ? "trocar produto" : "ligar a produto"}
                      </button>
                      <button type="button" className="link-acao link-acao-erro text-[13px]"
                              onClick={() => mudarGrupo(n, { opcoes: g.opcoes.filter((_, i) => i !== k) })}>×</button>
                    </>
                  )}
                </div>
              ))}
              {podeEditar && (
                <button type="button" className="link-acao mt-2 pl-3 text-[13px]"
                        onClick={() => mudarGrupo(n, { opcoes: [...g.opcoes, { nome: "", preco: null, id_produto_ref: null, ativo: true }] })}>
                  + opção
                </button>
              )}
            </div>
          ))}
          {podeEditar && (
            <div className="mt-3 flex justify-between">
              <button type="button" className="link-acao"
                      onClick={() => setGrupos((gs) => [...gs, { nome: "", minimo: 0, maximo: 1,
                                                               opcoes: [{ nome: "", preco: null, id_produto_ref: null, ativo: true }] }])}>
                + grupo de adicionais
              </button>
              <button type="button" className="btn btn-secundario" onClick={() => void gravarAdicionais()}>
                Gravar adicionais
              </button>
            </div>
          )}
        </section>
      </div>
    </Cartao>
  );
}
