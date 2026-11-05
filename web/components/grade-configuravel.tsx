"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { gravarPreferencia, lerPreferencia } from "@/lib/preferencias";

/**
 * 🔑 **O grid configurável** (layout novo, fase 2 — 05/11/2026, pedido do dono: *"grids
 * configuráveis e que proporcionem uma ótima visualização"*; protótipo em
 * `apresentacao/novo-layout/`).
 *
 * Cada pessoa escolhe, por tela: quais colunas aparecem, a ordem delas, a densidade das linhas
 * e as VISÕES salvas (colunas + filtros da URL, com nome). Tudo vai para o servidor
 * (`preferencias_usuario`, migração 148), então vale em qualquer aparelho.
 *
 * Uso:
 *     const g = useGrade("produtos", COLUNAS);
 *     <BarraDaGrade g={g} />                 // visões, densidade e o botão Colunas
 *     g.visiveis.map((c) => <th>{c.rotulo}</th>)
 *     <table className={`tabela ${g.compacta ? "tabela-compacta" : ""}`}>
 *
 * ⚠️ **A coluna `fixa` não se esconde** (o nome do registro: sem ele a linha não diz de quem é).
 * ⚠️ **Coluna nova no código aparece sozinha**: a ordem guardada é mesclada com a lista atual —
 * chave que sumiu do código é descartada, e a que nasceu entra na posição padrão dela.
 * ⚠️ A visão guarda a URL SEM a paginação (`p`, `pp`): abrir uma visão volta para a página 1.
 */

export type ColunaGrade = {
  chave: string;
  rotulo: string;
  /** Visível quando a pessoa ainda não escolheu nada. Padrão: sim. */
  padrao?: boolean;
  /** Não pode ser escondida nem sair do lugar. */
  fixa?: boolean;
};

export type VisaoGrade = { nome: string; busca: string; ordem: string[]; ocultas: string[]; compacta: boolean };
type Config = { ordem: string[]; ocultas: string[]; compacta: boolean; visoes: VisaoGrade[] };

const SEM_PAGINA = ["p", "pp"];
const limparBusca = (q: string) => {
  const u = new URLSearchParams(q);
  SEM_PAGINA.forEach((k) => u.delete(k));
  u.sort();
  return u.toString();
};

function padraoDe(colunas: ColunaGrade[]): Config {
  return {
    ordem: colunas.map((c) => c.chave),
    ocultas: colunas.filter((c) => c.padrao === false).map((c) => c.chave),
    compacta: false,
    visoes: [],
  };
}

/** A ordem guardada, sem o que sumiu do código e com o que nasceu na posição padrão. */
function mesclarOrdem(guardada: string[], colunas: ColunaGrade[]): string[] {
  const existentes = new Set(colunas.map((c) => c.chave));
  const ordem = guardada.filter((k) => existentes.has(k));
  colunas.forEach((c, i) => {
    if (ordem.includes(c.chave)) return;
    const antes = colunas.slice(0, i).map((x) => x.chave).reverse().find((k) => ordem.includes(k));
    ordem.splice(antes ? ordem.indexOf(antes) + 1 : 0, 0, c.chave);
  });
  return ordem;
}

