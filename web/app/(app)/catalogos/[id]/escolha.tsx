"use client";

/**
 * O ITEM DE ESCOLHA no editor do cardápio (migração 142).
 *
 * 🔑 **Pedido do dono (29/10/2026):** *"Chocolate Quente (este não é um produto): ao
 * selecionar, tem a escolha Preto ou Branco — estes são o produto"*; e "Monte sua cesta"
 * com as embalagens Pequena, Média e Grande. Estudo em `docs/item-de-escolha-estudo.md`.
 *
 * O item tem nome, descrição e foto PRÓPRIOS (não é produto) e uma lista de opções — cada
 * uma um produto, com um rótulo curto opcional. Os adicionais (os itens da cesta, com
 * mínimo e máximo) ficam no cadastro de cada produto-opção, aba Catálogo.
 * ⚠️ A lista vai INTEIRA a cada gravação, na ordem da tela.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import { urlArquivo } from "@/lib/api";
import * as cat from "@/lib/catalogos";
import { reais } from "@/lib/numeros";

/** Uma opção na tela: o produto e o rótulo que o cliente lê. */
export type OpcaoNaTela = {
  id_produto: number; produto: string; rotulo: string;
  ativo?: boolean; preco?: number | null;
};

const paraGravar = (opcoes: OpcaoNaTela[]) =>
  opcoes.map((o) => ({ id_produto: o.id_produto, rotulo: o.rotulo.trim() || null }));

