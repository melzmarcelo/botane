"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Fornecedor, mascaraCnpj, reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

/**
 * A lista dos fornecedores — só a lista.
 *
 * ⚠️ **O cadastro saiu da coluna da direita.** Espremido em 360 px, o formulário
 * tinha treze campos em uma coluna só: quem cadastrava rolava a tela inteira
 * para chegar no botão, e a lista — que é o assunto da página — ficava empurrada
 * para o lado numa base com 817 fornecedores. Mesmo corte de Compras e de
 * Vendas: consultar e cadastrar são telas diferentes.
 */
export default function PaginaFornecedores() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeEditar = pode("cadastros.fornecedores");

  const [lista, setLista] = useState<Fornecedor[] | null>(null);
  const [busca, setBusca] = useState("");
  const [inativos, setInativos] = useState(false);
  const [erro, setErro] = useState("");
  const pag = usePaginacao("fornecedores", { filtros: [busca, inativos] });

  const carregar = useCallback(async () => {
    const q = new URLSearchParams(pag.parametros);
    if (busca.trim()) q.set("busca", busca.trim());
    if (inativos) q.set("incluir_inativos", "true");
    try {
      const r = await api.listar<Fornecedor>(`/fornecedores?${q}`);
      setLista(r.itens);
      pag.setTotal(r.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca, inativos, pag.offset, pag.porPagina]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

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
          <Link href="/fornecedores/novo" className="btn btn-primario">
            Novo fornecedor
          </Link>
        )}
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

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

      <Cartao titulo={lista ? `${pag.total ?? lista.length} fornecedor(es)` : "Fornecedores"}>
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
                <Link href={`/fornecedores/${x.id}`} className="min-w-0 text-left">
                  <span className="font-semibold hover:text-erva">{x.nome}</span>
                  <span className="mt-0.5 block text-[13px] text-suave">
                    {x.cnpj ? mascaraCnpj(x.cnpj) : "sem CNPJ"}
                    {x.cidade ? ` · ${x.cidade}${x.uf ? "/" + x.uf : ""}` : ""}
                    {x.telefone ? ` · ${x.telefone}` : ""}
                  </span>
                  <span className="mt-1.5 flex flex-wrap gap-1.5">
                    {!!x.produtos && <Etiqueta cor="erva">{x.produtos} produto(s)</Etiqueta>}
                    {x.dias_entrega && <Etiqueta>entrega {x.dias_entrega}</Etiqueta>}
                    {x.pedido_minimo ? (
                      <Etiqueta>mínimo {reais(Number(x.pedido_minimo))}</Etiqueta>
                    ) : null}
                  </span>
                </Link>
                {podeEditar && (
                  <button className="rotulo hover:text-erva" onClick={() => void alternar(x)}>
                    {x.ativo ? "desativar" : "reativar"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        <Paginacao p={pag} rotulo="fornecedor(es)" />
      </Cartao>
    </div>
  );
}