export function useGrade(nome: string, colunas: ColunaGrade[]) {
  const chave = `grade:${nome}`;
  const router = useRouter();
  const caminho = usePathname();
  const params = useSearchParams();
  const [cfg, setCfg] = useState<Config>(() => padraoDe(colunas));
  const [carregado, setCarregado] = useState(false);
  const salvar = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let vivo = true;
    lerPreferencia<Partial<Config>>(chave)
      .then((v) => {
        if (!vivo || !v) return;
        const base = padraoDe(colunas);
        setCfg({
          ordem: mesclarOrdem(Array.isArray(v.ordem) ? v.ordem : base.ordem, colunas),
          ocultas: Array.isArray(v.ocultas) ? v.ocultas : base.ocultas,
          compacta: !!v.compacta,
          visoes: Array.isArray(v.visoes) ? v.visoes : [],
        });
      })
      // Sem preferência (ou sem servidor), fica o padrão: o grid funciona do mesmo jeito.
      .catch(() => {})
      .finally(() => vivo && setCarregado(true));
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave]);

  const mudar = useCallback((f: (c: Config) => Config) => {
    setCfg((atual) => {
      const novo = f(atual);
      if (salvar.current) clearTimeout(salvar.current);
      // Espera a pessoa parar de clicar: subir e descer uma coluna cinco vezes é uma gravação só.
      salvar.current = setTimeout(() => { void gravarPreferencia(chave, novo).catch(() => {}); }, 500);
      return novo;
    });
  }, [chave]);

  const porChave = useMemo(() => new Map(colunas.map((c) => [c.chave, c])), [colunas]);
  const ordenadas = cfg.ordem.map((k) => porChave.get(k)).filter((c): c is ColunaGrade => !!c);
  const visiveis = ordenadas.filter((c) => c.fixa || !cfg.ocultas.includes(c.chave));
  const buscaAtual = limparBusca(params.toString());
  const visaoAtual = cfg.visoes.find((v) => v.busca === buscaAtual
    && JSON.stringify(v.ordem) === JSON.stringify(cfg.ordem)
    && JSON.stringify([...v.ocultas].sort()) === JSON.stringify([...cfg.ocultas].sort())
    && v.compacta === cfg.compacta)?.nome ?? null;

  return {
    carregado,
    colunas: ordenadas,
    visiveis,
    mostra: (k: string) => visiveis.some((c) => c.chave === k),
    oculta: (k: string) => cfg.ocultas.includes(k),
    compacta: cfg.compacta,
    visoes: cfg.visoes,
    visaoAtual,
    /** A pessoa mexeu nas colunas (escolha ou ordem). Sem isso, a tela pode esconder coluna vazia. */
    personalizado: JSON.stringify(cfg.ordem) !== JSON.stringify(padraoDe(colunas).ordem)
      || JSON.stringify([...cfg.ocultas].sort()) !== JSON.stringify([...padraoDe(colunas).ocultas].sort()),
    /** Nenhum filtro na URL e as colunas do jeito de fábrica. */
    noPadrao: !buscaAtual && JSON.stringify(cfg.ordem) === JSON.stringify(padraoDe(colunas).ordem)
      && JSON.stringify([...cfg.ocultas].sort()) === JSON.stringify([...padraoDe(colunas).ocultas].sort()),
    alternar: (k: string) => mudar((c) => ({
      ...c, ocultas: c.ocultas.includes(k) ? c.ocultas.filter((x) => x !== k) : [...c.ocultas, k],
    })),
    mover: (k: string, passo: -1 | 1) => mudar((c) => {
      const o = [...c.ordem];
      const i = o.indexOf(k);
      let j = i + passo;
      // Pula as fixas: elas não saem do lugar, nem empurradas pelas vizinhas.
      while (j >= 0 && j < o.length && porChave.get(o[j])?.fixa) j += passo;
      if (i < 0 || j < 0 || j >= o.length || porChave.get(k)?.fixa) return c;
      [o[i], o[j]] = [o[j], o[i]];
      return { ...c, ordem: o };
    }),
    restaurar: () => mudar((c) => ({ ...padraoDe(colunas), visoes: c.visoes })),
    setCompacta: (v: boolean) => mudar((c) => ({ ...c, compacta: v })),
    salvarVisao: (nomeVisao: string) => mudar((c) => ({
      ...c,
      visoes: [...c.visoes.filter((v) => v.nome !== nomeVisao),
        { nome: nomeVisao, busca: buscaAtual, ordem: c.ordem, ocultas: c.ocultas, compacta: c.compacta }],
    })),
    removerVisao: (nomeVisao: string) => mudar((c) => ({ ...c, visoes: c.visoes.filter((v) => v.nome !== nomeVisao) })),
    abrirVisao: (v: VisaoGrade) => {
      mudar((c) => ({ ...c, ordem: mesclarOrdem(v.ordem, colunas), ocultas: v.ocultas, compacta: v.compacta }));
      router.replace(v.busca ? `${caminho}?${v.busca}` : caminho, { scroll: false });
    },
    abrirPadrao: () => {
      mudar((c) => ({ ...padraoDe(colunas), visoes: c.visoes }));
      router.replace(caminho, { scroll: false });
    },
  };
}

export type Grade = ReturnType<typeof useGrade>;

/** Fecha um painel suspenso com clique fora ou Escape. */
function useFechar(aberto: boolean, fechar: () => void) {
  const caixa = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (caixa.current && !caixa.current.contains(e.target as Node)) fechar();
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && fechar();
    document.addEventListener("mousedown", fora);
    window.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      window.removeEventListener("keydown", esc);
    };
  }, [aberto, fechar]);
  return caixa;
}

const Seta = ({ para }: { para: "cima" | "baixo" }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
       strokeLinecap="round" aria-hidden><path d={para === "cima" ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} /></svg>
);

