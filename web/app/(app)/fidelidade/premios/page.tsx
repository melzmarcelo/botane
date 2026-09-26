"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import ExplicaTela from "@/components/explica-tela";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { entregarPremio, listarPremios, type Premio } from "@/lib/fidelidade";

/**
 * Fidelidade → Prêmios: o balcão confere o código e entrega.
 *
 * 🔑 O cliente mostra no celular o código do prêmio (o site o exibe no cartão). A
 * atendente digita aqui, confere o nome e entrega. O servidor recusa o que já foi
 * entregue, o vencido e o dia que não é de consumo — a tela só explica.
 * ⚠️ **Da rede inteira**: o cartão é um só, e o prêmio pode ser buscado em qualquer
 * loja que participa.
 */
const SITUACOES = [
  { v: "DISPONIVEL", r: "Disponíveis" },
  { v: "USADO", r: "Entregues" },
  { v: "VENCIDO", r: "Vencidos" },
  { v: "", r: "Todos" },
];

const COR = { DISPONIVEL: "erva", USADO: "neutro", VENCIDO: "alerta" } as const;
const ROTULO = { DISPONIVEL: "disponível", USADO: "entregue", VENCIDO: "vencido" };

/** A data de hoje no relógio de quem usa (AAAA-MM-DD) — sem `toISOString`, que é UTC. */
const hojeIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const data = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

function telefone(t: string) {
  const m = t.match(/^(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : t;
}

export default function PremiosDaFidelidade() {
  const aviso = useAviso();
  const [status, setStatus] = useEstadoNaUrl<string>("status", "DISPONIVEL");
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [lista, setLista] = useState<Premio[] | null>(null);
  const [erro, setErro] = useState("");
  const [entregando, setEntregando] = useState<Premio | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const pag = usePaginacao("premios-fidelidade", { filtros: [status, busca] });

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    try {
      const r = await listarPremios(pag.parametros, { status, busca });
      setLista(r.itens);
      pag.setTotal(r.total);
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar os prêmios");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, status, busca, pag.offset, pag.porPagina]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  async function entregar(p: Premio) {
    setOcupado(true);
    try {
      const r = await entregarPremio(p.codigo);
      aviso.sucesso(r.message);
      setEntregando(null);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível entregar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes · Fidelidade</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Prêmios</h1>
        <ExplicaTela>
          O cliente mostra o código do prêmio no celular. Busque pelo código, nome ou telefone,
          confira e entregue.
        </ExplicaTela>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1">
            <span className="rotulo-campo">Buscar</span>
            <input
              className="campo mt-1.5"
              placeholder="código, nome ou telefone"
              value={busca}
              autoFocus
              onChange={(e) => setBusca(e.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="situação">
            {SITUACOES.map((s) => (
              <button
                key={s.v}
                type="button"
                role="tab"
                aria-selected={status === s.v}
                className={`btn px-3 py-1.5 text-[13px] ${status === s.v ? "btn-primario" : "btn-secundario"}`}
                onClick={() => setStatus(s.v)}
              >
                {s.r}
              </button>
            ))}
          </div>
        </div>
      </Cartao>

      <Cartao titulo={lista ? `${pag.total ?? lista.length} prêmio(s)` : "Prêmios"}>
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>{busca ? "Nenhum prêmio com essa busca." : "Nenhum prêmio nesta situação."}</Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th className="w-[100px]">Código</th>
                  <th className="min-w-[180px]">Cliente</th>
                  <th className="min-w-[160px]">Prêmio</th>
                  <th className="num w-[100px]">Ganho em</th>
                  <th className="num w-[100px]">Vence</th>
                  <th className="w-[130px]">Consumo</th>
                  <th className="w-[150px]">Situação</th>
                  <th className="w-[100px]"></th>
                </tr>
              </thead>
              <tbody>
                {lista.map((p) => (
                  <tr key={p.id} className={p.status === "DISPONIVEL" ? "" : "text-suave"}>
                    <td className="mono font-semibold tracking-wider">{p.codigo}</td>
                    <td>
                      <span className="font-medium">{p.nome}</span>
                      <span className="mono block text-[12px] text-suave">{telefone(p.telefone)}</span>
                    </td>
                    <td>
                      {p.premio}
                      <span className="block text-[12px] text-suave">
                        {p.visitas} visitas{p.loja ? ` · ${p.loja}` : ""}
                      </span>
                    </td>
                    <td className="num mono">{data(p.emitido_em)}</td>
                    <td className="num mono">{data(p.vence_em)}</td>
                    <td className="text-[13px]">{p.consumo}</td>
                    <td>
                      <Etiqueta cor={COR[p.status]}>{ROTULO[p.status]}</Etiqueta>
                      {p.usado_em && (
                        <span className="block text-[12px] text-suave">
                          {data(p.usado_em)}
                          {p.loja_uso ? ` · ${p.loja_uso}` : ""}
                          {p.entregue_por ? ` · ${p.entregue_por}` : ""}
                        </span>
                      )}
                    </td>
                    <td>
                      {p.status === "DISPONIVEL" &&
                        (p.pode_hoje ? (
                          <button className="btn btn-primario px-3 py-1 text-[13px]"
                                  onClick={() => setEntregando(p)}>
                            Entregar
                          </button>
                        ) : (
                          <span className="text-[12px] text-suave">
                            {/* 🔑 "No próximo é grátis": o prêmio completado hoje só vale
                                amanhã. É o motivo mais comum de não poder entregar. */}
                            {p.vale_de > hojeIso()
                              ? `vale a partir de ${data(p.vale_de)}`
                              : "hoje não é dia de consumo"}
                          </span>
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Paginacao p={pag} rotulo="prêmio(s)" />
      </Cartao>

      {entregando && (
        <Confirmacao
          titulo="Entregar este prêmio?"
          rotuloConfirmar="Sim, entregar"
          ocupado={ocupado}
          aoConfirmar={() => void entregar(entregando)}
          aoCancelar={() => setEntregando(null)}
        >
          <p>
            <b>{entregando.premio}</b> para <b>{entregando.nome}</b> — código{" "}
            <span className="mono font-semibold">{entregando.codigo}</span>.
          </p>
          <p className="mt-2 text-suave">
            Confira o código no celular do cliente. Depois de entregue, o prêmio não vale de novo.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