/** A lista de opções: rótulo, ordem, tirar e procurar produto para pôr. */
export function EditorDeOpcoes({ opcoes, aoMudar, podeEditar }: {
  opcoes: OpcaoNaTela[]; aoMudar: (o: OpcaoNaTela[]) => void; podeEditar: boolean;
}) {
  const [busca, setBusca] = useState("");
  const [achados, setAchados] = useState<cat.ProdutoDisponivel[]>([]);

  useEffect(() => {
    if (!busca.trim()) { setAchados([]); return; }
    let valeu = true;
    // ⚠️ Espera antes de consultar: a resposta do "c" pode chegar depois da do "café".
    const t = setTimeout(() => {
      cat.produtosDisponiveis(busca.trim()).then((r) => valeu && setAchados(r.slice(0, 8)))
        .catch(() => valeu && setAchados([]));
    }, 300);
    return () => { valeu = false; clearTimeout(t); };
  }, [busca]);

  const mover = (n: number, passo: number) => {
    const fila = [...opcoes];
    [fila[n], fila[n + passo]] = [fila[n + passo], fila[n]];
    aoMudar(fila);
  };

  return (
    <div className="flex flex-col gap-2">
      {opcoes.length === 0 && (
        <p className="text-[13.5px] text-suave">Nenhuma opção ainda. Procure abaixo os produtos (pelo menos dois).</p>
      )}
      <ul className="flex flex-col gap-2" aria-label="opções do item">
        {opcoes.map((o, n) => (
          <li key={o.id_produto} className="flex flex-wrap items-center gap-2 rounded-md border border-linha px-3 py-2">
            <span className="min-w-0 flex-1 basis-40">
              <span className="block truncate text-[14px]">{o.produto}</span>
              <span className="block text-[12.5px] text-suave">
                {o.preco !== undefined && (o.preco !== null ? reais(o.preco) : "sem preço")}
                {o.ativo === false && <span className="text-alerta"> · produto inativo (o cliente não vê)</span>}
              </span>
            </span>
            <input className="campo !w-36" placeholder="rótulo (ex.: Branco)" maxLength={60}
                   aria-label={`rótulo de ${o.produto}`} disabled={!podeEditar} value={o.rotulo}
                   onChange={(e) => aoMudar(opcoes.map((x, i) => (i === n ? { ...x, rotulo: e.target.value } : x)))} />
            {podeEditar && (
              <span className="flex gap-1">
                <button type="button" className="link-acao" disabled={n === 0}
                        aria-label={`subir ${o.produto}`} onClick={() => mover(n, -1)}>↑</button>
                <button type="button" className="link-acao" disabled={n === opcoes.length - 1}
                        aria-label={`descer ${o.produto}`} onClick={() => mover(n, 1)}>↓</button>
                <button type="button" className="link-acao link-acao-erro" aria-label={`tirar ${o.produto}`}
                        onClick={() => aoMudar(opcoes.filter((_, i) => i !== n))}>×</button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {podeEditar && (
        <div className="flex flex-col gap-1.5">
          <input className="campo" id="escolha-busca" placeholder="procurar produto para pôr como opção"
                 value={busca} onChange={(e) => setBusca(e.target.value)} />
          {achados.length > 0 && (
            <ul className="flex flex-col gap-px rounded-md border border-linha bg-linha text-[14px]">
              {achados.map((p) => {
                const ja = opcoes.some((o) => o.id_produto === p.id);
                return (
                  <li key={p.id} className="bg-superficie">
                    <button type="button" disabled={ja}
                            className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-superficie2 disabled:opacity-60"
                            onClick={() => { aoMudar([...opcoes, { id_produto: p.id, produto: p.nome, rotulo: "" }]); setBusca(""); }}>
                      <span className="min-w-0 truncate">{p.nome}</span>
                      <span className="mono shrink-0 text-[12.5px] text-suave">{ja ? "já é opção" : "+ pôr"}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="text-[12.5px] text-suave">Só produtos ativos e vendidos no PDV: a opção é o que vai no pedido.</p>
        </div>
      )}
    </div>
  );
}

/** Criar um item de escolha na seção. */
export function JanelaEscolha({ idCategoria, idSubcategoria, onde, aoFechar, aoCriar }: {
  idCategoria: number; idSubcategoria: number | null; onde: string;
  aoFechar: () => void; aoCriar: (id: number) => Promise<void>;
}) {
  const aviso = useAviso();
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [opcoes, setOpcoes] = useState<OpcaoNaTela[]>([]);
  const [gravando, setGravando] = useState(false);
  const pronto = nome.trim() && opcoes.length >= 2;

  async function criar() {
    setGravando(true);
    try {
      const r = await cat.criarEscolha(idCategoria, {
        nome: nome.trim(), descricao: descricao.trim() || null, id_subcategoria: idSubcategoria,
        opcoes: paraGravar(opcoes),
      });
      aviso.sucesso(r.message);
      aoFechar();
      await aoCriar(r.id);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível criar.");
    } finally {
      setGravando(false);
    }
  }

  return (
    <Modal titulo="Novo item de escolha"
           descricao={`Entrando em ${onde}. O cliente toca nele e escolhe UMA das opções — é a opção (um produto) que vai no pedido.`}
           aoFechar={aoFechar}
           rodape={
             <div className="flex items-center justify-end gap-2">
               <button type="button" className="btn btn-secundario" onClick={aoFechar}>Cancelar</button>
               <button type="button" className="btn btn-primario" id="escolha-criar" aria-busy={gravando}
                       disabled={gravando || !pronto} onClick={() => void criar()}>
                 {gravando ? "Criando…" : "Criar item"}
               </button>
             </div>
           }>
      <div className="flex flex-col gap-4">
        <Campo rotulo="Nome" dica="Ex.: Chocolate Quente; Monte sua cesta.">
          <input className="campo" id="escolha-nome" autoFocus maxLength={120}
                 value={nome} onChange={(e) => setNome(e.target.value)} />
        </Campo>
        <Campo rotulo="Descrição" dica="Opcional. O que o cliente lê embaixo do nome.">
          <textarea className="campo" id="escolha-descricao" rows={2} maxLength={2000}
                    value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </Campo>
        <div>
          <span className="rotulo">Opções</span>
          <div className="mt-1.5"><EditorDeOpcoes opcoes={opcoes} aoMudar={setOpcoes} podeEditar /></div>
        </div>
      </div>
    </Modal>
  );
}

/** Na gaveta do item: foto, nome, descrição e as opções. */
export function SecaoDaEscolha({ item: i, podeEditar, aoMudar }: {
  item: cat.ItemDoCatalogo; podeEditar: boolean; aoMudar: () => Promise<void>;
}) {
  const aviso = useAviso();
  const doServidor = (): OpcaoNaTela[] => (i.escolhas ?? []).map((o) => ({
    id_produto: o.id_produto, produto: o.produto, rotulo: o.rotulo ?? "", ativo: o.ativo,
    preco: o.preco === null ? null : Number(o.preco),
  }));
  const [nome, setNome] = useState(i.produto);
  const [descricao, setDescricao] = useState(i.informacao_adicional ?? "");
  const [opcoes, setOpcoes] = useState<OpcaoNaTela[]>(doServidor);
  const [gravando, setGravando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const falhou = (e: unknown, padrao: string) => aviso.erro(e instanceof Error ? e.message : padrao);

  const mudou = nome.trim() !== i.produto || descricao.trim() !== (i.informacao_adicional ?? "")
    || JSON.stringify(paraGravar(opcoes)) !== JSON.stringify(paraGravar(doServidor()));

  async function gravar() {
    setGravando(true);
    try {
      const r = await cat.atualizarEscolha(i.id, {
        nome: nome.trim(), descricao: descricao.trim() || null, opcoes: paraGravar(opcoes),
      });
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível salvar.");
    } finally {
      setGravando(false);
    }
  }

  async function foto(arquivo: File | undefined) {
    if (!arquivo) return;
    setEnviando(true);
    try {
      await cat.enviarFotoDoItem(i.id, arquivo);
      await aoMudar();
      aviso.sucesso("Foto atualizada.");
    } catch (e) {
      falhou(e, "Não foi possível enviar a foto.");
    } finally {
      setEnviando(false);
    }
  }

  async function tirarFoto() {
    try {
      await cat.removerFotoDoItem(i.id);
      await aoMudar();
      aviso.sucesso("Foto removida.");
    } catch (e) {
      falhou(e, "Não foi possível tirar a foto.");
    }
  }

  return (
    <section className="flex flex-col gap-3 border-t border-linha pt-5">
      <h3 className="rotulo">O item de escolha</h3>
      <p className="text-[13px] text-suave">
        Não é um produto: o cliente toca nele e escolhe uma opção. Os adicionais de cada opção (os itens
        da cesta, com mínimo e máximo) ficam no cadastro do produto dela, aba Catálogo.
      </p>
      <div className="flex items-center gap-3">
        <span className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-linha bg-superficie2">
          {i.foto_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={urlArquivo(i.foto_url) ?? undefined} alt="" className="h-full w-full object-cover" />
          ) : (
            <span className="text-[12px] text-suave">sem foto</span>
          )}
        </span>
        {podeEditar && (
          <span className="flex flex-col items-start gap-2">
            {/* ⚠️ `relative`: o input `sr-only` é absoluto e, sem ancestral posicionado, faz a página rolar de lado. */}
            <label className={`btn btn-secundario relative cursor-pointer ${enviando ? "opacity-60" : ""}`}>
              {enviando ? "Enviando…" : i.foto_url ? "Trocar foto" : "Pôr foto"}
              <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" id="escolha-foto"
                     disabled={enviando} onChange={(e) => { void foto(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            {i.foto_url && (
              <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarFoto()}>tirar foto</button>
            )}
          </span>
        )}
      </div>
      <Campo rotulo="Nome">
        <input className="campo" id="escolha-nome-gaveta" maxLength={120} disabled={!podeEditar}
               value={nome} onChange={(e) => setNome(e.target.value)} />
      </Campo>
      <Campo rotulo="Descrição">
        <textarea className="campo" rows={3} maxLength={2000} disabled={!podeEditar}
                  value={descricao} onChange={(e) => setDescricao(e.target.value)} />
      </Campo>
      <div>
        <span className="rotulo">Opções</span>
        <div className="mt-1.5"><EditorDeOpcoes opcoes={opcoes} aoMudar={setOpcoes} podeEditar={podeEditar} /></div>
        {opcoes.length > 0 && (
          <p className="mt-2 text-[12.5px] text-suave">
            Adicionais de uma opção:{" "}
            {opcoes.map((o, n) => (
              <span key={o.id_produto}>{n > 0 && " · "}
                <Link href={`/produtos/${o.id_produto}`} className="link-registro">{o.rotulo.trim() || o.produto}</Link>
              </span>
            ))}
          </p>
        )}
      </div>
      {podeEditar && (
        <div className="flex justify-end">
          <button type="button" className="btn btn-primario" id="escolha-salvar" aria-busy={gravando}
                  disabled={gravando || !mudou || !nome.trim() || opcoes.length < 2} onClick={() => void gravar()}>
            {gravando ? "Salvando…" : "Salvar item"}
          </button>
        </div>
      )}
    </section>
  );
}
