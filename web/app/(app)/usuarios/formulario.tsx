"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Carregando, Cartao } from "@/components/ui";
import { SENHA_MINIMA, dicaSenha } from "@/lib/senha";

/**
 * O cadastro do usuário — a mesma forma para criar e para corrigir.
 *
 * ⚠️ **Saiu da coluna da direita da lista.** A lista de papéis cresce com o
 * sistema (são seis hoje) e cada um tem descrição de duas linhas; espremida em
 * 380 px, ela empurrava o botão de salvar para fora da tela, e quem cadastrava
 * marcava as caixinhas sem ver o que estava marcando. Mesmo corte de Compras,
 * Vendas e Fornecedores: consultar e cadastrar são telas diferentes.
 *
 * ⚠️ **O papel decide o que a pessoa vê, e quem confere é o SERVIDOR.** A tela
 * escondendo um menu é conforto; a permissão é do backend.
 */

export type Papel = { id: number; nome: string; descricao: string | null; sistema: boolean };
export type Vinculo = {
  id_papel: number;
  papel: string;
  id_unidade: number | null;
  unidade: string | null;
};

type Form = { nome: string; email: string; telefone: string; senha: string; papeis: number[] };

export const VAZIO: Form = { nome: "", email: "", telefone: "", senha: "", papeis: [] };

export default function FormularioUsuario({
  inicial,
  id,
  aoGravar,
}: {
  inicial: Form;
  id?: number;
  aoGravar: () => void;
}) {
  const aviso = useAviso();
  const [form, setForm] = useState<Form>(inicial);
  const [papeis, setPapeis] = useState<Papel[] | null>(null);
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setPapeis(await api.get<Papel[]>("/papeis"));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao carregar os papéis");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    // id_unidade nulo = vale em todas as lojas; com uma loja só é o que faz sentido
    const vinculos = form.papeis.map((x) => ({ id_papel: x, id_unidade: null }));
    try {
      if (id) {
        const corpo: Record<string, unknown> = {
          nome: form.nome,
          email: form.email,
          telefone: form.telefone || null,
          papeis: vinculos,
        };
        // ⚠️ Senha em branco MANTÉM a que está: exigir redigitá-la para mudar um
        // papel é o caminho mais curto para alguém escolher uma senha fraca.
        if (form.senha) corpo.senha = form.senha;
        await api.put(`/usuarios/${id}`, corpo);
        aviso.sucesso("Usuário atualizado.");
      } else {
        await api.post("/usuarios", {
          nome: form.nome,
          email: form.email,
          telefone: form.telefone || null,
          senha: form.senha,
          papeis: vinculos,
        });
        aviso.sucesso("Usuário criado. A senha precisa ser trocada no primeiro acesso.");
      }
      aoGravar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  if (!papeis) return <Carregando />;

  return (
    <form onSubmit={salvar} className="flex flex-col gap-6">
      <Cartao titulo="A pessoa">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Campo rotulo="Nome">
            <input
              className="campo"
              required
              value={form.nome}
              onChange={(e) => setForm({ ...form, nome: e.target.value })}
            />
          </Campo>
          <Campo rotulo="E-mail" dica="é com ele que a pessoa entra">
            <input
              className="campo"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Campo>
          <Campo rotulo="Telefone">
            <input
              className="campo"
              value={form.telefone}
              onChange={(e) => setForm({ ...form, telefone: e.target.value })}
            />
          </Campo>
          <Campo
            rotulo={id ? "Nova senha" : "Senha"}
            dica={
              id
                ? "Em branco mantém. Trocar aqui obriga nova senha no próximo acesso."
                : `${dicaSenha} A pessoa troca no primeiro acesso.`
            }
          >
            <input
              className="campo"
              type="password"
              minLength={SENHA_MINIMA}
              required={!id}
              value={form.senha}
              onChange={(e) => setForm({ ...form, senha: e.target.value })}
            />
          </Campo>
        </div>
      </Cartao>

      <Cartao
        titulo="Papéis"
        descricao="O papel decide o que a pessoa vê. Quem confere é o servidor, não a tela."
      >
        <ul className="grid gap-3 sm:grid-cols-2">
          {papeis.map((p) => (
            <li key={p.id} className="flex items-start gap-2 rounded border border-linha p-3">
              <input
                id={`papel-${p.id}`}
                type="checkbox"
                className="mt-1 h-4 w-4 accent-erva"
                checked={form.papeis.includes(p.id)}
                onChange={(e) =>
                  setForm({
                    ...form,
                    papeis: e.target.checked
                      ? [...form.papeis, p.id]
                      : form.papeis.filter((x) => x !== p.id),
                  })
                }
              />
              <label htmlFor={`papel-${p.id}`} className="cursor-pointer">
                <span className="text-[14.5px] font-semibold">{p.nome}</span>
                {p.descricao && (
                  <span className="block text-[12.5px] leading-snug text-suave">
                    {p.descricao}
                  </span>
                )}
              </label>
            </li>
          ))}
        </ul>
      </Cartao>

      <div className="flex flex-wrap gap-2">
        <button className="btn btn-primario" type="submit" disabled={salvando}>
          {salvando ? "Salvando…" : id ? "Salvar" : "Criar usuário"}
        </button>
        <Link href="/usuarios" className="btn btn-secundario">
          Cancelar
        </Link>
      </div>
    </form>
  );
}
