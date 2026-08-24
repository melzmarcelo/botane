"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import {
  Aviso,
  Carregando,
  Cartao,
  Confirmacao,
  Etiqueta,
  Vazio,
} from "@/components/ui";

/**
 * A folha da produção: o que vai ser preciso para fazer aquilo.
 *
 * A linha da agenda diz "22 massas". Quem vai para a bancada precisa da outra
 * metade: quanto de cada insumo isso consome, quanto disso existe no local de
 * onde vai sair, e o que falta. Sem essa folha, a pessoa descobre que acabou a
 * farinha depois de ligar o forno.
 *
 * ⚠️ A previsão é sempre de AGORA, nunca a de quando se agendou: o estoque
 * mudou desde então, e é o de agora que diz se dá para produzir.
 */

type ItemPrevisto = {
  id_produto: number;
  produto: string;
  codigo: string;
  preparo: boolean;
  um_ficha: string | null;
  um_estoque: string | null;
  por_unidade: number;
  na_ficha: number;
  necessario: number | null;
  conversao: string;
  saldo_no_local: number;
  saldo_total: number;
  falta: number;
  custo_unitario: number | null;
  custo: number | null;
  observacao: string | null;
};

type Previsao = {
  id_ficha: number;
  versao: number;
  produto: string;
  codigo: string;
  um_estoque: string | null;
  quantidade: number;
  rendimento_qtd: number;
  rendimento_um: string | null;
  lotes: number;
  itens: ItemPrevisto[];
  itens_faltando: number;
  custo_total: number;
  custo_unitario: number;
};

type Linha = {
  id: number;
  id_produto: number;
  produto: string;
  codigo: string;
  um_estoque: string | null;
  data_prevista: string;
  quantidade: number;
  status: string;
  origem: string;
  observacao: string | null;
  local: string | null;
  criado_por_nome: string | null;
  produzido_por_nome: string | null;
  previsao: Previsao;
};

const qtd = (n: number | string | null) =>
  n === null ? "—" : Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 4 });

const dia = (d: string) => new Date(d + "T12:00").toLocaleDateString("pt-BR");

