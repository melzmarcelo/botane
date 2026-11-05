"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Aviso } from "@/components/ui";
import MarcaDeEntrada from "@/components/marca-de-entrada";

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
    // 🔑 1.3.0 (protótipo aprovado em `apresentacao/novo-layout/`): a entrada em duas metades —
    // o painel da casa à esquerda e o formulário à direita. ⚠️ No celular o painel some: lá o
    // que importa é chegar ao campo sem rolar.
    <main className="flex min-h-screen">
      <section
        aria-hidden
        className="hidden flex-1 flex-col justify-between gap-12 bg-[#17271f] px-14 py-12 text-white lg:flex"
      >
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-white/10">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#bfe3cb" strokeWidth="2"
               strokeLinecap="round" strokeLinejoin="round"><path d="M5 19c0-8 6-14 14-14 0 8-6 14-14 14z M5 19l7-7" /></svg>
        </span>
        <div className="max-w-[460px]">
          <p className="text-[40px] font-extrabold leading-[1.12] tracking-[-0.02em]">
            Toda a operação da casa, num lugar só.
          </p>
          <p className="mt-4 text-[16px] leading-relaxed text-[#c5d6cb]">
            Compras, estoque, produção, vendas e custos ligados entre si, com relatórios prontos.
          </p>
          <ul className="mt-8 flex flex-col gap-3.5 text-[15px] text-[#e4eee7]">
            {["Telas limpas, com o mesmo padrão em todo o sistema",
              "Estoque, fichas e CMV conversando entre si",
              "No computador, no tablet e no celular"].map((t) => (
              <li key={t} className="flex items-center gap-3">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#8fd1a6" strokeWidth="2.2"
                     strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                {t}
              </li>
            ))}
          </ul>
        </div>
        <span />
      </section>

      <div className="flex flex-1 items-center justify-center px-5 py-12">
      <div className="w-full max-w-[400px]">
        <MarcaDeEntrada grande />
        <h2 className="mt-8 text-[22px] font-extrabold tracking-[-0.02em]">Bem-vindo de volta</h2>
        <p className="mt-1 text-[15px] text-suave">Entre para continuar de onde parou.</p>

        <form onSubmit={entrar} className="mt-6 flex flex-col gap-4">
          <label className="block">
            <span className="rotulo-campo">E-mail</span>
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
            <span className="rotulo-campo">Senha</span>
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
              <span className="block text-suave">
                {manter
                  ? "A sessão continua aberta depois de fechar o navegador. Não use em computador compartilhado."
                  : "A sessão se encerra quando você fechar o navegador."}
              </span>
            </span>
          </label>

          {erro && <Aviso tipo="erro">{erro}</Aviso>}

          <button className="btn btn-primario mt-1 h-12 text-[15px]" type="submit" aria-busy={enviando} disabled={enviando}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <p className="mt-6 text-[13.5px]">
          <a href="/esqueci-senha" className="text-erva underline underline-offset-2">
            Esqueci minha senha
          </a>
        </p>
        <p className="mt-2 text-[13px] leading-relaxed text-suave">
          O link para escolher uma senha nova chega no seu e-mail e vale por 30 minutos.
        </p>
      </div>
      </div>
    </main>
  );
}
