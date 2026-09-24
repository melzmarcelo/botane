"use client";

import { useCallback, useEffect, useState } from "react";

import ExplicaTela from "@/components/explica-tela";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { listarClientes, type Cliente } from "@/lib/reservas";

/**
 * Os clientes cadastrados pelo site — o grid do Portal de Clientes.
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"dentro do Portal do Cliente, vamos criar o
 * menu e a página para listar os clientes cadastrados. Em grid paginado padrão do
 * sistema."* Paginação do SERVIDOR (`usePaginacao` + `X-Total`), busca na URL.
 *
 * ⚠️ **A rede inteira**, não a loja do seletor: desde a migração 087 o cadastro é
 * único por telefone. A coluna "Cadastro" diz em que loja ele nasceu.
 */

const GENERO: Record<string, string> = {
  FEMININO: "Feminino",
  MASCULINO: "Masculino",
  OUTRO: "Outro",
  NAO_INFORMADO: "Não informado",
};

/** "47999105033" → "(47) 99910-5033". O que não tiver 10 ou 11 dígitos sai como veio. */
function telefone(t: string) {
  const m = t.match(/^(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : t;
}

/** AAAA-MM-DD (ou ISO com hora) → DD/MM/AAAA. */
const data = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

export default function ClientesDoPortal() {
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [lista, setLista] = useState<Cliente[] | null>(null);
  const [erro, setErro] = useState("");
  const pag = usePaginacao("clientes-portal", { filtros: [busca] });

  const carregar = useCallback(async () => {
    // ⚠️ Espera a preferência de "por página": buscar antes dispara duas buscas
    // e a atrasada sobrescreve a certa (ver `usePaginacao`).
    if (!pag.pronto) return;
    try {
      const r = await listarClientes(pag.parametros, busca);
      setLista(r.itens);
      pag.setTotal(r.total);
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar os clientes");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, busca, pag.offset, pag.porPagina]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Clientes</h1>
        <ExplicaTela>
          Quem se cadastrou pelo site para reservar ou abrir um cardápio. O cadastro vale para
          todas as lojas: o telefone é único.
        </ExplicaTela>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao>
        <label className="block">
          <span className="rotulo-campo">Buscar</span>
          <input
            className="campo mt-1.5"
            placeholder="nome ou telefone"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </label>
      </Cartao>

      <Cartao titulo={lista ? `${pag.total ?? lista.length} cliente(s)` : "Clientes"}>
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>{busca ? "Nenhum cliente com essa busca." : "Nenhum cliente cadastrado ainda."}</Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th className="min-w-[200px]">Nome</th>
                  <th className="w-[140px]">Telefone</th>
                  <th className="min-w-[120px]">Cidade</th>
                  <th className="w-[120px]">Gênero</th>
                  <th className="num w-[110px]">Nascimento</th>
                  <th className="num w-[90px]">Reservas</th>
                  <th className="num w-[110px]">Última</th>
                  <th className="w-[110px]">Fidelidade</th>
                  <th className="w-[140px]">Cadastro</th>
                  <th className="w-[120px]">Termo</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((c) => (
                  <tr key={c.id}>
                    <td className="font-medium">{c.nome}</td>
                    <td className="mono">{telefone(c.telefone)}</td>
                    <td>{c.cidade || "—"}</td>
                    <td>{c.genero ? GENERO[c.genero] ?? c.genero : "—"}</td>
                    <td className="num mono">{data(c.nascimento)}</td>
                    <td className="num mono">
                      {c.reservas}
                      {/* Cancelada e não-comparecimento à parte: somar os dois
                          faria o cliente que nunca vem parecer o mais fiel. */}
                      {c.canceladas > 0 && (
                        <span className="block text-[11.5px] text-suave">
                          +{c.canceladas} canc.
                        </span>
                      )}
                    </td>
                    <td className="num mono">{data(c.ultima)}</td>
                    <td className="text-[13px]">
                      {c.no_cartao || c.premios ? (
                        <>
                          <span className="mono">{c.no_cartao}</span> visita(s)
                          {c.premios > 0 && (
                            <span className="block text-[12px] text-suave">
                              {c.premios} prêmio(s)
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-suave">—</span>
                      )}
                    </td>
                    <td>
                      <span className="mono">{data(c.criado_em)}</span>
                      {c.loja && <span className="block text-[12px] text-suave">{c.loja}</span>}
                    </td>
                    <td>
                      {/* ⚠️ Cadastro de antes de 24/09/2026 não viu termo nenhum:
                          "sem registro" é o fato, não uma pendência a esconder. */}
                      {c.termo_aceito_em ? (
                        <span title={`Versão ${c.termo_versao ?? "?"}`}>
                          <Etiqueta cor="erva">aceito</Etiqueta>
                          <span className="mono block text-[11.5px] text-suave">
                            {data(c.termo_aceito_em)}
                          </span>
                        </span>
                      ) : (
                        <span className="text-[12.5px] text-suave">sem registro</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Paginacao p={pag} rotulo="cliente(s)" />
      </Cartao>
    </div>
  );
}