export default function PaginaOrdemProducao() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const aviso = useAviso();
  const { pode } = useSessao();
  const veCusto = pode("fichas.custos");

  const [linha, setLinha] = useState<Linha | null>(null);
  const [erro, setErro] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const r = await api.get<Linha>(`/producao-agenda/${id}`);
      setLinha(r);
      setQuantidade((a) => a || String(Number(r.quantidade)));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  /** Refaz a conta quando a quantidade muda: é o "e se eu fizer o dobro?". */
  const recalcular = useCallback(async () => {
    if (!linha) return;
    const n = Number(quantidade.replace(",", "."));
    if (!n || n <= 0 || n === Number(linha.quantidade)) return;
    try {
      const p = await api.get<Previsao>(
        `/producao-agenda/necessario?id_produto=${linha.id_produto}&quantidade=${n}`,
      );
      setLinha({ ...linha, previsao: p });
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível recalcular");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linha, quantidade]);

  async function produzir() {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/producao-agenda/${id}/produzir`, {
        quantidade: Number(quantidade.replace(",", ".")),
      });
      aviso.sucesso(r.message, {
        texto: "voltar para a agenda",
        ao: () => router.push("/producao"),
      });
      setConfirmando(false);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível produzir");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!linha) return <Carregando />;

  const p = linha.previsao;
  const planejada = Number(linha.quantidade);
  const agora = Number(quantidade.replace(",", ".")) || planejada;
  const aberta = linha.status === "PLANEJADA";

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/producao" className="link-voltar">
          produção
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          {linha.produto}
        </h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <Etiqueta>{linha.codigo}</Etiqueta>
          <Etiqueta>ficha v{p.versao}</Etiqueta>
          <Etiqueta>{dia(linha.data_prevista)}</Etiqueta>
          {aberta ? (
            <Etiqueta cor="alerta">planejada</Etiqueta>
          ) : (
            <Etiqueta cor="erva">{linha.status.toLowerCase()}</Etiqueta>
          )}
          {linha.origem === "ALERTA" && <Etiqueta>veio do alerta</Etiqueta>}
        </div>
        <p className="mt-2 max-w-[70ch] text-suave">
          A receita rende <b className="mono">{qtd(p.rendimento_qtd)}</b>{" "}
          {p.rendimento_um ?? p.um_estoque} por vez — para{" "}
          <b className="mono">{qtd(agora)}</b> {p.um_estoque} ela é feita{" "}
          <b className="mono">{qtd(p.lotes)}</b> vez(es).
        </p>
      </header>

      {aberta && (
        <Cartao titulo="Quanto produzir">
          <div className="flex flex-wrap items-end gap-3">
            <label>
              <span className="rotulo">Quantidade</span>
              <input
                className="campo campo-toque mono mt-1.5 w-[140px] text-right"
                inputMode="decimal"
                value={quantidade}
                onChange={(e) => setQuantidade(e.target.value)}
                onBlur={() => void recalcular()}
              />
            </label>
            <span className="pb-2.5 text-[13.5px] text-suave">
              {p.um_estoque}
              {agora !== planejada && ` · o plano era ${qtd(planejada)}`}
            </span>
            <button
              className="btn btn-primario ml-auto"
              onClick={() => setConfirmando(true)}
              disabled={ocupado}
            >
              Produzir
            </button>
          </div>
        </Cartao>
      )}

      <Cartao
        titulo="O que vai ser preciso"
        descricao="Por unidade e no total, com o que existe no local de onde vai sair."
        acao={
          p.itens_faltando > 0 ? (
            <Etiqueta cor="alerta">
              {p.itens_faltando} item(ns) faltando
            </Etiqueta>
          ) : (
            <Etiqueta cor="erva">tem tudo</Etiqueta>
          )
        }
      >
        {!p.itens.length ? (
          <Vazio>A ficha não tem ingredientes.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th className="num">Por unidade</th>
                  <th className="num">Total</th>
                  <th className="num">Tem no local</th>
                  {veCusto && <th className="num">Custo</th>}
                </tr>
              </thead>
              <tbody>
                {p.itens.map((i) => (
                  <tr key={i.id_produto}>
                    <td>
                      <span className="font-medium">{i.produto}</span>
                      <span className="block text-[12.5px] text-suave">
                        <span className="mono">{i.codigo}</span>
                        {i.preparo && " · preparo com ficha própria"}
                        {i.observacao && ` · ${i.observacao}`}
                      </span>
                    </td>
                    {/* A ficha fala em grama; o estoque, em quilo. As duas
                        colunas mostram a mesma coisa nas duas linguagens. */}
                    <td className="num whitespace-nowrap text-suave">
                      {qtd(i.por_unidade)} {i.um_ficha ?? i.um_estoque}
                    </td>
                    <td className="num whitespace-nowrap font-semibold">
                      {qtd(i.necessario)} {i.um_estoque}
                      {i.um_ficha && i.um_ficha !== i.um_estoque && (
                        <span className="block text-[12px] font-normal text-suave">
                          {qtd(i.na_ficha)} {i.um_ficha} na receita
                        </span>
                      )}
                    </td>
                    <td
                      className={`num whitespace-nowrap ${
                        i.falta > 0 ? "text-erro" : "text-suave"
                      }`}
                    >
                      {qtd(i.saldo_no_local)} {i.um_estoque}
                      {i.falta > 0 && (
                        <span className="block text-[12px]">
                          faltam {qtd(i.falta)}
                        </span>
                      )}
                    </td>
                    {veCusto && (
                      <td className="num whitespace-nowrap">
                        {i.custo === null ? (
                          <span className="text-alerta">sem custo</span>
                        ) : (
                          <>
                            {reais(i.custo)}
                            <span className="block text-[12px] text-suave">
                              {reais(i.custo_unitario ?? 0)} / {i.um_estoque}
                            </span>
                          </>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
              {veCusto && (
                <tfoot>
                  <tr className="border-t-2 border-linha2 font-semibold">
                    <td colSpan={3}>Custo da produção</td>
                    <td className="num text-suave">
                      {reais(p.custo_unitario)} / {p.um_estoque}
                    </td>
                    <td className="num">{reais(p.custo_total)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}

        {p.itens_faltando > 0 && aberta && (
          <p className="mt-4 text-[13.5px] leading-snug text-suave">
            Falta insumo, mas a produção <b>não é barrada</b>: o razão aceita a saída e marca o
            custo como provisório. O saldo negativo fica à vista até a entrada que faltava ser
            lançada — some do controle é que não pode.
          </p>
        )}
      </Cartao>

      {confirmando && (
        <Confirmacao
          titulo="Confirmar a produção"
          rotuloConfirmar="Produzir"
          ocupado={ocupado}
          aoCancelar={() => setConfirmando(false)}
          aoConfirmar={() => void produzir()}
        >
          <p>
            Produzir{" "}
            <b className="mono">
              {qtd(agora)} {p.um_estoque}
            </b>{" "}
            de <b>{linha.produto}</b>?
          </p>
          {p.itens_faltando > 0 && (
            <p className="mt-2 text-[13.5px] text-alerta">
              {p.itens_faltando} insumo(s) sem saldo suficiente — o custo sai provisório.
            </p>
          )}
          <p className="mt-3 text-[13.5px] text-suave">
            Isto baixa os ingredientes da ficha e devolve o pronto ao estoque. Nada aqui se
            apaga: correção é estorno.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