/** O botão "Colunas" e o painel de escolher e ordenar. */
export function BotaoColunas({ g }: { g: Grade }) {
  const [aberto, setAberto] = useState(false);
  const fechar = useCallback(() => setAberto(false), []);
  const caixa = useFechar(aberto, fechar);
  return (
    <div className="relative" ref={caixa}>
      <button type="button" id="grade-colunas" className="btn btn-secundario btn-pequeno"
              aria-expanded={aberto} aria-haspopup="dialog" onClick={() => setAberto((a) => !a)}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" aria-hidden><path d="M4 4h6v16H4z M14 4h6v16h-6z" /></svg>
        Colunas <span className="contador-grade mono">{g.visiveis.length}</span>
      </button>
      {aberto && (
        <div role="dialog" aria-label="Colunas do grid" id="painel-colunas"
             className="cartao absolute right-0 z-30 mt-2 w-[300px] p-3.5 shadow-[0_12px_32px_rgba(20,30,25,.14)]">
          <div className="mb-1 flex items-center justify-between">
            <b className="text-[14px]">Colunas do grid</b>
            <button type="button" className="btn btn-terciario btn-pequeno" onClick={g.restaurar}>Restaurar</button>
          </div>
          <p className="mb-2.5 text-[12.5px] text-suave">Marque o que aparece e use as setas para mudar a ordem.</p>
          <ul className="flex flex-col">
            {g.colunas.map((c, i) => (
              <li key={c.chave} className="flex items-center gap-2.5 rounded-lg px-1 py-1" data-coluna={c.chave}>
                <input type="checkbox" id={`col-${c.chave}`} className="h-4 w-4 accent-erva"
                       checked={!g.oculta(c.chave) || !!c.fixa} disabled={c.fixa}
                       onChange={() => g.alternar(c.chave)} />
                <label htmlFor={`col-${c.chave}`} className="flex-1 cursor-pointer text-[13.5px]">
                  {c.rotulo}{c.fixa && <span className="ml-1.5 text-[12px] text-suave">sempre</span>}
                </label>
                {!c.fixa && (
                  <>
                    <button type="button" className="seta-coluna" aria-label={`Subir ${c.rotulo}`}
                            disabled={i === 0} onClick={() => g.mover(c.chave, -1)}><Seta para="cima" /></button>
                    <button type="button" className="seta-coluna" aria-label={`Descer ${c.rotulo}`}
                            disabled={i === g.colunas.length - 1} onClick={() => g.mover(c.chave, 1)}><Seta para="baixo" /></button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Confortável × compacta. */
export function DensidadeGrade({ g }: { g: Grade }) {
  return (
    <div className="seg-grade" role="group" aria-label="Densidade das linhas">
      <button type="button" aria-pressed={!g.compacta} onClick={() => g.setCompacta(false)}>Confortável</button>
      <button type="button" aria-pressed={g.compacta} onClick={() => g.setCompacta(true)}>Compacta</button>
    </div>
  );
}

/**
 * As visões salvas: "Padrão", as da pessoa e "Salvar esta visão".
 * ⚠️ O nome se digita num campo da própria barra — `window.prompt` é a caixa do navegador,
 * banida da casa (ver padroes-de-ui.md).
 */
export function VisoesDaGrade({ g }: { g: Grade }) {
  const [nomeando, setNomeando] = useState(false);
  const [nome, setNome] = useState("");
  const confirmar = () => {
    const n = nome.trim();
    if (!n) return;
    g.salvarVisao(n.slice(0, 40));
    setNome("");
    setNomeando(false);
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Visões salvas" id="visoes-grade">
      <button type="button" className="visao-grade" aria-pressed={g.noPadrao} onClick={g.abrirPadrao}>Padrão</button>
      {g.visoes.map((v) => (
        <span key={v.nome} className="visao-grade-item" data-visao={v.nome}>
          <button type="button" className="visao-grade" aria-pressed={g.visaoAtual === v.nome}
                  onClick={() => g.abrirVisao(v)}>{v.nome}</button>
          <button type="button" className="visao-grade-x" aria-label={`Apagar a visão ${v.nome}`}
                  onClick={() => g.removerVisao(v.nome)}>×</button>
        </span>
      ))}
      {nomeando ? (
        <form className="flex items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); confirmar(); }}>
          <label htmlFor="nome-visao" className="sr-only">Nome da visão</label>
          <input id="nome-visao" className="campo h-9 w-[180px] py-1 text-[14px]" autoFocus maxLength={40}
                 placeholder="Nome da visão" value={nome} onChange={(e) => setNome(e.target.value)}
                 onKeyDown={(e) => e.key === "Escape" && setNomeando(false)} />
          <button type="submit" className="btn btn-primario btn-pequeno" disabled={!nome.trim()}>Salvar</button>
          <button type="button" className="btn btn-terciario btn-pequeno" onClick={() => setNomeando(false)}>Cancelar</button>
        </form>
      ) : (
        <button type="button" id="salvar-visao" className="visao-grade text-erva" onClick={() => setNomeando(true)}>
          + Salvar esta visão
        </button>
      )}
    </div>
  );
}

/** O cabeçalho que ordena: clique alterna crescente/decrescente. */
export function CabecalhoOrdenavel({ rotulo, ativo, direcao, aoOrdenar, num }: {
  rotulo: string; ativo: boolean; direcao: "asc" | "desc"; aoOrdenar: () => void; num?: boolean;
}) {
  return (
    <th className={num ? "num" : undefined} aria-sort={ativo ? (direcao === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className="ordenar-coluna" onClick={aoOrdenar}>
        {rotulo}
        <span aria-hidden className="text-erva">{ativo ? (direcao === "asc" ? "↑" : "↓") : ""}</span>
      </button>
    </th>
  );
}
