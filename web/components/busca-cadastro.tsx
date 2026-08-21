"use client";

import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { FonteBusca, ItemBusca } from "@/lib/busca-cadastro";
import { Carregando, Modal, Vazio } from "@/components/ui";

/**
 * O campo de busca de cadastro — o padrão do sistema onde havia combobox.
 *
 * Combobox serve até umas dezenas de linhas. Com dois mil insumos vira um rolo
 * impossível, e quem sabe o código do produto tem de procurá-lo com o olho
 * numa lista alfabética.
 *
 * Aqui se digita código ou nome e se dá **Tab**:
 *
 * * um só resultado  → preenche e segue, sem tirar a mão do teclado;
 * * mais de um       → abre a janela de pesquisa JÁ FILTRADA pelo que foi
 *                      digitado, que é o gesto que a pessoa faria em seguida;
 * * nenhum           → abre a janela também, para corrigir o termo ali mesmo,
 *                      em vez de devolver um "não encontrado" e deixar o campo
 *                      com o texto errado.
 *
 * A lupa ao lado abre a janela direto, para quem não sabe o que procura.
 */

const POR_PAGINA = 25;

export default function BuscaCadastro({
  fonte,
  selecionado,
  aoEscolher,
  disabled = false,
  required = false,
  autoFocus = false,
  className = "",
  id,
}: {
  fonte: FonteBusca;
  selecionado: { id: number; rotulo: string } | null;
  aoEscolher: (item: ItemBusca | null) => void;
  disabled?: boolean;
  required?: boolean;
  autoFocus?: boolean;
  className?: string;
  id?: string;
}) {
  const [texto, setTexto] = useState(selecionado?.rotulo ?? "");
  const [aberto, setAberto] = useState(false);
  const [resolvendo, setResolvendo] = useState(false);
  const campo = useRef<HTMLInputElement>(null);
  // Tab dispara blur e o blur também resolve: sem esta trava a busca sairia
  // duas vezes e a janela abriria por cima de si mesma.
  const resolvendoRef = useRef(false);

  // Quem manda no texto é a escolha: trocar o item por fora (carregar uma nota
  // para corrigir, por exemplo) tem de aparecer no campo.
  useEffect(() => {
    setTexto(selecionado?.rotulo ?? "");
  }, [selecionado?.id, selecionado?.rotulo]);

  const resolver = useCallback(async () => {
    if (disabled || resolvendoRef.current) return;
    const termo = texto.trim();
    if (termo === (selecionado?.rotulo ?? "").trim()) return;   // nada mudou
    if (!termo) {
      aoEscolher(null);
      return;
    }
    resolvendoRef.current = true;
    setResolvendo(true);
    try {
      const { itens } = await fonte.buscar(termo, POR_PAGINA);
      if (itens.length === 1) {
        aoEscolher(itens[0]);
      } else {
        setAberto(true);
      }
    } catch {
      setAberto(true);
    } finally {
      setResolvendo(false);
      resolvendoRef.current = false;
    }
  }, [texto, selecionado?.rotulo, disabled, fonte, aoEscolher]);

  function aoTeclar(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      // Enter num campo de busca não pode enviar o formulário: a pessoa está
      // resolvendo o item, não terminando o lançamento.
      e.preventDefault();
      void resolver();
    }
  }

  function escolher(item: ItemBusca | null) {
    aoEscolher(item);
    setAberto(false);
    setTexto(item ? rotuloDe(item) : "");
    // Devolve o foco: quem escolheu na janela continua a preencher no teclado.
    requestAnimationFrame(() => campo.current?.focus());
  }

  return (
    <>
      <div className={`flex gap-1.5 ${className}`}>
        <input
          id={id}
          ref={campo}
          className="campo"
          autoFocus={autoFocus}
          disabled={disabled}
          required={required && !selecionado}
          placeholder={fonte.placeholder}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onBlur={() => void resolver()}
          onKeyDown={aoTeclar}
          aria-label={fonte.titulo}
        />
        <button
          type="button"
          className="btn btn-secundario shrink-0 px-2.5"
          disabled={disabled}
          onClick={() => setAberto(true)}
          aria-label={fonte.titulo}
          title={fonte.titulo}
        >
          {resolvendo ? "…" : <Lupa />}
        </button>
      </div>

      {aberto && (
        <Janela
          fonte={fonte}
          termoInicial={texto}
          aoFechar={() => {
            setAberto(false);
            // Fechar sem escolher devolve o campo ao que ele mostrava: deixar
            // um texto solto que não corresponde a registro nenhum faria a
            // pessoa achar que escolheu.
            setTexto(selecionado?.rotulo ?? "");
            requestAnimationFrame(() => campo.current?.focus());
          }}
          aoEscolher={escolher}
        />
      )}
    </>
  );
}

export function rotuloDe(item: ItemBusca): string {
  return item.codigo ? `${item.codigo} · ${item.nome}` : item.nome;
}

