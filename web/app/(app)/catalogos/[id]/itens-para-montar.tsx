"use client";

/**
 * "Itens para montar": a regra de cada opção do item de escolha, DENTRO do catálogo.
 *
 * 🔑 **Pedido do dono (30/10/2026):** *"adicionar um Monte sua cesta, onde coloco 3 produtos
 * embalagem, P, M e G. Ao selecionar um dos 3, irá ter uma regra de produtos selecionáveis máximo
 * e mínimo, e vai habilitar a seleção dos produtos que posso colocar na cesta"* — e a primeira
 * versão (1.1.153) deixava essa regra na aba Catálogo de CADA produto-embalagem, com "ligar a
 * produto" por janelinha de texto que pegava o primeiro nome parecido.
 *
 * ⚠️ **Por baixo é o MESMO dado**: os grupos de adicionais do produto da opção
 * (`PUT /produtos/{id}/adicionais`, permissão `cadastros.produtos`). O site, a mesa e o pedido
 * não mudam; o que muda é onde a casa mexe. E valem em todo cardápio em que a embalagem estiver.
 */

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import * as cat from "@/lib/catalogos";
import { ProdutoCardapioService, type GrupoAdicionalCadastro } from "@/lib/cardapio-vivo";

type Opcao = { id_produto: number; nome: string };

const semIds = (gs: GrupoAdicionalCadastro[]): GrupoAdicionalCadastro[] =>
  gs.map(({ id: _g, ...g }) => ({ ...g, opcoes: g.opcoes.map(({ id: _o, ...o }) => o) }));

