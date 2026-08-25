"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";


type Inventario = {
  id: number;
  id_local: number;
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
  const aviso = useAviso();
  const router = useRouter();
  const { pode } = useSessao();

  const [lista, setLista] = useState<Inventario[] | null>(null);
  const [locais, setLocais] = useState<Local[]>([]);
  const [idLocal, setIdLocal] = useState("");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [cega, setCega] = useState(false);
  const pag = usePaginacao("inventarios");

  const carregar = useCallback(async () => {
    try {
      const [l, ls] = await Promise.all([
        api.listar<Inventario>(`/inventarios?${new URLSearchParams(pag.parametros)}`),
        api.get<Local[]>("/locais"),
      ]);
      setLista(l.itens);
      pag.setTotal(l.total);
      setLocais(ls);
      // Sem principal, vale o primeiro: uma casa com um local só não tem por
      // que marcar caixinha nenhuma, e o padrão vazio virava "Local não
      // encontrado" com o nome do local à vista no seletor.
      setIdLocal((atual) =>
        atual || String(ls.find((x) => x.principal)?.id ?? ls[0]?.id ?? ""));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.offset, pag.porPagina]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function abrirInventario() {
    setOcupado(true);
    setErro("");
    try {
      const inv = await api.post<Inventario>("/inventarios", {
        id_local: Number(idLocal),
        cega,
      });
      // Abrir uma contagem é o começo de CONTAR: leva direto para a tela de
      // contagem, em vez de devolver a pessoa à lista para clicar de novo.
      router.push(`/inventario/${inv.id}`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível abrir");
    } finally {
      setOcupado(false);
    }
  }




  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Estoque</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Inventário</h1>
        <p className="mt-1 max-w-[66ch] text-suave">
          Contar o que existe e acertar o razão pela diferença. A contagem não mexe em nada até
          você fechar — e o acerto entra como movimento, com nome e rastro.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {pode("estoque.inventario") && (
        <Cartao titulo="Nova contagem">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Campo rotulo="Local" className="sm:w-[260px]">
              <select
                className="campo"
                value={idLocal}
                onChange={(e) => setIdLocal(e.target.value)}
              >
                {!locais.length && <option value="">nenhum local cadastrado</option>}
                {locais.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.nome}
                  </option>
                ))}
              </select>
            </Campo>
            {/* Contagem cega: quem conta não vê o esperado. Ver o número
                transforma a contagem em conferência — a pessoa lê 12, olha a
                prateleira e escreve 12. */}
            <label className="flex items-start gap-2 pb-1 sm:max-w-[320px]">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 accent-erva"
                checked={cega}
                onChange={(e) => setCega(e.target.checked)}
              />
              <span className="text-[14px] leading-snug">
                contagem cega
                <span className="block text-[12.5px] text-suave">
                  esconde o saldo do sistema até a contagem fechar
                </span>
              </span>
            </label>
            <button
              className="btn btn-primario"
              onClick={abrirInventario}
              disabled={ocupado || !idLocal}
            >
              Abrir inventário
            </button>
          </div>
        </Cartao>
      )}

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
                <Link href={`/inventario/${i.id}`} className="text-left">
                  <span className="font-semibold hover:text-erva">
                    #{i.id} · {i.local}
                  </span>
                  <span className="block text-[13px] text-suave">
                    {new Date(i.data).toLocaleDateString("pt-BR")} · {i.contados} de{" "}
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
