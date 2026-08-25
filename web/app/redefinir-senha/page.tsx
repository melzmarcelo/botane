"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Aviso } from "@/components/ui";
import { SENHA_MINIMA } from "@/lib/senha";

/**
 * A tela que o link do e-mail abre.
 *
 * Ela **confere o link antes** de mostrar o formulário: sem isso a pessoa
 * digita a senha nova duas vezes para só então descobrir que o link tinha
 * vencido — e aí já esqueceu qual senha inventou.
 */
function Formulario() {
  const parametros = useSearchParams();
  const router = useRouter();
  const token = parametros.get("token") ?? "";

  const [nome, setNome] = useState<string | null>(null);
  const [invalido, setInvalido] = useState("");
  const [senha, setSenha] = useState("");
  const [repetida, setRepetida] = useState("");
  const [erro, setErro] = useState("");
  const [pronto, setPronto] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!token) {
      setInvalido("Link incompleto. Abra o endereço exatamente como veio no e-mail.");
      return;
    }
    void api
      .get<{ nome: string }>(`/auth/redefinir-senha/${encodeURIComponent(token)}`)
      .then((r) => setNome(r.nome))
      .catch((e) => setInvalido(e instanceof Error ? e.message : "Link inválido"));
  }, [token]);

  async function redefinir(e: FormEvent) {
    e.preventDefault();
    if (senha !== repetida) {
      setErro("As duas senhas precisam ser iguais.");
      return;
    }
    setErro("");
    setEnviando(true);
    try {
      const r = await api.post<{ message: string; detalhe: string }>("/auth/redefinir-senha", {
        token,
        senha,
      });
      setPronto(`${r.message} ${r.detalhe}`);
      setTimeout(() => router.replace("/login"), 2500);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Não foi possível redefinir");
      setEnviando(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <div className="w-full max-w-[380px]">
        <p className="rotulo">Botané Deli e Café</p>
        <h1 className="mt-2 text-[28px] font-bold tracking-tight">Escolher uma senha nova</h1>

        {invalido ? (
          <div className="mt-6 flex flex-col gap-4">
            <Aviso tipo="erro">{invalido}</Aviso>
            <a className="btn btn-primario text-center no-underline" href="/esqueci-senha">
              Pedir outro link
            </a>
          </div>
        ) : pronto ? (
          <div className="mt-6 flex flex-col gap-4">
            <Aviso tipo="ok">{pronto}</Aviso>
            <a className="btn btn-primario text-center no-underline" href="/login">
              Entrar agora
            </a>
          </div>
        ) : nome === null ? (
          <p className="mt-6 text-suave">Conferindo o link…</p>
        ) : (
          <>
            <p className="mt-2 text-[14.5px] leading-relaxed text-suave">
              Olá, {nome}. Escolha uma senha de pelo menos {SENHA_MINIMA} caracteres.
            </p>
            {erro && (
              <div className="mt-4">
                <Aviso tipo="erro">{erro}</Aviso>
              </div>
            )}
            <form onSubmit={redefinir} className="mt-6 flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="rotulo">Senha nova</span>
                <input
                  className="campo"
                  type="password"
                  required
                  minLength={SENHA_MINIMA}
                  autoFocus
                  autoComplete="new-password"
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="rotulo">Repita a senha</span>
                <input
                  className="campo"
                  type="password"
                  required
                  minLength={SENHA_MINIMA}
                  autoComplete="new-password"
                  value={repetida}
                  onChange={(e) => setRepetida(e.target.value)}
                />
              </label>
              <button className="btn btn-primario" type="submit" disabled={enviando}>
                {enviando ? "Salvando…" : "Salvar a senha"}
              </button>
              <p className="text-[13px] leading-relaxed text-suave">
                Ao salvar, todas as sessões abertas nesta conta são encerradas — inclusive em
                outros aparelhos.
              </p>
            </form>
          </>
        )}
      </div>
    </main>
  );
}

export default function RedefinirSenha() {
  // `useSearchParams` exige a fronteira de Suspense; sem ela a página inteira
  // vira renderização sob demanda.
  return (
    <Suspense fallback={<main className="p-10 text-suave">Carregando…</main>}>
      <Formulario />
    </Suspense>
  );
}
