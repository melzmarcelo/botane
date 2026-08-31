"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Eu, limparSessao, temSessao, unidadeAtual } from "./api";

type Estado = {
  eu: Eu | null;
  carregando: boolean;
  /**
   * A loja em que se está — a MESMA regra do servidor (`seguranca.unidade_atual`).
   *
   * 🔑 **`localStorage` está VAZIO até alguém mexer no seletor**, e quem nunca
   * mexeu é a maioria. Tela que decidia lendo `unidadeAtual()` direto comparava
   * contra `0`: na da remessa isso escondia o botão de receber **e** o de
   * cancelar, e a pessoa ficava sem saída nenhuma numa remessa que era dela.
   * Zero não é uma loja — é a ausência de escolha, e a ausência de escolha tem
   * uma resposta, que é a mesma que o servidor dá.
   */
  unidade: number;
  pode: (chave: string) => boolean;
  recarregar: () => Promise<void>;
  sair: () => Promise<void>;
};

const Ctx = createContext<Estado>({
  eu: null,
  carregando: true,
  unidade: 0,
  pode: () => false,
  recarregar: async () => {},
  sair: async () => {},
});

export function ProvedorSessao({ children }: { children: React.ReactNode }) {
  const [eu, setEu] = useState<Eu | null>(null);
  const [carregando, setCarregando] = useState(true);
  const router = useRouter();

  const recarregar = useCallback(async () => {
    if (!temSessao()) {
      setEu(null);
      setCarregando(false);
      router.replace("/login");
      return;
    }
    try {
      setEu(await api.get<Eu>("/auth/me"));
    } catch {
      limparSessao();
      setEu(null);
      router.replace("/login");
    } finally {
      setCarregando(false);
    }
  }, [router]);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  const sair = useCallback(async () => {
    await api.logout();
    setEu(null);
    router.replace("/login");
  }, [router]);

  // A tela esconde o que a pessoa não pode; o servidor é quem realmente barra.
  const pode = useCallback((chave: string) => !!eu?.permissoes.includes(chave), [eu]);

  // ⚠️ **Espelha `seguranca.unidade_atual` passo a passo**: a escolhida no
  // seletor, senão a matriz para quem enxerga todas, senão a de menor id. Uma
  // segunda regra aqui faria a tela discordar do servidor sobre em que loja a
  // pessoa está — e o sintoma seria um 403 numa ação que a própria tela ofereceu.
  // ⚠️ Ler `localStorage` no render é seguro AQUI porque `eu` nasce nulo: a
  // primeira pintura do cliente é igual à do servidor, e o valor só aparece
  // depois que o `/auth/me` responde, que é sempre no navegador.
  const unidade = useMemo(() => {
    const escolhida = unidadeAtual();
    if (escolhida) return Number(escolhida);
    if (!eu?.unidades?.length) return 0;
    const porId = [...eu.unidades].sort((a, b) => a.id - b.id);
    return (eu.todas_unidades ? (porId.find((u) => u.matriz) ?? porId[0]) : porId[0]).id;
  }, [eu]);

  return (
    <Ctx.Provider value={{ eu, carregando, unidade, pode, recarregar, sair }}>
      {children}
    </Ctx.Provider>
  );
}

export const useSessao = () => useContext(Ctx);
