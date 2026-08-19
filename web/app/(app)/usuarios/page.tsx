"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Papel = { id: number; nome: string; descricao: string | null; sistema: boolean };
type Vinculo = { id_papel: number; papel: string; id_unidade: number | null; unidade: string | null };
type Usuario = {
  id: number;
  nome: string;
  email: string;
  telefone: string | null;
  ativo: boolean;
  ultimo_acesso: string | null;
  bloqueado: boolean;
  papeis: Vinculo[];
};

const vazio = { nome: "", email: "", telefone: "", senha: "", papeis: [] as number[] };

export default function PaginaUsuarios() {
  const { eu } = useSessao();
  const [usuarios, setUsuarios] = useState<Usuario[] | null>(null);
  const [papeis, setPapeis] = useState<Papel[]>([]);
  const [form, setForm] = useState({ ...vazio });
  const [editando, setEditando] = useState<number | null>(null);
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");
  const [link, setLink] = useState<{ nome: string; url: string } | null>(null);
  const [salvando, setSalvando] = useState(false);

  async function carregar() {
    try {
      const [u, p] = await Promise.all([
        api.get<Usuario[]>("/usuarios?incluir_inativos=true"),
        api.get<Papel[]>("/papeis"),
      ]);
      setUsuarios(u);
      setPapeis(p);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }

  useEffect(() => {
    void carregar();
  }, []);

  function novo() {
    setEditando(null);
    setForm({ ...vazio });
    setOk("");
    setErro("");
  }

  function editar(u: Usuario) {
    setEditando(u.id);
    setForm({
      nome: u.nome,
      email: u.email,
      telefone: u.telefone ?? "",
      senha: "",
      papeis: u.papeis.map((v) => v.id_papel),
    });
    setOk("");
    setErro("");
  }

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    setOk("");
    // id_unidade nulo = vale em todas as lojas; com uma loja só é o que faz sentido
    const vinculos = form.papeis.map((id) => ({ id_papel: id, id_unidade: null }));
    try {
      if (editando) {
        const corpo: Record<string, unknown> = {
          nome: form.nome,
          email: form.email,
          telefone: form.telefone || null,
          papeis: vinculos,
        };
        if (form.senha) corpo.senha = form.senha;
        await api.put(`/usuarios/${editando}`, corpo);
        setOk("Usuário atualizado.");
      } else {
        await api.post("/usuarios", {
          nome: form.nome,
          email: form.email,
          telefone: form.telefone || null,
          senha: form.senha,
          papeis: vinculos,
        });
        setOk("Usuário criado. A senha precisa ser trocada no primeiro acesso.");
      }
      novo();
      await carregar();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function alternarAtivo(u: Usuario) {
    setErro("");
    try {
      if (u.ativo) await api.delete(`/usuarios/${u.id}`);
      else await api.put(`/usuarios/${u.id}`, { ativo: true });
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao mudar a situação");
    }
  }

  async function desbloquear(u: Usuario) {
    await api.post(`/usuarios/${u.id}/desbloquear`);
    await carregar();
  }

  /**
   * Manda o link de recuperação — e mostra o link.
   *
   * Enquanto não houver SMTP configurado, é assim que o dono resolve o
   * esquecimento da equipe: copia o link e passa pela pessoa. Continua sendo
   * melhor que escolher uma senha pela outra pessoa e mandá-la por mensagem,
   * porque o link vale meia hora e quem escolhe a senha é o dono dela.
   */
  async function linkDeSenha(u: Usuario) {
    setErro("");
    setOk("");
    setLink(null);
    try {
      const r = await api.post<{ link: string; modo: string; message: string }>(
        `/usuarios/${u.id}/recuperar-senha`,
      );
      setOk(r.message);
      if (r.modo !== "real") setLink({ nome: u.nome, url: r.link });
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gerar o link");
    }
  }

  if (erro && !usuarios) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!usuarios) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Administração</p>
          <h1 className="mt-1 text-[30px] font-bold tracking-tight">Usuários</h1>
          <p className="mt-1 max-w-[62ch] text-suave">
            Cada pessoa da casa com o seu login. O papel decide o que ela vê — e quem confere é
            o servidor, não a tela.
          </p>
        </div>
        <button className="btn btn-secundario" onClick={novo}>
          Novo usuário
        </button>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {ok && <Aviso tipo="ok">{ok}</Aviso>}

      {link && (
        <Cartao
          titulo={`Link para ${link.nome}`}
          descricao="Vale por 30 minutos e só pode ser usado uma vez."
          acao={
            <div className="flex items-center gap-2">
              <button
                className="btn btn-secundario"
                onClick={() => void navigator.clipboard.writeText(link.url)}
              >
                Copiar
              </button>
              <button className="rotulo hover:text-erro" onClick={() => setLink(null)}>
                fechar
              </button>
            </div>
          }
        >
          <p className="mono break-all text-[13px]">{link.url}</p>
        </Cartao>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Cartao titulo="Quem tem acesso">
          {!usuarios.length ? (
            <Vazio>Nenhum usuário ainda.</Vazio>
          ) : (
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Pessoa</th>
                    <th>Papéis</th>
                    <th>Último acesso</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {usuarios.map((u) => (
                    <tr key={u.id} className={u.ativo ? "" : "opacity-55"}>
                      <td>
                        <button className="text-left" onClick={() => editar(u)}>
                          <span className="font-semibold hover:text-erva">{u.nome}</span>
                          <span className="block text-[13px] text-suave">{u.email}</span>
                        </button>
                        {u.bloqueado && (
                          <button
                            className="rotulo mt-1 block text-erro hover:underline"
                            onClick={() => void desbloquear(u)}
                          >
                            bloqueado · desbloquear
                          </button>
                        )}
                        {u.ativo && (
                          <button
                            className="rotulo mt-1 block hover:text-erva"
                            onClick={() => void linkDeSenha(u)}
                          >
                            esqueceu a senha?
                          </button>
                        )}
                      </td>
                      <td>
                        <div className="flex flex-wrap gap-1">
                          {u.papeis.length ? (
                            u.papeis.map((v) => (
                              <Etiqueta key={v.id_papel} cor="erva">
                                {v.papel}
                              </Etiqueta>
                            ))
                          ) : (
                            <Etiqueta cor="alerta">sem papel</Etiqueta>
                          )}
                        </div>
                      </td>
                      <td className="mono text-[13px] text-suave">
                        {u.ultimo_acesso
                          ? new Date(u.ultimo_acesso).toLocaleString("pt-BR")
                          : "nunca"}
                      </td>
                      <td className="text-right">
                        {u.id !== eu?.id && (
                          <button
                            className="rotulo hover:text-erva"
                            onClick={() => void alternarAtivo(u)}
                          >
                            {u.ativo ? "desativar" : "reativar"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Cartao>

        <Cartao titulo={editando ? "Editar usuário" : "Novo usuário"}>
          <form onSubmit={salvar} className="flex flex-col gap-4">
            <Campo rotulo="Nome">
              <input
                className="campo"
                required
                value={form.nome}
                onChange={(e) => setForm({ ...form, nome: e.target.value })}
              />
            </Campo>
            <Campo rotulo="E-mail">
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
              rotulo={editando ? "Nova senha" : "Senha"}
              dica={
                editando
                  ? "Deixe em branco para manter. Trocar aqui obriga nova senha no próximo acesso."
                  : "Mínimo de 8 caracteres. A pessoa troca no primeiro acesso."
              }
            >
              <input
                className="campo"
                type="password"
                minLength={8}
                required={!editando}
                value={form.senha}
                onChange={(e) => setForm({ ...form, senha: e.target.value })}
              />
            </Campo>

            <div>
              <span className="rotulo">Papéis</span>
              <ul className="mt-1.5 flex flex-col gap-1.5">
                {papeis.map((p) => (
                  <li key={p.id} className="flex items-start gap-2">
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
            </div>

            <div className="flex gap-2">
              <button className="btn btn-primario" type="submit" disabled={salvando}>
                {salvando ? "Salvando…" : editando ? "Salvar" : "Criar"}
              </button>
              {editando && (
                <button className="btn btn-secundario" type="button" onClick={novo}>
                  Cancelar
                </button>
              )}
            </div>
          </form>
        </Cartao>
      </div>
    </div>
  );
}
