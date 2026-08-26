"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";

/**
 * A fila de de-para: o que foi vendido e não achou produto no cadastro.
 *
 * ⚠️ **Enquanto um item está aqui, a receita dele entra e o custo NÃO.** O CMV
 * teórico sai menor do que foi, a variância sai maior, e nada na tela de CMV
 * denuncia a causa — o número simplesmente parece ruim.
 *
 * Tem página própria porque é uma FILA DE TRABALHO, não um aviso: alguém
 * percorre, cadastra ou vincula, e volta. Na lista de vendas ela ocupava meia
 * tela mostrando o que já estava resolvido.
 */

type Pendencia = {
  codigo_pdv: string | null;
  descricao_pdv: string | null;
  ocorrencias: number;
  quantidade: number;
  receita: number;
};

export default function PaginaSemVinculo() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const [fila, setFila] = useState<Pendencia[] | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setFila(await api.get<Pendencia[]>("/vendas/sem-vinculo"));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  /**
   * Passa o de-para de novo nos itens pendentes.
   *
   * ⚠️ Existe porque a ordem real é a venda chegar ANTES de o cardápio estar
   * ligado: sem isto, item que não achou produto no dia da importação ficaria
   * pendente para sempre, mesmo depois de alguém arrumar o vínculo.
   */
  async function reconciliar() {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>("/pdv/reconciliar");
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reconciliar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;

  const receita = (fila ?? []).reduce((s, p) => s + Number(p.receita), 0);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link href="/vendas" className="link-voltar">
            vendas
          </Link>
          <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
            Itens vendidos sem produto
          </h1>
          <p className="mt-2 max-w-[70ch] text-suave">
            A receita destes itens entra no CMV; o custo, não. Enquanto estiverem aqui, a
            variância do período sai maior do que é — e nada no painel diz por quê.
          </p>
        </div>
        {pode("integracao.pdv") && (
          <button className="btn btn-secundario" onClick={reconciliar} disabled={ocupado}>
            {ocupado ? "Reconciliando…" : "Reconciliar"}
          </button>
        )}
      </header>

      <Cartao
        titulo={fila ? `${fila.length} item(ns) na fila` : "Fila"}
        descricao={
          fila?.length
            ? `${reais(receita)} de receita sem custo do outro lado.`
            : undefined
        }
      >
        {!fila ? (
          <Carregando />
        ) : !fila.length ? (
          <Vazio>
            Nenhum item pendente — todo item vendido achou produto no cadastro.
          </Vazio>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Código no PDV</th>
                    <th>Descrição</th>
                    <th className="num">Vezes</th>
                    <th className="num">Qtd</th>
                    <th className="num">Receita</th>
                  </tr>
                </thead>
                <tbody>
                  {fila.map((p, i) => (
                    <tr key={i}>
                      <td className="mono">{p.codigo_pdv ?? "—"}</td>
                      <td>{p.descricao_pdv ?? "—"}</td>
                      <td className="num tabular-nums">{p.ocorrencias}</td>
                      <td className="num tabular-nums">{Number(p.quantidade)}</td>
                      <td className="num tabular-nums">{reais(Number(p.receita))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-4 text-[13.5px] text-suave">
              Dois caminhos: importar o cardápio em{" "}
              <Link href="/integracoes" className="underline">
                Integrações
              </Link>{" "}
              — que cria o prato e o vínculo de uma vez —, ou cadastrar o produto com o{" "}
              <b>nome exato</b> e clicar em Reconciliar. O vínculo passa a valer também para as
              vendas que já entraram.
            </p>
          </>
        )}
      </Cartao>
    </div>
  );
}
