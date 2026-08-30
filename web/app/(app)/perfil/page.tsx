"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Cartao, Etiqueta } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";

/**
 * O próprio cadastro de quem entrou.
 *
 * ⚠️ **Só nome e telefone se editam aqui.** E-mail é a identidade de quem
 * entra — trocá-lo derrubaria o login da própria pessoa no instante seguinte —,
 * e papel e loja são permissão: quem se dá permissão não tem permissão nenhuma.
 * Os três ficam à vista, porque a pergunta "com que conta eu estou?" é metade
 * do motivo de alguém abrir esta tela.
 */
export default function PaginaPerfil() {
  const aviso = useAviso();
  const { eu, recarregar } = useSessao();
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (!eu) return;
    setNome(eu.nome ?? "");
    setTelefone(eu.telefone ?? "");
  }, [eu]);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    try {
      await api.put("/auth/me", { nome: nome.trim(), telefone: telefone.trim() || null });
      // Sem recarregar a sessão, o nome no canto superior continuaria o antigo —
      // e quem acabou de corrigir o próprio nome olha exatamente para lá.
      await recarregar();
      aviso.sucesso("Perfil atualizado");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-[560px] flex-col gap-6">
      <header>
        <p className="rotulo">Sua conta</p>
        <h1 className="mt-1 text-[30px] font-bold tracking-tight">Perfil</h1>
        <p className="mt-1 text-suave">
          Seus dados de cadastro. Para trocar a senha, use{" "}
          <Link href="/trocar-senha">Alterar senha</Link>.
        </p>
      </header>

      <Cartao>
        <form className="flex flex-col gap-4" onSubmit={salvar}>
          <Campo rotulo="Nome">
            <input
              className="campo"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              minLength={2}
              maxLength={120}
              required
            />
          </Campo>
          <Campo rotulo="Telefone" dica="Opcional.">
            <input
              className="campo"
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              maxLength={30}
            />
          </Campo>
          <Campo
            rotulo="E-mail"
            dica="É com ele que você entra. Quem muda o e-mail de alguém é o administrador, em Usuários."
          >
            <input className="campo" value={eu?.email ?? ""} disabled />
          </Campo>

          <div>
            <span className="rotulo">Papéis</span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {eu?.papeis.length ? (
                eu.papeis.map((p) => <Etiqueta key={p}>{p}</Etiqueta>)
              ) : (
                <span className="text-[14px] text-suave">sem papel</span>
              )}
            </div>
          </div>

          <div>
            <span className="rotulo">Lojas</span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {eu?.todas_unidades && <Etiqueta cor="erva">todas</Etiqueta>}
              {eu?.unidades.map((u) => (
                <Etiqueta key={u.id}>{u.apelido ?? u.nome}</Etiqueta>
              ))}
            </div>
          </div>

          <div className="flex justify-end">
            <button className="btn btn-primario" disabled={salvando}>
              {salvando ? "Salvando…" : "Salvar"}
            </button>
          </div>
        </form>
      </Cartao>
    </div>
  );
}
