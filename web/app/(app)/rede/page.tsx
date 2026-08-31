"use client";

import { useCallback, useEffect, useState } from "react";

import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";

/**
 * As lojas lado a lado — o painel de quem responde pelas duas.
 *
 * 🔑 **Toda outra tela do sistema responde por UMA loja**, e está certo: quem
 * opera opera numa de cada vez. Mas o dono de duas não tinha onde ver as duas —
 * e somar de cabeça dois food costs de bases diferentes é a conta que ninguém
 * faz certo.
 *
 * ⚠️ **Os números saem da MESMA apuração de cada loja**, uma por vez, no
 * servidor — nunca de uma consulta nova que soma tudo. Se o total não bate com
 * o painel de uma delas, o erro está naquela loja, não entre elas.
 */

type Loja = {
  id_unidade: number;
  loja: string;
  matriz: boolean;
  periodo: { inicio: string; fim: string; rotulo: string; ciclo: string };
  estoque_agora: number;
  compras: number;
  cmv: number;
  perdas: number;
  receita: number;
  vendas: number;
  food_cost_pct: number | null;
  cobertura_ficha_pct: number;
};

type Rede = {
  lojas: Loja[];
  total: {
    estoque_agora: number;
    cmv: number;
    perdas: number;
    receita: number;
    food_cost_pct: number | null;
  };
};

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${v.toFixed(1).replace(".", ",")}%`;

export default function PaginaRede() {
  const [dados, setDados] = useState<Rede | null>(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    setErro("");
    try {
      setDados(await api.get<Rede>("/inicio/rede"));
    } catch (e) {
      // Erro de CARREGAMENTO fica inline: é ele que explica a tela vazia.
      setDados(null);
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const lojas = dados?.lojas ?? [];
  // Períodos diferentes entre as lojas é legítimo — uma pode fechar por semana e
  // a outra por mês —, mas o total precisa dizer isso em vez de somar calado.
  const periodosDiferentes =
    new Set(lojas.map((l) => `${l.periodo.inicio}|${l.periodo.fim}`)).size > 1;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">CMV</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
          Visão da rede
        </h1>
        <p className="mt-1 max-w-[68ch] text-suave">
          As lojas lado a lado, no período corrente de cada uma. Os números são os mesmos do
          painel de cada loja — esta tela não recalcula nada por conta própria.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!dados ? (
        <Carregando />
      ) : !lojas.length ? (
        <Vazio>Nenhuma loja para mostrar.</Vazio>
      ) : (
        <>
          {periodosDiferentes && (
            <Aviso tipo="info">
              As lojas fecham em ritmos diferentes, e cada linha traz o período dela. O total
              soma dinheiro de janelas que não são as mesmas — compare por loja antes de
              comparar o total.
            </Aviso>
          )}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {lojas.map((l) => (
              <Cartao key={l.id_unidade}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-[17px] font-bold tracking-tight">{l.loja}</span>
                  {l.matriz && <Etiqueta cor="erva">matriz</Etiqueta>}
                </div>
                <p className="rotulo mt-0.5">{l.periodo.rotulo}</p>

                <dl className="mt-3 flex flex-col gap-2 text-[14px]">
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-suave">CMV</dt>
                    <dd className="mono font-semibold">{reais(l.cmv)}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-suave">Receita</dt>
                    <dd className="mono">{reais(l.receita)}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-suave">Food cost</dt>
                    {/* ⚠️ Sem venda o percentual é NULO, não zero — zero ali
                        pareceria um resultado excelente. */}
                    <dd className={`mono font-semibold ${l.food_cost_pct === null ? "text-suave" : ""}`}>
                      {pct(l.food_cost_pct)}
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-3 border-t border-linha pt-2">
                    <dt className="text-suave">Estoque agora</dt>
                    <dd className="mono">{reais(l.estoque_agora)}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-suave">Perdas</dt>
                    <dd className="mono">{reais(l.perdas)}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-suave">Cobertura de ficha</dt>
                    <dd className="mono">{pct(l.cobertura_ficha_pct)}</dd>
                  </div>
                </dl>

                {l.food_cost_pct === null && (
                  <p className="mt-2 text-[12.5px] leading-snug text-suave">
                    Sem venda no período: food cost não é zero, é desconhecido.
                  </p>
                )}
              </Cartao>
            ))}
          </div>

          <Cartao titulo="A rede" descricao="A soma das lojas acima.">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["CMV", reais(dados.total.cmv)],
                ["Receita", reais(dados.total.receita)],
                ["Estoque agora", reais(dados.total.estoque_agora)],
                ["Perdas", reais(dados.total.perdas)],
              ].map(([rotulo, valor]) => (
                <div key={rotulo}>
                  <p className="rotulo">{rotulo}</p>
                  <p className="mono mt-1 text-[20px] font-bold">{valor}</p>
                </div>
              ))}
            </div>

            <div className="mt-4 border-t border-linha pt-3">
              <p className="rotulo">Food cost da rede</p>
              <p className="mono mt-1 text-[26px] font-bold">{pct(dados.total.food_cost_pct)}</p>
              {/* 🔑 A explicação fica na tela porque a conta NÃO é a média dos
                  percentuais acima, e quem confere com a calculadora vai achar
                  outro número se não souber disso. */}
              <p className="mt-1 max-w-[62ch] text-[12.5px] leading-snug text-suave">
                Calculado sobre o CMV e a receita somados — não é a média dos percentuais das
                lojas. Média daria o mesmo peso à loja que vendeu muito e à que vendeu pouco.
              </p>
            </div>
          </Cartao>
        </>
      )}
    </div>
  );
}
