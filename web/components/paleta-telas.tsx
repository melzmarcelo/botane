"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as EventoTecla } from "react";
import { useRouter } from "next/navigation";

import Icone from "@/components/icone";
import { haJanelaAberta } from "@/components/ui";
import { EVENTO_BUSCA } from "@/lib/eventos";
import { telasDisponiveis } from "@/lib/menu";
import { useSessao } from "@/lib/sessao";

/**
 * A busca de telas — `Ctrl+K`, digita, Enter, chegou.
 *
 * 🔑 **É a resposta para vinte e cinco destinos** (15/09/2026, pedido do dono:
 * *"gostaria de um menu mais moderno"*). O menu tem seis grupos e todos nascem
 * recolhidos — decisão registrada em `layout.tsx` e que continua certa —, e o
 * preço dela é dois cliques por navegação. Esta janela não desfaz a regra: ela
 * a torna irrelevante, porque quem sabe para onde vai deixa de navegar pela
 * árvore. Para quem abre o sistema todo dia, é a diferença entre caçar e chegar.
 *
 * ⚠️ **Varre a MESMA lista do menu** (`lib/menu.ts`), com o mesmo filtro de
 * permissão. Busca que oferece uma tela que a pessoa não pode abrir é um 403
 * com convite; busca que não conhece uma tela nova é uma busca em que não se
 * confia — e as duas coisas acontecem no dia em que as listas são duas.
 *
 * ⚠️ **Não abre por cima de uma janela.** Com a janela de vincular produto
 * aberta, um `Ctrl+K` distraído navegaria para outra tela e levaria junto o
 * trabalho de dentro dela.
 */

/** "inventário" e "inventario" encontram a mesma tela — ninguém digita acento aqui. */
const semAcento = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

/**
 * O trecho encontrado, em destaque.
 *
 * ⚠️ Os índices são os do texto ORIGINAL, e isso vale porque tirar os sinais da
 * forma NFD não muda o tamanho da string: "é" vira "e", "ç" vira "c".
 */
function Realce({ texto, termo }: { texto: string; termo: string }) {
  const t = semAcento(termo.trim());
  const onde = t ? semAcento(texto).indexOf(t) : -1;
  if (onde < 0) return <>{texto}</>;
  return (
    <>
      {texto.slice(0, onde)}
      <mark className="paleta-realce">
        {texto.slice(onde, onde + t.length)}
      </mark>
      {texto.slice(onde + t.length)}
    </>
  );
}