function Lupa() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden fill="none">
      <circle cx="7" cy="7" r="4.6" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10.6 10.6 L14 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function Janela({
  fonte,
  termoInicial,
  aoFechar,
  aoEscolher,
}: {
  fonte: FonteBusca;
  termoInicial: string;
  aoFechar: () => void;
  aoEscolher: (item: ItemBusca) => void;
}) {
  const [termo, setTermo] = useState(termoInicial);
  const [itens, setItens] = useState<ItemBusca[] | null>(null);
  const [total, setTotal] = useState(0);
  const [pagina, setPagina] = useState(1);
  const [erro, setErro] = useState("");
  const [marcado, setMarcado] = useState(0);

  useEffect(() => {
    let vivo = true;
    const t = setTimeout(async () => {
      try {
        const r = await fonte.buscar(termo, POR_PAGINA * pagina);
        if (!vivo) return;
        setItens(r.itens);
        setTotal(r.total);
        setMarcado(0);
        setErro("");
      } catch (e) {
        if (vivo) setErro(e instanceof Error ? e.message : "Falha na busca");
      }
    }, itens === null ? 0 : 250);
    return () => {
      vivo = false;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [termo, pagina, fonte]);

  function aoTeclar(e: KeyboardEvent<HTMLInputElement>) {
    if (!itens?.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setMarcado((n) => Math.min(n + 1, itens.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setMarcado((n) => Math.max(n - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      aoEscolher(itens[marcado]);
    }
  }

  return (
    <Modal
      titulo={fonte.titulo}
      descricao="Digite parte do código ou do nome. ↑ ↓ para andar, Enter para escolher."
      aoFechar={aoFechar}
    >
      <input
        className="campo"
        autoFocus
        placeholder={fonte.placeholder}
        value={termo}
        onChange={(e) => {
          setTermo(e.target.value);
          setPagina(1);
        }}
        onKeyDown={aoTeclar}
      />

      {erro && <p className="mt-3 border-l-2 border-erro py-1 pl-3 text-[14px] text-erro">{erro}</p>}

      <div className="mt-4 max-h-[46vh] overflow-y-auto">
        {!itens ? (
          <Carregando />
        ) : !itens.length ? (
          <Vazio>
            Nenhum {fonte.singular} com “{termo}”.
          </Vazio>
        ) : (
          <ul className="divide-y divide-linha">
            {itens.map((i, n) => (
              <li key={i.id}>
                <button
                  type="button"
                  className={`flex w-full items-baseline gap-3 px-2 py-2.5 text-left ${
                    n === marcado ? "bg-erva-claro" : "hover:bg-superficie2"
                  }`}
                  onMouseEnter={() => setMarcado(n)}
                  onClick={() => aoEscolher(i)}
                >
                  {i.codigo && (
                    <span className="mono shrink-0 text-[12.5px] text-suave">{i.codigo}</span>
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14.5px]">{i.nome}</span>
                    {i.detalhe && (
                      <span className="block text-[12.5px] text-suave">{i.detalhe}</span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {!!itens && itens.length < total && (
        <div className="mt-3 flex items-center justify-center gap-3">
          <button
            type="button"
            className="btn btn-secundario"
            onClick={() => setPagina((n) => n + 1)}
          >
            Mostrar mais
          </button>
          <span className="text-[13px] text-suave">
            {itens.length} de {total}
          </span>
        </div>
      )}
    </Modal>
  );
}

/**
 * A mesma busca, agora como FILTRO de lista.
 *
 * Filtrar é diferente de escolher: "café" tem de trazer os cinco cafés, senão
 * quem está conferindo o estoque perde a visão do grupo. Mas quem quer o razão
 * de UM produto não quer conferir os outros quatro.
 *
 * Por isso os dois convivem: o texto filtra solto, e a lupa **fixa** um
 * registro — que aparece como etiqueta, para ninguém achar que a lista está
 * curta por acaso.
 */
export function FiltroCadastro({
  fonte,
  texto,
  aoMudarTexto,
  fixado,
  aoFixar,
  placeholder,
  className = "",
}: {
  fonte: FonteBusca;
  texto: string;
  aoMudarTexto: (t: string) => void;
  fixado: { id: number; rotulo: string } | null;
  aoFixar: (item: { id: number; rotulo: string } | null) => void;
  placeholder?: string;
  className?: string;
}) {
  const [aberto, setAberto] = useState(false);

  if (fixado) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <span className="flex min-w-0 items-center gap-2 rounded border border-erva bg-erva-claro px-2.5 py-[7px]">
          <span className="truncate text-[14px] text-erva">{fixado.rotulo}</span>
          <button
            type="button"
            aria-label="tirar o filtro de produto"
            className="text-[16px] leading-none text-erva hover:text-tinta"
            onClick={() => aoFixar(null)}
          >
            ×
          </button>
        </span>
      </div>
    );
  }

  return (
    <>
      <div className={`flex gap-1.5 ${className}`}>
        <input
          className="campo"
          placeholder={placeholder ?? fonte.placeholder}
          value={texto}
          onChange={(e) => aoMudarTexto(e.target.value)}
          aria-label={fonte.titulo}
        />
        <button
          type="button"
          className="btn btn-secundario shrink-0 px-2.5"
          onClick={() => setAberto(true)}
          aria-label={fonte.titulo}
          title={fonte.titulo}
        >
          <Lupa />
        </button>
      </div>

      {aberto && (
        <Janela
          fonte={fonte}
          termoInicial={texto}
          aoFechar={() => setAberto(false)}
          aoEscolher={(item) => {
            aoFixar({ id: item.id, rotulo: rotuloDe(item) });
            aoMudarTexto("");
            setAberto(false);
          }}
        />
      )}
    </>
  );
}
