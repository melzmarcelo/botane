"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Eu, limparSessao, temSessao } from "./api";

type Estado = {
  eu: Eu | null;
  carregando: boolean;
  pode: (chave: string) => boolean;
  recarregar: () => Promise<void>;
  sair: () => Promise<void>;
};

const Ctx = createContext<Estado>({
  eu: null,
  carregando: true,
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

  return (
    <Ctx.Provider value={{ eu, carregando, pode, recarregar, sair }}>{children}</Ctx.Provider>
  );
}

export const useSessao = () => useContext(Ctx);
