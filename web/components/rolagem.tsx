"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

/**
 * Voltar devolve a tela ONDE a pessoa estava — não no topo.
 *
 * 🔑 **Pedido do dono (06/10/2026):** *"ir lá, ver, e voltar, continuando no
 * mesmo contexto"*. O filtro e a página já voltavam (moram na URL), mas a
 * rolagem não: quem abria o 40º produto da lista e voltava caía no primeiro.
 *
 * ⚠️ **O navegador tenta, e chega cedo demais.** Ele restaura a rolagem no
 * instante em que a URL volta; nessa hora a tela ainda está buscando os dados,
 * a página tem a altura de um "carregando" e não há para onde rolar. Quando a
 * lista chega, ninguém tenta de novo.
 *
 * Então: a posição de cada endereço é anotada enquanto se rola, e ao VOLTAR
 * (`popstate`) a tela espera a página crescer até caber a posição — até três
 * segundos — e só então rola.
 *
 * ⚠️ **Só no voltar/avançar.** Abrir uma tela por link ou pelo menu é ir a ela
 * de novo, e começa do topo: devolver ali a rolagem de uma visita antiga seria
 * a tela decidir pela pessoa.
 *
 * ⚠️ **Enquanto restaura, não anota.** A tela curta do "carregando" gera um
 * evento de rolagem para o zero, e anotá-lo apagaria a posição que se está
 * tentando devolver.
 *
 * ⚠️ **Quem arma a restauração é o próprio `popstate`, não o efeito da rota.**
 * A primeira versão marcava no `popstate` e restaurava no efeito de
 * `usePathname` — e nunca restaurou: o Next conclui a troca de tela DENTRO do
 * tratador dele, que roda antes do nosso, então o efeito já tinha passado
 * quando a marca chegava. O efeito da rota só serve para CANCELAR: se a pessoa
 * sair por um link no meio da espera, a restauração morre.
 */
const CHAVE = "botane:rolagem";
const ESPERA_MAXIMA = 3000;

function ler(): Record<string, number> {
  try {
    return JSON.parse(sessionStorage.getItem(CHAVE) || "{}");
  } catch {
    return {};
  }
}

function gravar(endereco: string, y: number) {
  try {
    const tudo = ler();
    tudo[endereco] = y;
    // Sessenta endereços bastam para qualquer ida e volta, e o limite impede
    // que um dia inteiro de trabalho encha o armazenamento da aba.
    const chaves = Object.keys(tudo);
    for (const velha of chaves.slice(0, Math.max(0, chaves.length - 60))) delete tudo[velha];
    sessionStorage.setItem(CHAVE, JSON.stringify(tudo));
  } catch {
    // Armazenamento cheio ou bloqueado: voltar para o topo é só o de antes.
  }
}

const enderecoDeAgora = () => window.location.pathname + window.location.search;

type Alvo = { endereco: string; y: number; ate: number };

export default function Rolagem() {
  const caminho = usePathname();
  const busca = useSearchParams();
  // A restauração em andamento. Nula quando não há nenhuma.
  const restaurando = useRef<Alvo | null>(null);

  useEffect(() => {
    // O navegador não disputa a rolagem: quem devolve é este componente.
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";

    let quadro = 0;
    const aoRolar = () => {
      if (restaurando.current) return;
      cancelAnimationFrame(quadro);
      quadro = requestAnimationFrame(() => gravar(enderecoDeAgora(), window.scrollY));
    };

    const aoVoltar = () => {
      const endereco = enderecoDeAgora();
      const y = ler()[endereco] ?? 0;
      const alvo: Alvo = { endereco, y, ate: Date.now() + ESPERA_MAXIMA };
      restaurando.current = alvo;
      const tentar = () => {
        // Outra navegação tomou o lugar desta: quem manda é a mais nova.
        if (restaurando.current !== alvo) return;
        if (enderecoDeAgora() !== alvo.endereco) {
          restaurando.current = null;
          return;
        }
        const cabe = document.documentElement.scrollHeight - window.innerHeight >= alvo.y - 2;
        if (cabe || Date.now() > alvo.ate) {
          window.scrollTo({ top: alvo.y, behavior: "auto" });
          restaurando.current = null;
          return;
        }
        setTimeout(tentar, 80);
      };
      // Um quadro de folga: a tela nova precisa ter sido pintada para a altura
      // dela (e não a da tela de onde se veio) responder à pergunta "cabe?".
      requestAnimationFrame(tentar);
    };

    // ⚠️ **Quem mexe na tela durante a espera manda mais que a memória.** Sem
    // isto, a pessoa que voltasse e começasse a rolar antes de a lista chegar
    // seria puxada de volta para a posição antiga meio segundo depois.
    const desistir = () => {
      restaurando.current = null;
    };

    window.addEventListener("scroll", aoRolar, { passive: true });
    window.addEventListener("popstate", aoVoltar);
    window.addEventListener("wheel", desistir, { passive: true });
    window.addEventListener("touchmove", desistir, { passive: true });
    window.addEventListener("keydown", desistir);
    return () => {
      window.removeEventListener("scroll", aoRolar);
      window.removeEventListener("popstate", aoVoltar);
      window.removeEventListener("wheel", desistir);
      window.removeEventListener("touchmove", desistir);
      window.removeEventListener("keydown", desistir);
      cancelAnimationFrame(quadro);
    };
  }, []);

  // Trocar de tela por um LINK cancela a restauração que estivesse esperando.
  useEffect(() => {
    const alvo = restaurando.current;
    if (alvo && alvo.endereco !== enderecoDeAgora()) restaurando.current = null;
  }, [caminho, busca]);

  return null;
}