export default function ItensParaMontar({ opcao, outras, podeEditar }: {
  opcao: Opcao; outras: Opcao[]; podeEditar: boolean;
}) {
  const aviso = useAviso();
  const [grupos, setGrupos] = useState<GrupoAdicionalCadastro[] | null>(null);
  const [gravado, setGravado] = useState("");
  const [gravando, setGravando] = useState(false);
  const [escolhendo, setEscolhendo] = useState<number | null>(null);
  const falhou = (e: unknown, padrao: string) => aviso.erro(e instanceof Error ? e.message : padrao);

  useEffect(() => {
    ProdutoCardapioService.obter(opcao.id_produto)
      .then((d) => { setGrupos(d.adicionais); setGravado(JSON.stringify(semIds(d.adicionais))); })
      .catch(() => setGrupos([]));
  }, [opcao.id_produto]);

  if (!grupos) return <p className="text-[13px] text-suave">Carregando os itens…</p>;
  const mudou = JSON.stringify(semIds(grupos)) !== gravado;

  const mudarGrupo = (n: number, g: Partial<GrupoAdicionalCadastro>) =>
    setGrupos(grupos.map((x, i) => (i === n ? { ...x, ...g } : x)));
  const novoGrupo = () => setGrupos([...grupos, {
    nome: grupos.length ? "Extras" : "Itens", minimo: grupos.length ? 0 : 1, maximo: grupos.length ? 1 : 3,
    permite_repetir: !grupos.length, opcoes: [] }]);

  async function copiarDe(outra: Opcao) {
    try {
      const d = await ProdutoCardapioService.obter(outra.id_produto);
      if (!d.adicionais.length) { aviso.erro(`${outra.nome} ainda não tem itens.`); return; }
      setGrupos(semIds(d.adicionais));
      aviso.sucesso(`Lista de ${outra.nome} copiada. Ajuste o mínimo e o máximo e grave.`);
    } catch (e) {
      falhou(e, "Não foi possível copiar.");
    }
  }

  async function gravar() {
    if (!grupos) return;
    const vazio = grupos.find((g) => !g.nome.trim() || !g.opcoes.length);
    if (vazio) { aviso.erro(vazio.nome.trim() ? `“${vazio.nome}” está sem itens.` : "Dê um nome a cada grupo."); return; }
    setGravando(true);
    try {
      const r = await ProdutoCardapioService.adicionais(opcao.id_produto, grupos);
      setGrupos(r.adicionais);
      setGravado(JSON.stringify(semIds(r.adicionais)));
      aviso.sucesso(`Itens de ${opcao.nome} gravados.`);
    } catch (e) {
      falhou(e, "Não foi possível gravar os itens.");
    } finally {
      setGravando(false);
    }
  }

  return (
    <div className="flex flex-col gap-3" data-montar={opcao.id_produto}>
      {grupos.length === 0 && (
        <p className="text-[13px] text-suave">
          Sem itens: o cliente escolhe {opcao.nome} e já adiciona. Para montar (a cesta), crie a lista.
        </p>
      )}
      {grupos.map((g, n) => (
        <div key={n} className="rounded-md border border-linha p-3">
          <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
            <input className="campo !w-auto min-w-0 flex-1" aria-label="nome do grupo" placeholder="Nome (ex.: Itens da cesta)"
                   maxLength={80} disabled={!podeEditar} value={g.nome}
                   onChange={(e) => mudarGrupo(n, { nome: e.target.value })} />
            <label className="flex items-center gap-1">mín
              <input className="campo mono !w-14" type="number" min={0} max={30} aria-label="mínimo" disabled={!podeEditar}
                     value={g.minimo} onChange={(e) => mudarGrupo(n, { minimo: Number(e.target.value) })} />
            </label>
            <label className="flex items-center gap-1">máx
              <input className="campo mono !w-14" type="number" min={1} max={30} aria-label="máximo" disabled={!podeEditar}
                     value={g.maximo} onChange={(e) => mudarGrupo(n, { maximo: Number(e.target.value) })} />
            </label>
            <label className="flex items-center gap-1.5" title="O mesmo item mais de uma vez (2 geleias); o mínimo e o máximo contam unidades.">
              <input type="checkbox" disabled={!podeEditar} checked={!!g.permite_repetir} aria-label="pode repetir"
                     onChange={(e) => mudarGrupo(n, { permite_repetir: e.target.checked })} />
              pode repetir
            </label>
            {podeEditar && (
              <button type="button" className="link-acao link-acao-erro"
                      onClick={() => setGrupos(grupos.filter((_, i) => i !== n))}>tirar grupo</button>
            )}
          </div>
          <ul className="mt-2 flex flex-col gap-1 text-[13.5px]">
            {g.opcoes.map((o, k) => (
              <li key={k} className="flex flex-wrap items-center gap-2 border-t border-linha pt-1">
                <span className="min-w-0 flex-1 truncate">{o.nome}
                  {!o.ativo && <span className="text-alerta"> · inativo</span>}
                </span>
                <span className="text-[12.5px] text-suave">
                  {o.incluso ? "incluso (R$ 0)" : o.id_produto_ref ? "preço do produto" : o.preco !== null ? `+ R$ ${o.preco}` : "sem acréscimo"}
                </span>
                <label className="flex items-center gap-1 text-[12.5px]">
                  <input type="checkbox" disabled={!podeEditar} checked={!!o.incluso} aria-label={`${o.nome} incluso`}
                         onChange={(e) => mudarGrupo(n, { opcoes: g.opcoes.map((x, i) => (i === k ? { ...x, incluso: e.target.checked } : x)) })} />
                  incluso
                </label>
                {podeEditar && (
                  <button type="button" className="link-acao link-acao-erro" aria-label={`tirar ${o.nome}`}
                          onClick={() => mudarGrupo(n, { opcoes: g.opcoes.filter((_, i) => i !== k) })}>×</button>
                )}
              </li>
            ))}
          </ul>
          {podeEditar && (
            <button type="button" className="link-acao mt-2 text-[13px]" onClick={() => setEscolhendo(n)}>+ itens</button>
          )}
        </div>
      ))}
      {podeEditar && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[13.5px]">
          <button type="button" className="link-acao" onClick={novoGrupo}>
            {grupos.length ? "+ outro grupo" : "+ criar a lista de itens"}
          </button>
          {outras.map((o) => (
            <button key={o.id_produto} type="button" className="link-acao" onClick={() => void copiarDe(o)}>
              usar a mesma lista de {o.nome}
            </button>
          ))}
          <button type="button" className="btn btn-secundario ml-auto" aria-busy={gravando}
                  disabled={gravando || !mudou} onClick={() => void gravar()}>
            {gravando ? "Gravando…" : `Gravar itens de ${opcao.nome}`}
          </button>
        </div>
      )}
      {escolhendo !== null && (
        <JanelaItens jaEstao={new Set(grupos[escolhendo].opcoes.map((o) => o.id_produto_ref ?? 0))}
                     idDaOpcao={opcao.id_produto}
                     aoFechar={() => setEscolhendo(null)}
                     aoPor={(ps) => {
                       const g = grupos[escolhendo];
                       mudarGrupo(escolhendo, { opcoes: [...g.opcoes, ...ps.map((p) => ({
                         nome: p.nome, preco: null, id_produto_ref: p.id, produto_ref: p.nome, ativo: true, incluso: false }))] });
                       setEscolhendo(null);
                     }} />
      )}
    </div>
  );
}

