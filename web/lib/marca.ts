"use client";

import { useEffect, useState } from "react";
import { BASE_API, urlArquivo } from "@/lib/api";
import { EVENTO_EMPRESA } from "@/lib/eventos";

/**
 * De quem é este sistema: o nome e a logo da CASA, lidos do cadastro.
 *
 * 🔑 **Pedido do dono (05/10/2026):** o sistema nasceu para uma casa e passou a
 * ser levado a outras do mesmo ramo. O nome dela estava escrito no login, nas
 * telas de senha, no título da aba e no topo — e cada um mostraria a marca de
 * OUTRA empresa para o cliente novo. Agora tudo sai de Administração ▸ Empresa.
 *
 * ⚠️ **Rota pública (`/publico/marca`), e por isso sem `api.get`**: a tela de
 * entrada é de quem ainda não tem token, e passar pelo cliente autenticado
 * dispararia renovação de sessão onde não há sessão. Mesmo caminho do `/saude`
 * do rodapé.
 */
export type Marca = { nome: string; logo: string | null };

/**
 * Como o produto se chama quando o assunto é ELE, e não a casa. ⚠️ Genérico de
 * propósito: o produto ainda não tem nome próprio — quando tiver, troca aqui e
 * em `api/services/marca.py`.
 */
export const NOME_SISTEMA = "Sistema de gestão";

const CHAVE = "botane.marca";

/** A última marca vista neste navegador — pinta na hora e serve à tela sem rede. */
export function marcaGuardada(): Marca | null {
  try {
    const m = JSON.parse(localStorage.getItem(CHAVE) ?? "null");
    return m && typeof m.nome === "string" ? m : null;
  } catch {
    return null;
  }
}

export async function buscarMarca(): Promise<Marca> {
  const r = await fetch(`${BASE_API}/publico/marca`);
  if (!r.ok) throw new Error("Falha ao carregar a marca");
  const d: { nome: string | null; logo_url: string | null } = await r.json();
  const marca = { nome: d.nome || NOME_SISTEMA, logo: urlArquivo(d.logo_url) };
  try {
    localStorage.setItem(CHAVE, JSON.stringify(marca));
  } catch {
    /* navegador sem armazenamento: só não lembra */
  }
  return marca;
}

/**
 * A marca, para qualquer tela. Nula só até a primeira resposta num navegador
 * que nunca abriu o sistema — quem pinta decide o que mostrar nesse instante
 * (o login deixa o espaço reservado, para o formulário não pular).
 *
 * ⚠️ **A guardada entra num efeito, não no inicializador do estado**: estas
 * telas são pré-renderizadas no servidor, e ler `localStorage` na primeira
 * pintura daria HTML diferente do do servidor (erro de hidratação).
 */
export function useMarca(): Marca | null {
  const [marca, setMarca] = useState<Marca | null>(null);

  useEffect(() => {
    let vivo = true;
    const guardada = marcaGuardada();
    if (guardada) setMarca(guardada);
    const buscar = () =>
      buscarMarca()
        .then((m) => vivo && setMarca(m))
        // Sem resposta e sem nada guardado, o nome genérico: tela de entrada
        // sem título nenhum parece quebrada.
        .catch(() => vivo && setMarca((atual) => atual ?? { nome: NOME_SISTEMA, logo: null }));
    void buscar();
    // A tela de empresa avisa quando o nome ou a logo mudam.
    window.addEventListener(EVENTO_EMPRESA, buscar);
    return () => {
      vivo = false;
      window.removeEventListener(EVENTO_EMPRESA, buscar);
    };
  }, []);

  return marca;
}
