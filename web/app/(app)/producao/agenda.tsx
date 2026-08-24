"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import BuscaCadastro from "@/components/busca-cadastro";
import { fonteDaLista, ItemBusca } from "@/lib/busca-cadastro";

/**
 * A agenda de produção — o PLANO, que é diferente do que já aconteceu.
 *
 * Registrar produção diz que ela foi feita. Aqui fica o passo anterior:
 * "amanhã a gente faz 20 kg de massa". É onde a cozinha se organiza e onde o
 * estoque mínimo vira decisão em vez de susto no meio do serviço.
 *
 * A agenda **não mexe no estoque**. Quem mexe é a produção, quando a linha é
 * cumprida — e aí a quantidade pode sair diferente da planejada, porque o que
 * vale é o que saiu do fogão.
 */

type Ficha = {
  id: number;
  id_produto: number;
  produto: string;
  versao: number;
  status: string;
  rendimento_um: string | null;
};

type Linha = {
  id: number;
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  data_prevista: string;
  quantidade: number;
  status: string;
  origem: string;
  observacao: string | null;
  local: string | null;
  saldo_atual: number;
  estoque_minimo: number | null;
  atrasada: boolean;
  criado_por: string | null;
  produzido_por: string | null;
};

type Sugestao = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  estoque_minimo: number;
  saldo: number;
  sugerido: number;
};

type Resposta = {
  linhas: Linha[];
  resumo: { hoje: number; atrasadas: number; proximas: number; sugestoes: number };
  sugestoes: Sugestao[];
};

const qtd = (n: number | string) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

const dia = (d: string) => new Date(d + "T12:00").toLocaleDateString("pt-BR");

function amanha() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