/** Marcar VÁRIOS produtos de uma vez, como o "+ pratos". */
function JanelaItens({ jaEstao, idDaOpcao, aoFechar, aoPor }: {
  jaEstao: Set<number>; idDaOpcao: number; aoFechar: () => void; aoPor: (p: cat.ProdutoDisponivel[]) => void;
}) {
  const [busca, setBusca] = useState("");
  const [achados, setAchados] = useState<cat.ProdutoDisponivel[]>([]);
  const [marcados, setMarcados] = useState<cat.ProdutoDisponivel[]>([]);

  useEffect(() => {
    let valeu = true;
    // ⚠️ Espera antes de consultar: a resposta do "c" pode chegar depois da do "café".
    const t = setTimeout(() => {
      cat.produtosDisponiveis(busca).then((r) => valeu && setAchados(r)).catch(() => valeu && setAchados([]));
    }, 300);
    return () => { valeu = false; clearTimeout(t); };
  }, [busca]);

  const alternar = (p: cat.ProdutoDisponivel) =>
    setMarcados((x) => (x.some((m) => m.id === p.id) ? x.filter((m) => m.id !== p.id) : [...x, p]));

  return (
    <Modal titulo="Pôr itens" descricao="Marque os produtos que o cliente pode pôr. O preço é o de cada produto na loja."
           aoFechar={aoFechar}
           rodape={
             <div className="flex justify-end gap-2">
               <button type="button" className="btn btn-secundario" onClick={aoFechar}>Cancelar</button>
               <button type="button" className="btn btn-primario" id="itens-por" disabled={!marcados.length}
                       onClick={() => aoPor(marcados)}>
                 {marcados.length === 1 ? "Pôr 1 item" : `Pôr ${marcados.length} itens`}
               </button>
             </div>
           }>
      <div className="flex flex-col gap-3">
        <Campo rotulo="Procurar" dica="Só produtos ativos e vendidos no PDV.">
          <input className="campo" id="itens-busca" autoFocus placeholder="nome ou código"
                 value={busca} onChange={(e) => setBusca(e.target.value)} />
        </Campo>
        <ul className="lista-rolante flex flex-col gap-px bg-linha text-[14px]">
          {achados.filter((p) => p.id !== idDaOpcao).map((p) => {
            const esta = jaEstao.has(p.id);
            return (
              <li key={p.id} className="bg-superficie">
                <label className={`flex items-center gap-3 py-2 ${esta ? "opacity-60" : "cursor-pointer"}`}>
                  <input type="checkbox" disabled={esta} checked={esta || marcados.some((m) => m.id === p.id)}
                         aria-label={p.nome} onChange={() => alternar(p)} />
                  <span className="min-w-0 flex-1 truncate">{p.nome}</span>
                  <span className="mono shrink-0 text-[12.5px] text-suave">{esta ? "já está" : p.codigo}</span>
                </label>
              </li>
            );
          })}
        </ul>
      </div>
    </Modal>
  );
}
