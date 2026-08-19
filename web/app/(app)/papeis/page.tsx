"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";

type Permissao = { chave: string; modulo: string; descricao: string; ordem: number };
type Papel = {
  id: number;
  nome: string;
  descricao: string | null;
  sistema: boolean;
  permissoes: string[];
  usuarios: number;
};

export default function PaginaPapeis() {
  const [papeis, setPapeis] = useState<Papel[] | null>(null);
  const [permissoes, setPermissoes] = useState<Permissao[]>([]);
  const [sel, setSel] = useState<Papel | null>(null);
  const [novoNome, setNovoNome] = useState("");
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");

  async function carregar() {
    try {
      const [p, x] = await Promise.all([
        api.get<Papel[]>("/papeis"),
        api.get<Permissao[]>("/permissoes"),
      ]);
      setPapeis(p);
      setPermissoes(x);
      setSel((atual) => (atual ? (p.find((i) => i.id === atual.id) ?? p[0]) : p[0]) ?? null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }

  useEffect(() => {
    void carregar();
  }, []);

  useEffect(() => {
    setMarcadas(new Set(sel?.permissoes ?? []));
    setOk("");
  }, [sel]);

  const porModulo = useMemo(() => {
    const m = new Map<string, Permissao[]>();
    for (const p of permissoes) {
      if (!m.has(p.modulo)) m.set(p.modulo, []);
      m.get(p.modulo)!.push(p);
    }
    return [...m.entries()];
  }, [permissoes]);

  function alternar(chave: string) {
    const n = new Set(marcadas);
    if (n.has(chave)) n.delete(chave);
    else n.add(chave);
    setMarcadas(n);
  }

  async function salvar() {
    if (!sel) return;
    setErro("");
    setOk("");
    try {
      await api.put(`/papeis/${sel.id}`, { permissoes: [...marcadas] });
      setOk("Permissões do papel salvas.");
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível salvar");
    }
  }

  async function criar(e: FormEvent) {
    e.preventDefault();
    setErro("");
    try {
      await api.post("/papeis", { nome: novoNome, permissoes: [] });
      setNovoNome("");
      await carregar();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Não foi possível criar");
    }
  }

  async function copiar(p: Papel) {
    setErro("");
    try {
      await api.post("/papeis", {
        nome: `${p.nome} (cópia)`,
        descricao: p.descricao,
        permissoes: p.permissoes,
      });
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível copiar");
    }
  }

  if (erro && !papeis) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!papeis) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Administração</p>
        <h1 className="mt-1 text-[30px] font-bold tracking-tight">Papéis e permissões</h1>
        <p className="mt-1 max-w-[64ch] text-suave">
          Os papéis de fábrica vêm prontos e não são editáveis — copie um e ajuste a cópia.
          Ver custo é permissão à parte de ver a ficha.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {ok && <Aviso tipo="ok">{ok}</Aviso>}

      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          <Cartao titulo="Papéis">
            <ul className="flex flex-col gap-1">
              {papeis.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => setSel(p)}
                    className={`w-full rounded px-3 py-2 text-left ${
                      sel?.id === p.id ? "bg-erva-claro" : "hover:bg-superficie2"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span className="font-semibold">{p.nome}</span>
                      {p.sistema && <Etiqueta>fábrica</Etiqueta>}
                    </span>
                    <span className="mono mt-0.5 block text-[11.5px] text-suave">
                      {p.permissoes.length} permissões · {p.usuarios} usuário(s)
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Cartao>

          <Cartao titulo="Novo papel">
            <form onSubmit={criar} className="flex flex-col gap-3">
              <Campo rotulo="Nome">
                <input
                  className="campo"
                  required
                  minLength={2}
                  value={novoNome}
                  onChange={(e) => setNovoNome(e.target.value)}
                />
              </Campo>
              <button className="btn btn-secundario" type="submit">
                Criar vazio
              </button>
            </form>
          </Cartao>
        </div>

        {sel && (
          <Cartao
            titulo={sel.nome}
            descricao={sel.descricao ?? undefined}
            acao={
              sel.sistema ? (
                <button className="btn btn-secundario" onClick={() => void copiar(sel)}>
                  Copiar e ajustar
                </button>
              ) : (
                <button className="btn btn-primario" onClick={salvar}>
                  Salvar
                </button>
              )
            }
          >
            {sel.sistema && (
              <div className="mb-4">
                <Aviso tipo="info">
                  Papel de fábrica: a lista abaixo é só leitura. Ele é redefinido a cada
                  atualização do sistema — por isso a customização vive numa cópia.
                </Aviso>
              </div>
            )}

            <div className="grid gap-5 sm:grid-cols-2">
              {porModulo.map(([modulo, lista]) => (
                <div key={modulo}>
                  <p className="rotulo border-b border-linha pb-1.5">{modulo}</p>
                  <ul className="mt-2 flex flex-col gap-1.5">
                    {lista.map((p) => (
                      <li key={p.chave} className="flex items-start gap-2">
                        <input
                          id={p.chave}
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-erva"
                          disabled={sel.sistema}
                          checked={marcadas.has(p.chave)}
                          onChange={() => alternar(p.chave)}
                        />
                        <label htmlFor={p.chave} className="cursor-pointer">
                          <span className="text-[14px]">{p.descricao}</span>
                          <span className="mono block text-[11px] text-suave">{p.chave}</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Cartao>
        )}
      </div>
    </div>
  );
}