export default function AgendaProducao({
  fichas,
  locais,
  aoProduzir,
}: {
  fichas: Ficha[];
  locais: Local[];
  aoProduzir: () => void;
}) {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeProduzir = pode("estoque.saidas");

  const [dados, setDados] = useState<Resposta | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [f, setF] = useState({ id_produto: "", quantidade: "", data: amanha(), rotulo: "" });

  const carregar = useCallback(async () => {
    try {
      setDados(await api.get<Resposta>("/producao-agenda"));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // Só entra na agenda o que se produz PARA ESTOQUE — o feito na hora nasce e
  // morre na venda, e o servidor recusa agendá-lo.
  const fonteReceitas = useMemo(
    () =>
      fonteDaLista(
        "Buscar receita",
        "receita",
        fichas.map((x) => ({
          id: x.id_produto,
          codigo: null,
          nome: x.produto,
          detalhe: `ficha v${x.versao}`,
        })),
        "nome do prato",
      ),
    [fichas],
  );

  async function agendar(e: FormEvent) {
    e.preventDefault();
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>("/producao-agenda", {
        id_produto: Number(f.id_produto),
        quantidade: Number(f.quantidade.replace(",", ".")),
        data_prevista: f.data,
      });
      aviso.sucesso(r.message);
      setF({ id_produto: "", quantidade: "", data: f.data, rotulo: "" });
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível agendar");
    } finally {
      setOcupado(false);
    }
  }

  async function produzirLinha(l: Linha) {
    const texto = window.prompt(
      `Quanto saiu de fato de ${l.produto}?\n(planejado: ${qtd(l.quantidade)} ${l.um_estoque ?? ""})`,
      String(Number(l.quantidade)),
    );
    if (texto === null) return;
    const valor = Number(texto.replace(",", "."));
    if (!valor || valor <= 0) {
      aviso.erro("Quantidade tem de ser maior que zero.");
      return;
    }
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/producao-agenda/${l.id}/produzir`, {
        quantidade: valor,
      });
      aviso.sucesso(r.message);
      await carregar();
      aoProduzir();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível produzir");
    } finally {
      setOcupado(false);
    }
  }

  async function cancelar(l: Linha) {
    setOcupado(true);
    try {
      await api.delete(`/producao-agenda/${l.id}`);
      aviso.sucesso(`${l.produto} saiu da agenda de ${dia(l.data_prevista)}.`);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível cancelar");
    } finally {
      setOcupado(false);
    }
  }

  async function agendarSugestoes() {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>("/producao-agenda/das-sugestoes");
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível agendar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  const porDia = dados.linhas.reduce<Record<string, Linha[]>>((mapa, l) => {
    (mapa[l.data_prevista] ??= []).push(l);
    return mapa;
  }, {});
  const hoje = new Date().toISOString().slice(0, 10);

  return (
    <div className="flex flex-col gap-6">
      {/* O alerta diz "vai faltar" e para por aí. Este cartão é o que
          transforma o aviso em plano — o passo que costuma não acontecer. */}
      {!!dados.sugestoes.length && (
        <Cartao
          titulo="Vai faltar, e a casa produz"
          descricao="Abaixo do mínimo, com ficha homologada e sem nada marcado na agenda."
          acao={
            <button
              className="btn btn-primario"
              onClick={() => void agendarSugestoes()}
              disabled={ocupado}
            >
              Pôr todas na agenda de amanhã
            </button>
          }
        >
          <ul className="flex flex-col gap-px bg-linha">
            {dados.sugestoes.map((s) => (
              <li
                key={s.id_produto}
                className="flex flex-wrap items-center justify-between gap-3 bg-superficie py-2.5"
              >
                <span>
                  <span className="font-medium">{s.produto}</span>
                  <span className="block text-[12.5px] text-suave">
                    tem {qtd(s.saldo)} {s.um_estoque} · mínimo {qtd(s.estoque_minimo)}
                  </span>
                </span>
                <span className="mono text-[14px] text-erva">
                  produzir {qtd(s.sugerido)} {s.um_estoque}
                </span>
              </li>
            ))}
          </ul>
        </Cartao>
      )}

      <Cartao
        titulo="Agendar produção"
        descricao="O plano não mexe no estoque — quem mexe é a produção, quando a linha for cumprida."
      >
        <form onSubmit={agendar} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Campo rotulo="O que produzir" className="sm:col-span-2">
            <BuscaCadastro
              fonte={fonteReceitas}
              required
              selecionado={
                f.id_produto ? { id: Number(f.id_produto), rotulo: f.rotulo } : null
              }
              aoEscolher={(item: ItemBusca | null) =>
                setF({
                  ...f,
                  id_produto: item ? String(item.id) : "",
                  rotulo: item?.nome ?? "",
                })
              }
            />
          </Campo>
          <Campo rotulo="Quantidade">
            <input
              className="campo mono"
              inputMode="decimal"
              required
              value={f.quantidade}
              onChange={(e) => setF({ ...f, quantidade: e.target.value })}
            />
          </Campo>
          <Campo rotulo="Para quando">
            <input
              className="campo"
              type="date"
              required
              value={f.data}
              onChange={(e) => setF({ ...f, data: e.target.value })}
            />
          </Campo>
          <div className="flex items-end">
            <button className="btn btn-primario" type="submit" disabled={ocupado}>
              {ocupado ? "Agendando…" : "Pôr na agenda"}
            </button>
          </div>
        </form>
      </Cartao>

      <Cartao
        titulo="O que está marcado"
        descricao={
          dados.resumo.atrasadas
            ? `${dados.resumo.atrasadas} linha(s) do passado ainda esperando — ou se produz, ou se cancela.`
            : "Do que ficou para trás até o que vem."
        }
      >
        {!dados.linhas.length ? (
          <Vazio>Nada agendado. A cozinha decide o dia, não a véspera.</Vazio>
        ) : (
          <div className="flex flex-col gap-5">
            {Object.entries(porDia).map(([data, linhas]) => (
              <div key={data}>
                <p className="rotulo mb-2">
                  {data === hoje ? "hoje" : dia(data)}
                  {data < hoje && <span className="text-erro"> · atrasado</span>}
                </p>
                <ul className="flex flex-col gap-px bg-linha">
                  {linhas.map((l) => (
                    <li
                      key={l.id}
                      className="flex flex-wrap items-center justify-between gap-3 bg-superficie py-3"
                    >
                      <span className="min-w-0">
                        <span className="font-medium">{l.produto}</span>
                        <span className="mono ml-2 text-[13px] text-erva">
                          {qtd(l.quantidade)} {l.um_estoque}
                        </span>
                        <span className="block text-[12.5px] text-suave">
                          tem {qtd(l.saldo_atual)} {l.um_estoque} em estoque
                          {l.estoque_minimo !== null && ` · mínimo ${qtd(l.estoque_minimo)}`}
                          {l.origem === "ALERTA" && " · veio do alerta"}
                        </span>
                      </span>
                      <span className="flex flex-wrap items-center gap-3">
                        {l.atrasada && <Etiqueta cor="alerta">atrasada</Etiqueta>}
                        {podeProduzir && (
                          <button
                            className="btn btn-secundario"
                            onClick={() => void produzirLinha(l)}
                            disabled={ocupado}
                          >
                            Produzir
                          </button>
                        )}
                        <button
                          className="rotulo hover:text-erro"
                          onClick={() => void cancelar(l)}
                          disabled={ocupado}
                        >
                          cancelar
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Cartao>
    </div>
  );
}
