"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Fornecedor, mascaraCnpj, reais } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Form = {
  nome: string;
  nome_fantasia: string;
  cnpj: string;
  contato: string;
  telefone: string;
  whatsapp: string;
  email: string;
  cidade: string;
  uf: string;
  prazo_entrega_dias: string;
  dias_entrega: string;
  pedido_minimo: string;
  observacao: string;
};

const VAZIO: Form = {
  nome: "", nome_fantasia: "", cnpj: "", contato: "", telefone: "", whatsapp: "",
  email: "", cidade: "", uf: "", prazo_entrega_dias: "", dias_entrega: "",
  pedido_minimo: "", observacao: "",
};

const texto = (v: string) => (v.trim() === "" ? null : v.trim());
const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

export default function PaginaFornecedores() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeEditar = pode("cadastros.fornecedores");

  const [lista, setLista] = useState<Fornecedor[] | null>(null);
  const [busca, setBusca] = useState("");
  const [inativos, setInativos] = useState(false);
  const [f, setF] = useState<Form>(VAZIO);
  const [editando, setEditando] = useState<number | null>(null);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    const q = new URLSearchParams();
    if (busca.trim()) q.set("busca", busca.trim());
    if (inativos) q.set("incluir_inativos", "true");
    try {
      setLista(await api.get<Fornecedor[]>(`/fornecedores?${q}`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [busca, inativos]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  function novo() {
    setEditando(null);
    setF(VAZIO);
    setErro("");
  }

  function editar(x: Fornecedor) {
    setEditando(x.id);
    setF({
      nome: x.nome ?? "",
      nome_fantasia: x.nome_fantasia ?? "",
      cnpj: x.cnpj ? mascaraCnpj(x.cnpj) : "",
      contato: x.contato ?? "",
      telefone: x.telefone ?? "",
      whatsapp: x.whatsapp ?? "",
      email: x.email ?? "",
      cidade: x.cidade ?? "",
      uf: x.uf ?? "",
      prazo_entrega_dias: x.prazo_entrega_dias?.toString() ?? "",
      dias_entrega: x.dias_entrega ?? "",
      pedido_minimo: x.pedido_minimo?.toString() ?? "",
      observacao: x.observacao ?? "",
    });
    setErro("");
  }

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    const corpo = {
      nome: f.nome.trim(),
      nome_fantasia: texto(f.nome_fantasia),
      cnpj: texto(f.cnpj),
      contato: texto(f.contato),
      telefone: texto(f.telefone),
      whatsapp: texto(f.whatsapp),
      email: texto(f.email),
      cidade: texto(f.cidade),
      uf: texto(f.uf),
      prazo_entrega_dias: num(f.prazo_entrega_dias),
      dias_entrega: texto(f.dias_entrega),
      pedido_minimo: num(f.pedido_minimo),
      observacao: texto(f.observacao),
    };
    try {
      if (editando) {
        await api.put(`/fornecedores/${editando}`, corpo);
        aviso.sucesso("Fornecedor atualizado.");
      } else {
        await api.post("/fornecedores", corpo);
        aviso.sucesso("Fornecedor criado.");
      }
      novo();
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function alternar(x: Fornecedor) {
    setErro("");
    try {
      if (x.ativo) await api.delete(`/fornecedores/${x.id}`);
      else await api.put(`/fornecedores/${x.id}`, { ativo: true });
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao mudar a situação");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Cadastros</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Fornecedores</h1>
          <p className="mt-1 max-w-[62ch] text-suave">
            De quem a casa compra. O CNPJ é o que liga a nota fiscal que vem do Omie ao
            fornecedor certo — sem ele, a conciliação vira trabalho manual.
          </p>
        </div>
        {podeEditar && (
          <button className="btn btn-secundario" onClick={novo}>
            Novo fornecedor
          </button>
        )}
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex flex-col gap-4">
          <Cartao>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="min-w-0 flex-1">
                <span className="rotulo">Buscar</span>
                <input
                  className="campo mt-1.5"
                  placeholder="nome ou CNPJ"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                />
              </label>
              <label className="flex items-center gap-2 pb-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-erva"
                  checked={inativos}
                  onChange={(e) => setInativos(e.target.checked)}
                />
                <span className="text-[14px]">mostrar inativos</span>
              </label>
            </div>
          </Cartao>

          <Cartao titulo={lista ? `${lista.length} fornecedor(es)` : "Fornecedores"}>
            {!lista ? (
              <Carregando />
            ) : !lista.length ? (
              <Vazio>Nenhum fornecedor encontrado.</Vazio>
            ) : (
              <ul className="flex flex-col gap-px bg-linha">
                {lista.map((x) => (
                  <li
                    key={x.id}
                    className={`flex flex-wrap items-start justify-between gap-3 bg-superficie py-3 ${
                      x.ativo ? "" : "opacity-55"
                    }`}
                  >
                    <div className="min-w-0">
                      <button className="text-left" onClick={() => editar(x)}>
                        <span className="font-semibold hover:text-erva">{x.nome}</span>
                      </button>
                      <p className="mt-0.5 text-[13px] text-suave">
                        {x.cnpj ? mascaraCnpj(x.cnpj) : "sem CNPJ"}
                        {x.cidade ? ` · ${x.cidade}${x.uf ? "/" + x.uf : ""}` : ""}
                        {x.telefone ? ` · ${x.telefone}` : ""}
                      </p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {!!x.produtos && <Etiqueta cor="erva">{x.produtos} produto(s)</Etiqueta>}
                        {x.dias_entrega && <Etiqueta>entrega {x.dias_entrega}</Etiqueta>}
                        {x.pedido_minimo ? (
                          <Etiqueta>mínimo {reais(Number(x.pedido_minimo))}</Etiqueta>
                        ) : null}
                      </div>
                    </div>
                    {podeEditar && (
                      <button className="rotulo hover:text-erva" onClick={() => void alternar(x)}>
                        {x.ativo ? "desativar" : "reativar"}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Cartao>
        </div>

        {podeEditar && (
          <Cartao titulo={editando ? "Editar fornecedor" : "Novo fornecedor"}>
            <form onSubmit={salvar} className="flex flex-col gap-4">
              <Campo rotulo="Razão social / nome">
                <input
                  className="campo"
                  required
                  minLength={2}
                  value={f.nome}
                  onChange={(e) => setF({ ...f, nome: e.target.value })}
                />
              </Campo>
              <Campo rotulo="Nome fantasia">
                <input
                  className="campo"
                  value={f.nome_fantasia}
                  onChange={(e) => setF({ ...f, nome_fantasia: e.target.value })}
                />
              </Campo>
              <Campo rotulo="CNPJ" dica="usado para casar a nota do Omie">
                <input
                  className="campo mono"
                  placeholder="00.000.000/0000-00"
                  value={f.cnpj}
                  onChange={(e) => setF({ ...f, cnpj: mascaraCnpj(e.target.value) })}
                />
              </Campo>
              <div className="grid grid-cols-2 gap-4">
                <Campo rotulo="Contato">
                  <input
                    className="campo"
                    value={f.contato}
                    onChange={(e) => setF({ ...f, contato: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Telefone">
                  <input
                    className="campo"
                    value={f.telefone}
                    onChange={(e) => setF({ ...f, telefone: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="WhatsApp">
                  <input
                    className="campo"
                    value={f.whatsapp}
                    onChange={(e) => setF({ ...f, whatsapp: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="E-mail">
                  <input
                    className="campo"
                    type="email"
                    value={f.email}
                    onChange={(e) => setF({ ...f, email: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Cidade">
                  <input
                    className="campo"
                    value={f.cidade}
                    onChange={(e) => setF({ ...f, cidade: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="UF">
                  <input
                    className="campo"
                    maxLength={2}
                    value={f.uf}
                    onChange={(e) => setF({ ...f, uf: e.target.value.toUpperCase() })}
                  />
                </Campo>
                <Campo rotulo="Prazo (dias)">
                  <input
                    className="campo mono"
                    type="number"
                    min="0"
                    value={f.prazo_entrega_dias}
                    onChange={(e) => setF({ ...f, prazo_entrega_dias: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Dias de entrega" dica="seg,qua,sex">
                  <input
                    className="campo"
                    value={f.dias_entrega}
                    onChange={(e) => setF({ ...f, dias_entrega: e.target.value })}
                  />
                </Campo>
              </div>
              <Campo rotulo="Pedido mínimo (R$)">
                <input
                  className="campo mono"
                  type="number"
                  step="0.01"
                  min="0"
                  value={f.pedido_minimo}
                  onChange={(e) => setF({ ...f, pedido_minimo: e.target.value })}
                />
              </Campo>
              <Campo rotulo="Observação">
                <textarea
                  className="campo min-h-[70px]"
                  value={f.observacao}
                  onChange={(e) => setF({ ...f, observacao: e.target.value })}
                />
              </Campo>

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
        )}
      </div>
    </div>
  );
}
