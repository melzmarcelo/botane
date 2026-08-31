"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";

/**
 * As lojas da casa — só a lista.
 *
 * 🔑 **Consultar e cadastrar são telas diferentes.** Esta tela juntava a lista,
 * a seleção por clique na linha e o formulão de parâmetros embaixo; e não tinha
 * cadastro nenhum — nem botão de nova loja, nem endereço, nem CNPJ. O sistema
 * sabia criar loja pela API e não oferecia isso a ninguém, o que é o mesmo que
 * não saber. Mesmo corte de Compras, Vendas, Fornecedores e Usuários.
 */

type Loja = {
  id: number;
  nome: string;
  apelido: string | null;
  cnpj: string | null;
  matriz: boolean;
  cidade: string | null;
  uf: string | null;
  telefone: string | null;
  mesas: number | null;
  ativo: boolean;
};

export default function PaginaLojas() {
  const { pode } = useSessao();
  const podeEditar = pode("admin.unidades");
  const [lojas, setLojas] = useState<Loja[] | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api
      .get<Loja[]>("/unidades?incluir_inativas=true")
      .then(setLojas)
      // Erro de CARREGAMENTO fica inline: é ele que explica a tela vazia.
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="rotulo">Administração</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Lojas</h1>
          <p className="mt-1 max-w-[68ch] text-suave">
            Cada loja tem CNPJ, endereço, estoque e integrações próprios. Todo movimento nasce
            carimbado com ela — razão, nota, venda, inventário e fechamento.
          </p>
        </div>
        {podeEditar && (
          <Link href="/lojas/nova" className="btn btn-primario">
            Nova loja
          </Link>
        )}
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao>
        {!lojas ? (
          <Carregando />
        ) : !lojas.length ? (
          <Vazio>Nenhuma loja cadastrada.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>CNPJ</th>
                  <th>Cidade</th>
                  <th>Mesas</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {lojas.map((l) => (
                  <tr key={l.id} className={l.ativo ? "" : "opacity-55"}>
                    <td>
                      {/* O NOME leva ao registro — no celular o hover não
                          existe, e sem a pista sublinhada o cartão parece
                          texto. */}
                      <Link href={`/lojas/${l.id}`} className="link-registro font-semibold">
                        {l.apelido || l.nome}
                      </Link>
                      {l.matriz && (
                        <span className="ml-2">
                          <Etiqueta cor="erva">matriz</Etiqueta>
                        </span>
                      )}
                    </td>
                    <td className="mono">{l.cnpj ?? "—"}</td>
                    <td>{l.cidade ? `${l.cidade}${l.uf ? "/" + l.uf : ""}` : "—"}</td>
                    <td className="mono">{l.mesas ?? "—"}</td>
                    <td>{l.ativo ? "ativa" : "inativa"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      {/* ⚠️ Onde ficam os parâmetros e as integrações precisa estar dito AQUI:
          eles saíram desta tela, e quem os procurava no lugar antigo concluiria
          que sumiram. */}
      <p className="max-w-[70ch] text-[13.5px] text-suave">
        Os parâmetros de operação — ritmo do fechamento, travas e alertas — ficam dentro de cada
        loja. As integrações com o PDV e o Omie são configuradas em{" "}
        <Link href="/integracoes">Integrações</Link>, sempre para a loja escolhida no seletor do
        topo.
      </p>
    </div>
  );
}
