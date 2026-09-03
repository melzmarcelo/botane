"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Etiqueta, Modal, Vazio } from "@/components/ui";

/**
 * Quanto este produto custa hoje — e o que mudou isso.
 *
 * 🔑 **O número não tinha onde ser consultado** (pedido do dono, 03/09/2026).
 * Ele já alimentava ficha, CMV teórico e margem, mas nenhuma tela o mostrava:
 * para saber quanto custava um insumo era preciso abrir uma ficha que o usasse.
 *
 * 🔑 **E a "Memória de cálculo" ao lado não cobre este caso.** Ela explica o
 * custo MÉDIO, que nasce de movimento — numa casa que acabou de importar o
 * catálogo e ainda não lançou nota, ela sai vazia, enquanto o custo de
 * referência responde pela cascata sem aparecer em lugar nenhum. Foi
 * exatamente o que aconteceu depois da carga do Omie.
 *
 * ⚠️ **A ORIGEM vem junto do valor, sempre.** "R$ 20,03" sem dizer de onde
 * veio não responde à pergunta que se faz em seguida — se é o que a casa pagou,
 * o que o fornecedor cobra ou o que outro sistema acha. As três coisas são
 * diferentes e valem diferente.
 */

type Linha = {
  fonte: "movimento" | "fornecedor" | "referencia";
  quando: string | null;
  custo: number;
  custo_do_documento: number | null;
  anterior: number | null;
  quantidade: number | null;
  saldo_apos: number | null;
  detalhe: string;
  documento: string | null;
  local: string | null;
  provisorio: boolean;
};

type Custo = {
  atual: number | null;
  origem: string;
  origem_texto: string;
  linhas: Linha[];
};

/** ⚠️ Sem `new Date(iso)` para data pura: ele lê `aaaa-mm-dd` como meia-noite
    UTC, que em Brasília é o dia anterior a partir das 21h. Data com hora já vem
    com fuso e pode ir pelo construtor. */
function quando(iso: string | null) {
  if (!iso) return "—";
  if (iso.length <= 10) {
    const [a, m, d] = iso.split("-");
    return `${d}/${m}/${a}`;
  }
  return new Date(iso).toLocaleDateString("pt-BR");
}

const FONTES: Record<Linha["fonte"], { rotulo: string; cor: "erva" | "neutro" | "alerta" }> = {
  movimento: { rotulo: "razão", cor: "erva" },
  fornecedor: { rotulo: "fornecedor", cor: "neutro" },
  referencia: { rotulo: "referência", cor: "alerta" },
};

export default function CustoDoProduto({ idProduto, um }: { idProduto: number; um: string | null }) {
  const [c, setC] = useState<Custo | null>(null);
  const [erro, setErro] = useState("");
  const [aberto, setAberto] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setC(await api.get<Custo>(`/produtos/${idProduto}/custo`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao consultar o custo");
    }
  }, [idProduto]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!c) return <Carregando />;

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Custo de {um || "uma unidade"}</p>
          <p className="mono mt-1 text-[26px] font-bold leading-none">
            {/* ⚠️ **Sem custo é "—", nunca R$ 0,00.** Zero é uma afirmação:
                diz que o produto não custa nada, e é justamente o número que
                faz o food cost sair bom demais sem ninguém desconfiar. */}
            {c.atual === null ? "—" : reais(c.atual)}
          </p>
          <p className="mt-1.5 text-[13px] text-suave">
            {c.atual === null
              ? "Ninguém sabe quanto custa: não há entrada no estoque, preço de fornecedor nem referência."
              : c.origem_texto}
          </p>
        </div>
        <button type="button" className="btn btn-secundario" onClick={() => setAberto(true)}>
          Histórico
        </button>
      </div>

      {/* ⚠️ **A referência é o degrau mais fraco, e a tela diz isso.** O médio
          do razão é o que a casa pagou, com frete dentro; o preço do fornecedor
          é o que ela negociou; a referência é o que outro sistema acha. Sem o
          aviso, os três aparecem com a mesma cara de número apurado. */}
      {c.origem === "referencia" && (
        <div className="mt-3">
          <Aviso tipo="info">
            Este custo veio de fora e vale enquanto não houver melhor: assim que entrar a
            primeira nota deste produto, o custo médio do estoque passa a responder no lugar
            dele.
          </Aviso>
        </div>
      )}

      {aberto && (
        <Modal
          titulo="Histórico de custo"
          descricao="Cada linha diz de onde o número veio — as três fontes valem diferente."
          aoFechar={() => setAberto(false)}
          largura="820px"
        >
          {!c.linhas.length ? (
            <Vazio>
              Nada registrou custo para este produto ainda — nem entrada no estoque, nem preço
              de fornecedor, nem referência trazida de fora.
            </Vazio>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Quando</th>
                      <th>Fonte</th>
                      <th>O que aconteceu</th>
                      <th className="num">Custo depois</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.linhas.map((l, i) => (
                      <tr key={`${l.fonte}-${i}`}>
                        <td className="mono whitespace-nowrap">{quando(l.quando)}</td>
                        <td>
                          <Etiqueta cor={FONTES[l.fonte].cor}>{FONTES[l.fonte].rotulo}</Etiqueta>
                        </td>
                        <td>
                          {l.detalhe}
                          {l.documento && <span className="mono text-suave"> · {l.documento}</span>}
                          {l.local && <span className="text-suave"> · {l.local}</span>}
                          {/* ⚠️ Entrada sem nota lançada: o número vale, mas
                              muda quando a nota chegar. Esconder isso faria a
                              linha parecer definitiva. */}
                          {l.provisorio && (
                            <span className="ml-2">
                              <Etiqueta cor="alerta">provisório</Etiqueta>
                            </span>
                          )}
                          {/* A conta que produziu o médio, quando houve uma:
                              é o que separa "o número apareceu" de "o número
                              se confere". */}
                          {l.fonte === "movimento" && l.custo_do_documento !== null && (
                            <span className="block text-[12.5px] text-suave">
                              {l.quantidade?.toLocaleString("pt-BR")} {um ?? ""} a{" "}
                              {reais(l.custo_do_documento)}
                              {l.anterior !== null && ` · antes ${reais(l.anterior)}`}
                              {l.saldo_apos !== null &&
                                ` · saldo ${l.saldo_apos.toLocaleString("pt-BR")}`}
                            </span>
                          )}
                        </td>
                        <td className="num mono">{reais(l.custo)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* 🔑 A distinção que evita a leitura errada da tabela acima. */}
              <p className="mt-4 text-[12.5px] leading-snug text-suave">
                Só o <b>razão</b> é uma linha do tempo: cada movimento guarda o custo médio
                depois dele. <b>Fornecedor</b> e <b>referência</b> guardam apenas o valor
                corrente e a data em que ele foi gravado — o sistema não tem os anteriores.
              </p>
            </>
          )}
        </Modal>
      )}
    </>
  );
}
