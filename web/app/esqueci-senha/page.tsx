"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { Aviso } from "@/components/ui";

/**
 * Pedido público de recuperação.
 *
 * A tela mostra **a mesma resposta** para e-mail cadastrado e para e-mail que
 * não existe — a diferença viraria um jeito de descobrir quem trabalha na casa.
 * Por isso, também, o formulário some depois do envio: não há o que tentar de
 * novo aqui.
 */
export default function EsqueciSenha() {
  const [email, setEmail] = useState("");
  const [enviado, setEnviado] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function pedir(e: FormEvent) {
    e.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      const r = await api.post<{ message: string }>("/auth/esqueci-senha", {
        email: email.trim(),
      });
      setEnviado(r.message);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Não foi possível enviar o pedido");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <div className="w-full max-w-[380px]">
        <p className="rotulo">Botané Deli e Café</p>
        <h1 className="mt-2 text-[28px] font-bold tracking-tight">Esqueci minha senha</h1>

        {enviado ? (
          <div className="mt-6 flex flex-col gap-4">
            <Aviso tipo="ok">{enviado}</Aviso>
            <p className="text-[13.5px] leading-relaxed text-suave">
              O link vale por 30 minutos e só pode ser usado uma vez. Se nada chegar, fale com
              quem administra o sistema — dá para gerar o link por lá.
            </p>
            <a className="btn btn-secundario text-center no-underline" href="/login">
              Voltar para a entrada
            </a>
          </div>
        ) : (
          <>
            <p className="mt-2 text-[14.5px] leading-relaxed text-suave">
              Informe o e-mail do seu acesso. Se ele estiver cadastrado, mandamos um link para
              você escolher uma senha nova.
            </p>
            {erro && (
              <div className="mt-4">
                <Aviso tipo="erro">{erro}</Aviso>
              </div>
            )}
            <form onSubmit={pedir} className="mt-6 flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="rotulo">E-mail</span>
                <input
                  className="campo"
                  type="email"
                  required
                  autoFocus
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              <button className="btn btn-primario" type="submit" disabled={enviando}>
                {enviando ? "Enviando…" : "Enviar o link"}
              </button>
              <a className="link-acao self-center" href="/login">
                voltar
              </a>
            </form>
          </>
        )}
      </div>
    </main>
  );
}
