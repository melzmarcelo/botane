"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Aviso, Campo, Cartao, Etiqueta, Vazio } from "@/components/ui";

/**
 * Buscar notas no Omie e conferir se não ficou nenhuma para trás.
 *
 * A busca comum **não pede período**: a janela vai desde a última
 * sincronização, com folga. Pedir "quantos dias" a cada vez transferia para
 * quem usa uma decisão que o sistema tem como tomar sozinho.
 *
 * O que sobra para a pessoa são as duas perguntas que o sistema não pode
 * responder: **de quando trazer o histórico** (uma vez, na implantação) e
 * **o que o Omie tem que aqui não tem** — porque "0 novas" é ambíguo, e essa
 * ambiguidade some quando a tela mostra o número da nota que falta.
 */

type Resultado = { novas: number; repetidas: number; janela: string; modo: string };

type Faltando = {
  chave_nfe: string | null;
  numero: string | null;
  emitente: string | null;
  data: string | null;
  valor_total: number;
};

type Conferencia = {
  inicio: string;
  fim: string;
  no_omie: number;
  aqui: number;
  faltando: Faltando[];
  so_aqui: { numero: string | null; emitente: string | null; status: string }[];
};

const hoje = () => new Date().toISOString().slice(0, 10);
const mesPassado = () => {
  const d = new Date();
  d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 10);
};
const dataBr = (d: string | null) =>
  d ? new Date(d.slice(0, 10) + "T00:00").toLocaleDateString("pt-BR") : "—";

export default function NotasOmie() {
  const [ocupado, setOcupado] = useState("");
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");
  const [desde, setDesde] = useState("");
  const [inicio, setInicio] = useState(mesPassado);
  const [fim, setFim] = useState(hoje);
  const [conf, setConf] = useState<Conferencia | null>(null);

  async function buscar(caminho: string, oQue: string) {
    setOcupado(oQue);
    setErro("");
    setOk("");
    try {
      const r = await api.post<Resultado & { message: string }>(caminho);
      setOk(r.message);
      // Depois de buscar, a conferência aberta na tela está velha.
      if (conf) await conferir();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível buscar");
    } finally {
      setOcupado("");
    }
  }

  async function conferir() {
    setOcupado("conferencia");
    setErro("");
    try {
      setConf(await api.get<Conferencia>(`/omie/conferencia-notas?inicio=${inicio}&fim=${fim}`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível conferir");
    } finally {
      setOcupado("");
    }
  }

  return (
    <Cartao
      titulo="Notas de entrada do Omie"
      descricao="A busca comum vai desde a última vez, com folga — não precisa escolher período."
      acao={
        <button
          className="btn btn-primario"
          disabled={!!ocupado}
          onClick={() => buscar("/omie/sincronizar", "busca")}
        >
          {ocupado === "busca" ? "Buscando…" : "Buscar notas novas"}
        </button>
      }
    >
      {erro && (
        <div className="mb-4">
          <Aviso tipo="erro">{erro}</Aviso>
        </div>
      )}
      {ok && (
        <div className="mb-4">
          <Aviso tipo="ok">{ok}</Aviso>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <p className="rotulo">Trazer o histórico</p>
          <p className="mt-1 text-[13.5px] leading-snug text-suave">
            Uma vez, na implantação: escolha de quando o Omie deve ser varrido. As notas que
            já existirem aqui são reconhecidas pela chave e não entram de novo.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <Campo rotulo="Desde" className="w-[170px]">
              <input
                className="campo"
                type="date"
                value={desde}
                max={hoje()}
                onChange={(e) => setDesde(e.target.value)}
              />
            </Campo>
            <button
              className="btn btn-secundario"
              disabled={!desde || !!ocupado}
              onClick={() => buscar(`/omie/sincronizar?desde=${desde}`, "historico")}
            >
              {ocupado === "historico" ? "Buscando…" : "Buscar o histórico"}
            </button>
          </div>
        </div>

        <div>
          <p className="rotulo">Conferir o período</p>
          <p className="mt-1 text-[13.5px] leading-snug text-suave">
            Compara o que o Omie tem com o que existe aqui e diz <b>quais</b> notas faltam —
            &ldquo;0 novas&rdquo; sozinho não distingue &ldquo;nada mudou&rdquo; de &ldquo;passou
            batido&rdquo;.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <Campo rotulo="De" className="w-[150px]">
              <input
                className="campo"
                type="date"
                value={inicio}
                onChange={(e) => setInicio(e.target.value)}
              />
            </Campo>
            <Campo rotulo="Até" className="w-[150px]">
              <input
                className="campo"
                type="date"
                value={fim}
                onChange={(e) => setFim(e.target.value)}
              />
            </Campo>
            <button className="btn btn-secundario" disabled={!!ocupado} onClick={conferir}>
              {ocupado === "conferencia" ? "Conferindo…" : "Conferir"}
            </button>
          </div>
        </div>
      </div>

      {conf && (
        <div className="mt-6 border-t border-linha pt-5">
          <p className="text-[14.5px]">
            No Omie: <b className="mono">{conf.no_omie}</b> · aqui:{" "}
            <b className="mono">{conf.aqui}</b>
            {conf.faltando.length > 0 ? (
              <>
                {" "}
                · <Etiqueta cor="alerta">{conf.faltando.length} faltando</Etiqueta>
              </>
            ) : (
              <span className="text-suave"> — nada ficou para trás no período.</span>
            )}
          </p>

          {!!conf.faltando.length && (
            <>
              <div className="mt-3 overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Nota</th>
                      <th>Emitente</th>
                      <th>Data</th>
                      <th className="num">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conf.faltando.map((f, i) => (
                      <tr key={f.chave_nfe ?? i}>
                        <td className="mono">NF {f.numero ?? "—"}</td>
                        <td>{f.emitente ?? "—"}</td>
                        <td className="mono text-[13px]">{dataBr(f.data)}</td>
                        <td className="num mono">{reais(Number(f.valor_total))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button
                className="btn btn-primario mt-3"
                disabled={!!ocupado}
                onClick={() => buscar(`/omie/sincronizar?desde=${conf.inicio}`, "faltantes")}
              >
                {ocupado === "faltantes" ? "Buscando…" : "Trazer as que faltam"}
              </button>
            </>
          )}

          {!!conf.so_aqui.length && (
            <p className="mt-4 text-[13.5px] text-suave">
              {conf.so_aqui.length} nota(s) existem aqui e não vieram na lista do Omie — quase
              sempre é nota cancelada lá depois de ter sido importada.
            </p>
          )}
          {!conf.faltando.length && !conf.so_aqui.length && conf.no_omie === 0 && (
            <Vazio>O Omie não tem nota de entrada neste período.</Vazio>
          )}
        </div>
      )}
    </Cartao>
  );
}
