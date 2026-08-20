"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Aviso, Campo, Cartao } from "@/components/ui";

export default function TrocarSenha() {
  const aviso = useAviso();
  const { eu, sair } = useSessao();
  const router = useRouter();
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [repetida, setRepetida] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (nova !== repetida) {
      aviso.erro("A confirmação não confere com a nova senha");
      return;
    }
    setEnviando(true);
    try {
      await api.post("/auth/trocar-senha", { senha_atual: atual, senha_nova: nova });
      // Trocar a senha derruba as sessões — inclusive esta. Voltar ao login é o certo.
      await sair();
      router.replace("/login");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível trocar");
      setEnviando(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-[520px] flex-col gap-6">
      <header>
        <p className="rotulo">Sua conta</p>
        <h1 className="mt-1 text-[30px] font-bold tracking-tight">Trocar senha</h1>
        {eu?.trocar_senha && (
          <div className="mt-2">
            <Aviso tipo="info">
              Sua senha foi definida por outra pessoa. Troque agora — as demais sessões serão
              encerradas.
            </Aviso>
          </div>
        )}
      </header>

      <Cartao>
        <form onSubmit={salvar} className="flex flex-col gap-4">
          <Campo rotulo="Senha atual">
            <input
              className="campo"
              type="password"
              required
              autoComplete="current-password"
              value={atual}
              onChange={(e) => setAtual(e.target.value)}
            />
          </Campo>
          <Campo rotulo="Nova senha" dica="Mínimo de 8 caracteres.">
            <input
              className="campo"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={nova}
              onChange={(e) => setNova(e.target.value)}
            />
          </Campo>
          <Campo rotulo="Repita a nova senha">
            <input
              className="campo"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={repetida}
              onChange={(e) => setRepetida(e.target.value)}
            />
          </Campo>


          <button className="btn btn-primario" type="submit" disabled={enviando}>
            {enviando ? "Trocando…" : "Trocar senha"}
          </button>
        </form>
      </Cartao>
    </div>
  );
}
