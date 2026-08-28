"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Aviso } from "@/components/ui";

export default function Login() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [manter, setManter] = useState(false);
  const router = useRouter();

  async function entrar(e: FormEvent) {
    e.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      const s = await api.login(email.trim(), senha, manter);
      router.replace(s.usuario.trocar_senha ? "/trocar-senha" : "/");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Não foi possível entrar");
      setEnviando(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <div className="w-full max-w-[380px]">
        <h1 className="text-[42px] font-extrabold leading-[0.95] tracking-[-0.035em]">
          Botané
          <span className="block text-[26px] font-semibold tracking-[-0.02em] text-erva">
            Deli e Café
          </span>
        </h1>
        <p className="rotulo mt-3">Gestão de custo · CMV</p>

        <div
          className="mt-5 h-[18px] border-b border-linha2 opacity-80"
          style={{
            background:
              "repeating-linear-gradient(to right, var(--color-linha2) 0 1px, transparent 1px 10px) left bottom/100% 6px no-repeat, repeating-linear-gradient(to right, var(--color-linha2) 0 1px, transparent 1px 50px) left bottom/100% 12px no-repeat",
          }}
          aria-hidden
        />

        <form onSubmit={entrar} className="mt-8 flex flex-col gap-4">
          <label className="block">
            <span className="rotulo">E-mail</span>
            <input
              className="campo mt-1.5"
              type="email"
              autoComplete="username"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="rotulo">Senha</span>
            <input
              className="campo mt-1.5"
              type="password"
              autoComplete="current-password"
              required
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
            />
          </label>

          {/*
            ⚠️ Desmarcado por padrão de propósito: a opção segura é a que vale
            para quem não escolheu nada. A frase abaixo diz o que cada estado
            FAZ — "manter conectado" sozinho não avisa que a sessão sobrevive a
            fechar o navegador, que é justamente a parte que importa num
            computador compartilhado.
          */}
          <label className="flex items-start gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-erva cursor-pointer"
              checked={manter}
              onChange={(e) => setManter(e.target.checked)}
            />
            <span className="text-[13.5px] leading-snug">
              <b>Manter conectado neste aparelho</b>
              <span className="block text-neutro-500">
                {manter
                  ? "A sessão continua aberta depois de fechar o navegador. Não use em computador compartilhado."
                  : "A sessão se encerra quando você fechar o navegador."}
              </span>
            </span>
          </label>

          {erro && <Aviso tipo="erro">{erro}</Aviso>}

          <button className="btn btn-primario mt-1" type="submit" disabled={enviando}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <p className="mt-6 text-[13.5px]">
          <a href="/esqueci-senha" className="text-erva underline-offset-2 hover:underline">
            Esqueci minha senha
          </a>
        </p>
        <p className="mt-2 text-[13px] leading-relaxed text-suave">
          O link para escolher uma senha nova chega no seu e-mail e vale por 30 minutos.
        </p>
      </div>
    </main>
  );
}