export default function PaletaTelas() {
  const router = useRouter();
  const { eu, pode } = useSessao();
  const [aberta, setAberta] = useState(false);
  const [termo, setTermo] = useState("");
  const [escolhido, setEscolhido] = useState(0);
  const campo = useRef<HTMLInputElement>(null);
  const lista = useRef<HTMLUListElement>(null);
  /** Quem estava com o foco antes — para devolvê-lo ao fechar. */
  const antes = useRef<HTMLElement | null>(null);

  const telas = useMemo(
    () =>
      telasDisponiveis({
        pode,
        enviaAoPdv: !!eu?.enviar_ao_pdv,
        variasLojas: (eu?.unidades.length ?? 0) > 1,
        temReservas: !!eu?.reservas_ligado,
      }),
    [pode, eu],
  );

  const achados = useMemo(() => {
    const t = semAcento(termo.trim());
    if (!t) return telas;
    return telas.filter((i) => semAcento(i.nome).includes(t) || semAcento(i.grupo).includes(t));
  }, [telas, termo]);

  const abrir = useCallback(() => {
    if (haJanelaAberta()) return;
    antes.current = document.activeElement as HTMLElement | null;
    setTermo("");
    setEscolhido(0);
    setAberta(true);
  }, []);

  const fechar = useCallback(() => {
    setAberta(false);
    antes.current?.focus?.();
  }, []);

  // O atalho do teclado e o botão do menu chegam pelos dois caminhos.
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAberta((estava) => {
          if (estava) return estava;
          if (haJanelaAberta()) return false;
          antes.current = document.activeElement as HTMLElement | null;
          setTermo("");
          setEscolhido(0);
          return true;
        });
      }
    };
    window.addEventListener("keydown", tecla);
    window.addEventListener(EVENTO_BUSCA, abrir);
    return () => {
      window.removeEventListener("keydown", tecla);
      window.removeEventListener(EVENTO_BUSCA, abrir);
    };
  }, [abrir]);

  // A página atrás não rola enquanto a busca está aberta — é a mesma regra da
  // `Modal`, e por isso a mesma implementação.
  useEffect(() => {
    if (!aberta) return;
    const antesDisso = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    campo.current?.focus();
    return () => {
      document.body.style.overflow = antesDisso;
    };
  }, [aberta]);

  // ⚠️ A opção marcada tem de estar À VISTA: com vinte e cinco telas, descer de
  // seta até a última rolava o pensamento e não a lista.
  useEffect(() => {
    lista.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [escolhido, termo]);

  if (!aberta) return null;

  const ir = (href: string) => {
    setAberta(false);
    router.push(href);
  };

  const noTeclado = (e: EventoTecla<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!achados.length) return;
      setEscolhido((n) => (n + (e.key === "ArrowDown" ? 1 : achados.length - 1)) % achados.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const alvo = achados[escolhido];
      if (alvo) ir(alvo.href);
    } else if (e.key === "Escape") {
      e.preventDefault();
      // ⚠️ `stopPropagation` para o Escape não atravessar até a `Modal` de trás
      // — embora a busca só abra sem janela, o inverso pode acontecer.
      e.stopPropagation();
      fechar();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-tinta/40 p-4 pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) fechar();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Buscar tela"
        id="paleta-telas"
        className="w-full max-w-[560px] overflow-hidden rounded-[14px] border border-linha2 bg-superficie shadow-[0_1px_2px_rgba(20,32,26,.10),0_26px_60px_-24px_rgba(20,32,26,.6)]"
      >
        <div className="flex items-center gap-2 border-b border-linha px-4">
          <span className="text-suave">
            <Icone nome="lupa" tamanho={16} />
          </span>
          <input
            ref={campo}
            id="paleta-campo"
            role="combobox"
            aria-expanded="true"
            aria-controls="paleta-lista"
            aria-activedescendant={achados[escolhido] ? `paleta-op-${escolhido}` : undefined}
            aria-autocomplete="list"
            autoComplete="off"
            className="w-full bg-transparent py-4 text-[16px] text-tinta outline-none placeholder:text-suave"
            placeholder="Buscar tela… (ex.: produto, nota, CMV)"
            value={termo}
            onChange={(e) => {
              setTermo(e.target.value);
              setEscolhido(0);
            }}
            onKeyDown={noTeclado}
          />
        </div>

        <ul ref={lista} id="paleta-lista" role="listbox" aria-label="Telas" className="max-h-[340px] overflow-y-auto p-1.5">
          {achados.length === 0 && (
            <li className="prosa px-4 py-5 text-suave">
              Nada com esse nome. Tente o nome do grupo — ou pode ser uma tela que o seu
              acesso não abre.
            </li>
          )}
          {achados.map((i, n) => (
            <li
              key={i.href}
              id={`paleta-op-${n}`}
              role="option"
              aria-selected={n === escolhido}
              onMouseMove={() => setEscolhido(n)}
              onClick={() => ir(i.href)}
              className="paleta-op"
            >
              <span className="menu-ico">
                <Icone nome={i.icone} />
              </span>
              <span className="min-w-0 truncate">
                <Realce texto={i.nome} termo={termo} />
              </span>
              <span className="paleta-grupo">{i.grupo}</span>
            </li>
          ))}
        </ul>

        <div className="flex gap-4 border-t border-linha bg-superficie2 px-4 py-2 text-[11.5px] text-suave">
          <span>
            <b className="mono font-normal">↑ ↓</b> para andar
          </span>
          <span>
            <b className="mono font-normal">Enter</b> para abrir
          </span>
          <span>
            <b className="mono font-normal">Esc</b> para fechar
          </span>
        </div>
      </div>
    </div>
  );
}
