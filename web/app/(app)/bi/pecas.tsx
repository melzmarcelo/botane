"use client";

import { useEffect, useState } from "react";

import { Modal } from "@/components/ui";
import { api } from "@/lib/api";
import {
  type CatalogoBI, type ColunaBI, type DefinicaoBI, formatar, type LigacaoManual,
  type ResultadoBI, type TipoLigacao, type Visibilidade,
} from "@/lib/bi";

/** As peças do Estúdio BI (layout novo, fase 4 — 05/11/2026). O estado mora na página. */

type Mudar = (f: (d: DefinicaoBI) => DefinicaoBI) => void;

const Passo = ({ n, titulo, children }: { n: number; titulo: string; children: React.ReactNode }) => (
  <section className="cartao p-4 sm:p-5">
    <h2 className="mb-3 flex items-center gap-2.5 text-[15px] font-bold">
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-erva-claro text-[12px] font-extrabold text-erva">{n}</span>
      {titulo}
    </h2>
    {children}
  </section>
);

const Marca = ({ ligada }: { ligada: boolean }) => (
  <span className={`inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-md border-[1.5px] ${
    ligada ? "border-erva bg-erva" : "border-linha2 bg-superficie"}`}>
    {ligada && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3.4"
                    strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M20 6 9 17l-5-5" /></svg>}
  </span>
);

export function PassoFontes({ cat, d, mudar }: { cat: CatalogoBI; d: DefinicaoBI; mudar: Mudar }) {
  const alternar = (k: string) => mudar((x) => {
    const tem = x.fontes.includes(k);
    const exige = (c: string) => cat.fontes.find((f) => f.chave === c)?.exige ?? [];
    // Marcar Itens da venda marca Vendas junto (é por ela que se sabe a loja); desmarcar Vendas
    // tira junto quem depende dela.
    const fontes = tem
      ? x.fontes.filter((f) => f !== k && !exige(f).includes(k))
      : [...new Set([...x.fontes, ...exige(k), k])];
    const validos = new Set(cat.fontes.filter((f) => fontes.includes(f.chave)).flatMap((f) => f.campos.map((c) => c.chave)));
    return {
      ...x, fontes,
      dimensoes: x.dimensoes.filter((c) => validos.has(c)),
      medidas: x.medidas.filter((c) => validos.has(c)),
      manuais: x.manuais.filter((m) => fontes.includes(m.a) && fontes.includes(m.b)),
    };
  });
  return (
    <Passo n={1} titulo="Fontes de dados">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" id="bi-fontes">
        {cat.fontes.map((f) => {
          const on = d.fontes.includes(f.chave);
          return (
            <button key={f.chave} type="button" aria-pressed={on} data-fonte={f.chave} title={f.descricao}
                    onClick={() => alternar(f.chave)}
                    className={`flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left text-[14px] font-semibold transition-colors ${
                      on ? "border-erva/50 bg-erva-claro" : "border-linha bg-superficie hover:border-linha2"}`}>
              <Marca ligada={on} />{f.rotulo}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[12.5px] text-suave">
        Itens da venda entram junto com Vendas, e itens da nota com Notas: é por elas que se sabe a loja.
      </p>
    </Passo>
  );
}

export function PassoLigacoes({ cat, d, mudar, soltas }: { cat: CatalogoBI; d: DefinicaoBI; mudar: Mudar; soltas: string[] }) {
  const nome = (k: string) => cat.fontes.find((f) => f.chave === k)?.rotulo ?? k;
  const chaves = (k: string) => cat.fontes.find((f) => f.chave === k)?.chaves ?? [];
  const sugeridas = cat.relacoes.filter((r) => d.fontes.includes(r.a) && d.fontes.includes(r.b));
  const mudarManual = (i: number, campo: keyof LigacaoManual, v: string) => mudar((x) => {
    const m = [...x.manuais];
    const atual = { ...m[i], [campo]: v } as LigacaoManual;
    if (campo === "a") atual.ca = chaves(v)[0] ?? "id";
    if (campo === "b") atual.cb = chaves(v)[0] ?? "id";
    m[i] = atual;
    return { ...x, manuais: m };
  });
  return (
    <Passo n={2} titulo="Ligações entre as fontes">
      <p className="-mt-1 mb-3 text-[12.5px] text-suave">
        O sistema sugere as ligações que conhece. Troque o tipo ou crie uma ligação manual pelas colunas de ligação.
      </p>
      <div className="flex flex-col gap-2" id="bi-ligacoes">
        {d.fontes.length < 2 && <p className="text-[13.5px] text-suave">Com uma fonte só não há o que ligar.</p>}
        {sugeridas.map((r) => (
          <div key={r.id} className="flex flex-col gap-2 rounded-xl border border-linha p-3" data-ligacao={r.id}>
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
              <span className="rounded-full bg-superficie2 px-2.5 py-0.5 font-bold">{nome(r.a)}</span>
              <span aria-hidden className="text-suave">→</span>
              <span className="rounded-full bg-superficie2 px-2.5 py-0.5 font-bold">{nome(r.b)}</span>
              <span className="ml-auto rounded-full bg-[#e3ecf7] px-2 py-0.5 text-[11px] font-bold text-[#1f4c80]">sugerida</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded-md bg-superficie2 px-2 py-1 text-[12px]">{r.a}.{r.ca} = {r.b}.{r.cb}</code>
              <label className="sr-only" htmlFor={`tipo-${r.id}`}>Tipo da ligação</label>
              <select id={`tipo-${r.id}`} className="campo ml-auto w-auto py-1.5 text-[13.5px]"
                      value={d.tipos[r.id] ?? "INNER"}
                      onChange={(e) => mudar((x) => ({ ...x, tipos: { ...x.tipos, [r.id]: e.target.value as TipoLigacao } }))}>
                <option value="INNER">Só o que casa</option>
                <option value="LEFT">Manter todos de {nome(r.a)}</option>
                <option value="NENHUMA">Não ligar</option>
              </select>
            </div>
          </div>
        ))}
        {d.manuais.map((m, i) => (
          <div key={i} className="flex flex-col gap-2 rounded-xl border border-dashed border-erva/50 bg-erva-claro/40 p-3" data-manual={i}>
            <div className="flex items-center justify-between">
              <span className="rounded-full bg-erva-claro px-2 py-0.5 text-[11px] font-bold text-erva">ligação manual</span>
              <button type="button" className="btn btn-terciario btn-pequeno"
                      onClick={() => mudar((x) => ({ ...x, manuais: x.manuais.filter((_, j) => j !== i) }))}>Remover</button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <select className="campo py-1.5 text-[13.5px]" aria-label="Fonte de origem" value={m.a} onChange={(e) => mudarManual(i, "a", e.target.value)}>
                {d.fontes.map((k) => <option key={k} value={k}>{nome(k)}</option>)}
              </select>
              <select className="campo py-1.5 text-[13.5px]" aria-label="Coluna de origem" value={m.ca} onChange={(e) => mudarManual(i, "ca", e.target.value)}>
                {chaves(m.a).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select className="campo py-1.5 text-[13.5px]" aria-label="Fonte de destino" value={m.b} onChange={(e) => mudarManual(i, "b", e.target.value)}>
                {d.fontes.map((k) => <option key={k} value={k}>{nome(k)}</option>)}
              </select>
              <select className="campo py-1.5 text-[13.5px]" aria-label="Coluna de destino" value={m.cb} onChange={(e) => mudarManual(i, "cb", e.target.value)}>
                {chaves(m.b).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select className="campo col-span-2 py-1.5 text-[13.5px]" aria-label="Tipo da ligação manual" value={m.tipo}
                      onChange={(e) => mudarManual(i, "tipo", e.target.value)}>
                <option value="INNER">Só o que casa</option>
                <option value="LEFT">Manter todos da origem</option>
              </select>
            </div>
          </div>
        ))}
        {!!soltas.length && (
          <div className="aviso aviso-info" role="status" id="bi-soltas">
            Sem ligação: {soltas.join(", ")}. Crie uma ligação manual ou desmarque a fonte.
          </div>
        )}
        {d.fontes.length >= 2 && (
          <button type="button" id="bi-nova-ligacao" className="btn btn-secundario btn-pequeno self-start"
                  onClick={() => mudar((x) => {
                    const a = x.fontes[0], b = x.fontes[x.fontes.length - 1];
                    return { ...x, manuais: [...x.manuais, { a, ca: chaves(a)[0] ?? "id", b, cb: chaves(b)[0] ?? "id", tipo: "INNER" }] };
                  })}>
            + Nova ligação
          </button>
        )}
      </div>
    </Passo>
  );
}

export function PassoCampos({ cat, d, mudar }: { cat: CatalogoBI; d: DefinicaoBI; mudar: Mudar }) {
  const campos = cat.fontes.filter((f) => d.fontes.includes(f.chave))
    .flatMap((f) => f.campos.map((c) => ({ ...c, fonte: f.rotulo })));
  const dims = campos.filter((c) => c.tipo === "dim");
  const meds = campos.filter((c) => c.tipo === "med");
  const Chip = ({ ligado, onClick, rotulo, extra, id }: { ligado: boolean; onClick: () => void; rotulo: string; extra: string; id: string }) => (
    <button type="button" aria-pressed={ligado} onClick={onClick} data-campo={id}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-semibold transition-colors ${
              ligado ? "border-erva/40 bg-erva-claro text-erva" : "border-linha bg-superficie hover:border-linha2"}`}>
      {rotulo}<span className="text-[11.5px] font-medium text-suave">{extra}</span>
    </button>
  );
  return (
    <Passo n={3} titulo="Campos">
      <p className="rotulo-campo mb-1.5">Agrupar por <span className="rotulo-opcional">até duas dimensões</span></p>
      <div className="mb-4 flex flex-wrap gap-1.5" id="bi-dimensoes">
        {!dims.length && <span className="text-[13px] text-suave">Escolha uma fonte com dimensões.</span>}
        {dims.map((c) => {
          const on = d.dimensoes.includes(c.chave);
          return <Chip key={c.chave} id={c.chave} ligado={on} rotulo={c.rotulo} extra={c.fonte}
                       onClick={() => mudar((x) => ({
                         ...x, dimensoes: on ? x.dimensoes.filter((k) => k !== c.chave) : [...x.dimensoes, c.chave].slice(-2),
                       }))} />;
        })}
      </div>
      <p className="rotulo-campo mb-1.5">Medidas</p>
      <div className="flex flex-wrap gap-1.5" id="bi-medidas">
        {!meds.length && <span className="text-[13px] text-suave">Escolha uma fonte com medidas (Vendas, Itens da venda, Notas…).</span>}
        {meds.map((c) => {
          const on = d.medidas.includes(c.chave);
          return <Chip key={c.chave} id={c.chave} ligado={on} rotulo={c.rotulo} extra={c.fonte}
                       onClick={() => mudar((x) => ({
                         ...x, medidas: on ? x.medidas.filter((k) => k !== c.chave) : [...x.medidas, c.chave].slice(0, 6),
                       }))} />;
        })}
      </div>
    </Passo>
  );
}

export function PassoPeriodo({ d, mudar }: { d: DefinicaoBI; mudar: Mudar }) {
  return (
    <Passo n={4} titulo="Período">
      <div className="flex flex-wrap items-end gap-3">
        <label><span className="rotulo-campo">De</span>
          <input id="bi-de" type="date" className="campo mt-1.5 w-auto" value={d.de ?? ""}
                 onChange={(e) => mudar((x) => ({ ...x, de: e.target.value || null }))} /></label>
        <label><span className="rotulo-campo">Até</span>
          <input id="bi-ate" type="date" className="campo mt-1.5 w-auto" value={d.ate ?? ""}
                 onChange={(e) => mudar((x) => ({ ...x, ate: e.target.value || null }))} /></label>
      </div>
      <p className="mt-2 text-[12.5px] text-suave">
        Vale para as fontes que têm data (vendas, reservas, notas, movimentos). Sempre na loja escolhida no topo.
      </p>
    </Passo>
  );
}

/** As barras: UMA medida (a primeira), um eixo só — misturar R$ e quantidade no mesmo eixo engana. */
export function Barras({ res }: { res: ResultadoBI }) {
  const dims = res.colunas.filter((c) => c.tipo === "dim");
  const iMed = res.colunas.findIndex((c) => c.tipo === "med");
  if (iMed < 0 || !dims.length) return <p className="py-6 text-center text-[14px] text-suave">As barras pedem uma dimensão.</p>;
  const med: ColunaBI = res.colunas[iMed];
  const linhas = res.linhas.slice(0, 30);
  const max = Math.max(...linhas.map((l) => Math.abs(Number(l[iMed]) || 0)), 1);
  return (
    <div role="img" aria-label={`${med.rotulo} por ${dims.map((x) => x.rotulo.toLowerCase()).join(" e ")}`}
         className="flex flex-col gap-2" id="bi-barras">
      {linhas.map((l, i) => {
        const rotulo = dims.map((_, j) => formatar(l[j], dims[j].formato)).join(" · ");
        const v = Number(l[iMed]) || 0;
        return (
          <div key={i} className="grid grid-cols-[minmax(110px,190px)_minmax(0,1fr)_minmax(80px,auto)] items-center gap-3"
               title={`${rotulo}: ${formatar(l[iMed], med.formato)}`}>
            <span className="truncate text-[13px] font-semibold">{rotulo}</span>
            <div className="rounded bg-superficie2"><div className="h-[22px] rounded bg-erva" style={{ width: `${Math.max(1, (Math.abs(v) / max) * 100)}%` }} /></div>
            <span className="mono text-right text-[13px]">{formatar(l[iMed], med.formato)}</span>
          </div>
        );
      })}
      {res.linhas.length > 30 && <p className="text-[12.5px] text-suave">As 30 primeiras; a tabela mostra todas.</p>}
    </div>
  );
}

export function Tabela({ res }: { res: ResultadoBI }) {
  return (
    <div className="grid-rolante">
      <table className="tabela tabela-compacta" id="bi-tabela">
        <thead><tr>{res.colunas.map((c) => <th key={c.chave} className={c.tipo === "med" ? "num" : undefined}>{c.rotulo}</th>)}</tr></thead>
        <tbody>
          {res.linhas.map((l, i) => (
            <tr key={i}>{l.map((v, j) => (
              <td key={j} className={res.colunas[j].tipo === "med" ? "num mono" : undefined}>{formatar(v, res.colunas[j].formato)}</td>
            ))}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Indicadores({ res }: { res: ResultadoBI }) {
  const linha = res.linhas[0] ?? [];
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3" id="bi-indicadores">
      {res.colunas.map((c, i) => c.tipo === "med" && (
        <div key={c.chave} className="rounded-2xl border border-linha p-4">
          <p className="text-[13px] font-semibold text-suave">{c.rotulo}</p>
          <p className="mono mt-1.5 text-[26px] font-extrabold tracking-[-0.02em]">{formatar(linha[i] ?? null, c.formato)}</p>
        </div>
      ))}
    </div>
  );
}

type Papel = { id: number; nome: string };

export function JanelaSalvar({ nome, setNome, visibilidade, setVisibilidade, papeis, setPapeis, noMenu, setNoMenu,
  aoFechar, aoSalvar, salvando }: {
  nome: string; setNome: (v: string) => void;
  visibilidade: Visibilidade; setVisibilidade: (v: Visibilidade) => void;
  papeis: number[]; setPapeis: (v: number[]) => void;
  noMenu: boolean; setNoMenu: (v: boolean) => void;
  aoFechar: () => void; aoSalvar: () => void; salvando: boolean;
}) {
  const [todos, setTodos] = useState<Papel[]>([]);
  useEffect(() => { api.get<Papel[]>("/papeis").then(setTodos).catch(() => setTodos([])); }, []);
  const opcoes: { v: Visibilidade; r: string; d: string }[] = [
    { v: "EU", r: "Só eu", d: "Fica nos seus relatórios, para você." },
    { v: "TODOS", r: "Todos com acesso a relatórios personalizados", d: "Quem tem a permissão “Ver os relatórios personalizados”." },
    { v: "PAPEIS", r: "Papéis escolhidos", d: "Só quem está num dos papéis marcados abaixo." },
  ];
  return (
    <Modal titulo="Salvar e publicar" descricao="O relatório fica disponível para quem você escolher." aoFechar={aoFechar} largura="560px"
           rodape={
             <div className="flex justify-end gap-2">
               <button type="button" className="btn btn-secundario" onClick={aoFechar}>Cancelar</button>
               <button type="button" id="bi-confirmar-salvar" className="btn btn-primario" onClick={aoSalvar}
                       disabled={salvando || !nome.trim() || (visibilidade === "PAPEIS" && !papeis.length)} aria-busy={salvando}>
                 {salvando ? "Salvando…" : "Salvar e publicar"}
               </button>
             </div>
           }>
      <div className="flex flex-col gap-5">
        <label className="block"><span className="rotulo-campo">Nome</span>
          <input id="bi-nome-salvar" className="campo mt-1.5" maxLength={120} value={nome} onChange={(e) => setNome(e.target.value)} /></label>
        <fieldset>
          <legend className="rotulo-campo mb-2">Quem pode ver</legend>
          <div className="flex flex-col gap-2">
            {opcoes.map((o) => (
              <label key={o.v} className="flex cursor-pointer items-start gap-2.5">
                <input type="radio" name="visibilidade" className="mt-1 h-4 w-4 accent-erva" checked={visibilidade === o.v}
                       onChange={() => setVisibilidade(o.v)} value={o.v} />
                <span><span className="block text-[14px] font-semibold">{o.r}</span><span className="block text-[12.5px] text-suave">{o.d}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
        {visibilidade === "PAPEIS" && (
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {!todos.length && <p className="text-[13px] text-suave">Sem acesso à lista de papéis.</p>}
            {todos.map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-[14px]">
                <input type="checkbox" className="h-4 w-4 accent-erva" checked={papeis.includes(p.id)}
                       onChange={() => setPapeis(papeis.includes(p.id) ? papeis.filter((x) => x !== p.id) : [...papeis, p.id])} />
                {p.nome}
              </label>
            ))}
          </div>
        )}
        <label className="flex items-center gap-2.5 text-[14px]">
          <input type="checkbox" className="h-4 w-4 accent-erva" checked={noMenu} onChange={(e) => setNoMenu(e.target.checked)} />
          Aparece em Relatórios ▸ Personalizados
        </label>
      </div>
    </Modal>
  );
}
