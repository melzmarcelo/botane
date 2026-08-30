"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useSessao } from "@/lib/sessao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";


type Inventario = {
  id: number;
  nome: string | null;
  /** Nulo quando a contagem cobre mais de um local. */
  id_local: number | null;
  local: string;
  data: string;
  status: string;
  observacao: string | null;
  cega?: boolean;
  contados: number;
  total_itens: number;
  diferenca_valor?: number | null;
};

export default function PaginaInventario() {
  const { pode } = useSessao();

  const [lista, setLista] = useState<Inventario[] | null>(null);
  const [erro, setErro] = useState("");
  const pag = usePaginacao("inventarios");

  const carregar = useCallback(async () => {
    try {
      const l = await api.listar<Inventario>(
        `/inventarios?${new URLSearchParams(pag.parametros)}`);
      setLista(l.itens);
      pag.setTotal(l.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.offset, pag.porPagina]);

  useEffect(() => {
    void carregar();
  }, [carregar]);


  return (
    <div className="flex flex-col gap-6">
      {/* ⚠️ Montar a contagem virou tela própria. O formulário morava aqui em
          cima e empurrava as contagens para fora do campo de visão — e com
          quatro filtros e a prévia ele não caberia de jeito nenhum. Aqui se
          consulta; em `/inventario/novo` se monta. É a mesma separação de
          Compras. */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="rotulo">Estoque</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Inventário
          </h1>
          <p className="mt-1 max-w-[66ch] text-suave">
            Contar o que existe e acertar o razão pela diferença. A contagem não mexe em nada
            até você fechar — e o acerto entra como movimento, com nome e rastro.
          </p>
        </div>
        {/* ⚠️ Montar a contagem é outra permissão. Quem só conta não vê o botão —
            e o servidor barra de qualquer jeito: aqui é dica de interface. */}
        {pode("estoque.inventario_criar") && (
          <Link href="/inventario/novo" className="btn btn-primario">
            Nova contagem
          </Link>
        )}
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao titulo="Contagens">
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>Nenhum inventário ainda.</Vazio>
        ) : (
          <ul className="flex flex-col gap-px bg-linha">
            {lista.map((i) => (
              <li
                key={i.id}
                className="flex flex-wrap items-center justify-between gap-3 bg-superficie py-3"
              >
                {/* ⚠️ O nome vem primeiro quando existe: numa lista de
                    contagens de recorte, "Estoque" repetido em todas não
                    distingue nada. Sem nome, `local` já traz o recorte por
                    extenso — quem monta a frase é o servidor. */}
                <Link href={`/inventario/${i.id}`} className="min-w-0 text-left">
                  <span className="link-registro">
                    #{i.id} · {i.nome || i.local}
                  </span>
                  <span className="block text-[13px] text-suave">
                    {new Date(i.data).toLocaleDateString("pt-BR")}
                    {i.nome && i.local !== i.nome ? ` · ${i.local}` : ""} · {i.contados} de{" "}
                    {i.total_itens} contado(s)
                  </span>
                </Link>
                <span className="flex flex-wrap items-center gap-1.5">
                  {i.cega && <Etiqueta>cega</Etiqueta>}
                  <Etiqueta cor={i.status === "ABERTO" ? "alerta" : "erva"}>
                    {i.status.toLowerCase()}
                  </Etiqueta>
                </span>
              </li>
            ))}
          </ul>
        )}
        <Paginacao p={pag} rotulo="inventário(s)" />
      </Cartao>
    </div>
  );
}
