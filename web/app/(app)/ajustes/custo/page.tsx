"use client";

/**
 * Ajuste de custo — corrigir o custo médio de vários produtos de uma vez.
 *
 * Tela própria, e não uma aba de Ajustes, porque é outro processo: ajustar
 * quantidade é dizer que a prateleira tem outra coisa; ajustar custo é dizer
 * que o dinheiro é outro. Permissão própria (`estoque.custo`).
 *
 * ⚠️ **A prévia vem antes do botão.** O ajuste entra no razão e só sai por
 * estorno; quem confirma precisa ver a diferença em REAIS — não em custo
 * unitário, que é onde o erro de casa decimal se esconde.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { Aviso, Campo, Cartao, Confirmacao } from "@/components/ui";
import { api, ErroApi } from "@/lib/api";
import { fonteProdutos } from "@/lib/busca-cadastro";
import { Local, reais } from "@/lib/cadastros";
import { useSessao } from "@/lib/sessao";

type Linha = {
  chave: number;
  produto: { id: number; rotulo: string } | null;
  custo_novo: string;
};

type LinhaPrevia = {
  id_produto: number;
  produto: string;
  codigo: string;
  um: string | null;
  saldo: number;
  custo_atual: number;
  custo_novo: number;
  valor_atual: number;
  valor_novo: number;
  diferenca: number;
  efeito_no_cmv: number;
};

type Previa = { linhas: LinhaPrevia[]; diferenca_total: number; efeito_no_cmv: number };

let sequencia = 1;
const nova = (): Linha => ({ chave: sequencia++, produto: null, custo_novo: "" });

export default function PaginaAjusteCusto() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const [locais, setLocais] = useState<Local[]>([]);
  const [idLocal, setIdLocal] = useState<number | "">("");
  const [linhas, setLinhas] = useState<Linha[]>([nova()]);
  const [observacao, setObservacao] = useState("");
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  useEffect(() => {
    api
      .get<Local[]>("/locais")
      .then((l) => {
        setLocais(l);
        const principal = l.find((x) => x.principal) ?? l[0];
        if (principal) setIdLocal(principal.id);
      })
      .catch(() => setErro("Falha ao carregar os locais de estoque."));
  }, []);

  // ⚠️ Trocar qualquer coisa invalida a prévia. Sem isto, alguém mudaria o
  // custo depois de conferir e confirmaria um número que não é o que viu.
  const mudar = (fn: () => void) => {
    setPrevia(null);
    setErro("");
    fn();
  };

  const preenchidas = linhas.filter((l) => l.produto && l.custo_novo.trim() !== "");

  async function conferir() {
    if (!preenchidas.length) {
      setErro("Escolha ao menos um produto e informe o custo certo.");
      return;
    }
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<Previa>("/ajustes/custo/previa", {
        linhas: preenchidas.map((l) => ({
          id_produto: l.produto!.id,
          custo_novo: Number(l.custo_novo.replace(",", ".")),
          id_local: idLocal || null,
        })),
      });
      setPrevia(r);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível conferir.");
    } finally {
      setOcupado(false);
    }
  }

  async function lancar() {
    setOcupado(true);
    try {
      const r = await api.post<{ lancados: number; diferenca_total: number }>(
        "/ajustes/custo",
        {
          observacao: observacao.trim() || null,
          linhas: preenchidas.map((l) => ({
            id_produto: l.produto!.id,
            custo_novo: Number(l.custo_novo.replace(",", ".")),
            id_local: idLocal || null,
          })),
        },
      );
      aviso.sucesso(
        `${r.lancados} custo(s) corrigido(s) — ${reais(r.diferenca_total)} de diferença.`,
      );
      // Formulário limpo: quem corrige um lote corrige o próximo.
      setLinhas([nova()]);
      setObservacao("");
      setPrevia(null);
    } catch (e) {
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível lançar.");
    } finally {
      setOcupado(false);
    }
  }

  if (!pode("estoque.custo")) {
    return (
      <Cartao>
        <Aviso tipo="erro">
          Você não tem permissão para ajustar custo. Contar prateleira e decidir valor são
          coisas diferentes — fale com o administrador.
        </Aviso>
      </Cartao>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <Link href="/ajustes" className="link-voltar">
          ← Ajustes
        </Link>
        <h1 className="titulo mt-2">Ajuste de custo</h1>
        <p className="text-neutro-500 text-[14px] mt-1 max-w-[70ch]">
          Corrige o <b>custo médio</b> de produtos que já estão em estoque. A quantidade não
          muda — só quanto ela vale. Serve para o custo provisório de uma saída sem saldo,
          para o produto que entrou sem custo e para a nota digitada com o valor errado.
        </p>
      </div>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao>
        <div className="grid gap-4 sm:grid-cols-[220px_minmax(0,1fr)]">
          <Campo rotulo="Local de estoque">
            <select
              className="campo mt-1.5"
              value={idLocal}
              onChange={(e) => mudar(() => setIdLocal(Number(e.target.value) || ""))}
            >
              {locais.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nome}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Por que este ajuste">
            <input
              className="campo mt-1.5"
              placeholder="ex.: correção do custo provisório da entrada sem saldo"
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
            />
          </Campo>
        </div>

        <div className="rolagem mt-5 overflow-x-auto">
          <table className="w-full text-[14px]">
            <thead>
              <tr>
                <th className="rotulo text-left pb-2 min-w-[280px]">Produto</th>
                <th className="rotulo text-left pb-2 w-[150px] min-w-[150px]">
                  Custo certo
                </th>
                <th className="pb-2 w-[40px]"></th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((l, i) => (
                <tr key={l.chave} className="border-t border-linha">
                  <td className="py-2 pr-3">
                    <BuscaCadastro
                      fonte={fonteProdutos((p) => p.controla_estoque)}
                      selecionado={l.produto}
                      aoEscolher={(item) =>
                        mudar(() =>
                          setLinhas((ls) =>
                            ls.map((x, j) =>
                              j === i
                                ? {
                                    ...x,
                                    produto: item
                                      ? { id: item.id, rotulo: rotuloDe(item) }
                                      : null,
                                  }
                                : x,
                            ),
                          ),
                        )
                      }
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <input
                      className="campo"
                      inputMode="decimal"
                      placeholder="0,000000"
                      value={l.custo_novo}
                      onChange={(e) =>
                        mudar(() =>
                          setLinhas((ls) =>
                            ls.map((x, j) =>
                              j === i ? { ...x, custo_novo: e.target.value } : x,
                            ),
                          ),
                        )
                      }
                    />
                  </td>
                  <td className="py-2">
                    {linhas.length > 1 && (
                      <button
                        className="btn btn-texto"
                        title="Tirar esta linha"
                        onClick={() =>
                          mudar(() => setLinhas((ls) => ls.filter((_, j) => j !== i)))
                        }
                      >
                        ×
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap gap-2 mt-4">
          <button
            className="btn btn-secundario"
            onClick={() => mudar(() => setLinhas((ls) => [...ls, nova()]))}
          >
            + Outro produto
          </button>
          <button
            className="btn btn-primario"
            onClick={conferir}
            disabled={ocupado || !preenchidas.length}
          >
            {ocupado ? "Conferindo…" : "Conferir"}
          </button>
        </div>
      </Cartao>

      {previa && (
        <Cartao>
          <p className="rotulo">O que vai acontecer</p>
          <div className="overflow-x-auto mt-3">
            <table className="w-full text-[14px]">
              <thead>
                <tr>
                  <th className="rotulo text-left pb-2">Produto</th>
                  <th className="rotulo text-right pb-2">Saldo</th>
                  <th className="rotulo text-right pb-2">Custo hoje</th>
                  <th className="rotulo text-right pb-2">Custo novo</th>
                  <th className="rotulo text-right pb-2">Vale hoje</th>
                  <th className="rotulo text-right pb-2">Vai valer</th>
                  <th className="rotulo text-right pb-2">Diferença</th>
                </tr>
              </thead>
              <tbody>
                {previa.linhas.map((l) => (
                  <tr key={l.id_produto} className="border-t border-linha">
                    <td className="py-2">
                      {l.produto}
                      <span className="text-neutro-500 text-[12.5px]"> · {l.codigo}</span>
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {l.saldo} {l.um}
                    </td>
                    <td className="py-2 text-right tabular-nums">{l.custo_atual}</td>
                    <td className="py-2 text-right tabular-nums font-medium">
                      {l.custo_novo}
                    </td>
                    <td className="py-2 text-right tabular-nums">{reais(l.valor_atual)}</td>
                    <td className="py-2 text-right tabular-nums">{reais(l.valor_novo)}</td>
                    <td
                      className={`py-2 text-right tabular-nums font-medium ${
                        l.diferenca >= 0 ? "text-erva" : "text-erro"
                      }`}
                    >
                      {l.diferenca >= 0 ? "+" : ""}
                      {reais(l.diferenca)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/*
            ⚠️ O sinal é contraintuitivo e precisa estar escrito: subir o custo
            do estoque AUMENTA o estoque final, e o CMV é `inicial + compras −
            final`. Estoque mais caro, CMV menor. Quem confirma tem de ler isso
            ANTES — depois é estorno.
          */}
          <Aviso tipo="info">
            O estoque passa a valer{" "}
            <b>
              {previa.diferenca_total >= 0 ? "+" : ""}
              {reais(previa.diferenca_total)}
            </b>
            . Como o CMV é <span className="mono">inicial + compras − final</span>, isto{" "}
            {previa.efeito_no_cmv < 0 ? "REDUZ" : "AUMENTA"} o CMV do período em{" "}
            <b>{reais(Math.abs(previa.efeito_no_cmv))}</b>. O painel mostra a linha
            “Ajuste de custo” com esse valor.
          </Aviso>

          <div className="mt-4">
            <button
              className="btn btn-primario"
              onClick={() => setConfirmando(true)}
              disabled={ocupado}
            >
              Corrigir custo
            </button>
          </div>
        </Cartao>
      )}

      {/*
        ⚠️ Pergunta porque MEXE NO RAZÃO — é a regra da casa para o que não se
        desfaz. E diz o que a ação FAZ, com o número na frente, em vez de só
        "tem certeza".
      */}
      {confirmando && previa && (
        <Confirmacao
          titulo="Corrigir o custo médio?"
          rotuloConfirmar={ocupado ? "Lançando…" : "Corrigir custo"}
          ocupado={ocupado}
          aoCancelar={() => setConfirmando(false)}
          aoConfirmar={() => {
            setConfirmando(false);
            void lancar();
          }}
        >
          <p>
            <b>{previa.linhas.length} produto(s)</b> passam a valer{" "}
            <b>
              {previa.diferenca_total >= 0 ? "+" : ""}
              {reais(previa.diferenca_total)}
            </b>
            , e o CMV do período {previa.efeito_no_cmv < 0 ? "cai" : "sobe"}{" "}
            <b>{reais(Math.abs(previa.efeito_no_cmv))}</b>.
          </p>
          <p>
            O movimento entra no razão, que é somente-inclusão: desfazer é estornar, não
            apagar.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
