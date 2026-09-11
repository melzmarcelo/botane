"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Confirmacao, Vazio } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { custo, qtd } from "@/lib/numeros";

/**
 * Unificar o custo médio das prateleiras — prévia e botão único.
 *
 * 🔑 **Pedido do dono (11/09/2026):** "hoje temos produto com custo em um local,
 * porém em outros locais não tem. gostaria que neste primeiro momento o custo
 * fosse geral, inclusive ajustar isto já nos produtos cadastrados". A migração
 * 064 muda o cálculo dali para a frente; o que já está no estoque precisa deste
 * botão.
 *
 * ⚠️ **A prévia vem antes e é obrigatória.** Reavaliar estoque entra no razão e
 * só sai por estorno. Com centenas de prateleiras, descobrir o efeito depois é
 * tarde — é a mesma regra do ajuste de custo linha a linha, ao lado.
 *
 * ⚠️ **Duas contagens separadas, de propósito.** Prateleira com saldo muda
 * quanto a casa tem em mercadoria (e portanto o CMV); prateleira com saldo zero
 * só passa a saber o custo, sem efeito nenhum. Um número só faria a pessoa
 * aprovar uma reavaliação achando que estava preenchendo campo vazio.
 */

type Linha = {
  id_produto: number;
  produto: string;
  codigo: string | null;
  local: string;
  quantidade: number;
  custo_medio: number;
  custo_novo: number;
  diferenca: number;
};

type Previa = {
  produtos: number;
  prateleiras_reavaliadas: number;
  prateleiras_so_preenchidas: number;
  efeito_no_estoque: number;
  linhas: Linha[];
};

export default function CustoGeral({ aoLancar }: { aoLancar: () => void }) {
  const aviso = useAviso();
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [lancando, setLancando] = useState(false);

  const conferir = useCallback(async () => {
    setCarregando(true);
    try {
      setPrevia(await api.get<Previa>("/ajustes/custo-geral/previa"));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível conferir");
    } finally {
      setCarregando(false);
    }
  }, [aviso]);

  async function unificar() {
    setLancando(true);
    try {
      const r = await api.post<{ message: string }>("/ajustes/custo-geral", {});
      aviso.sucesso(r.message);
      setPrevia(null);
      aoLancar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível unificar");
    } finally {
      setLancando(false);
      setConfirmando(false);
    }
  }

  const nada = previa && previa.produtos === 0;

  return (
    <Cartao
      titulo="Custo único por loja"
      descricao="Põe todas as prateleiras do mesmo produto no mesmo custo médio — o ponderado do que tem saldo."
    >
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn btn-secundario" onClick={() => void conferir()}
                disabled={carregando}>
          {carregando ? "Conferindo…" : "Conferir o que mudaria"}
        </button>
        {previa && !nada && (
          <button type="button" className="btn btn-primario" onClick={() => setConfirmando(true)}
                  disabled={lancando}>
            Unificar {previa.produtos} produto(s)
          </button>
        )}
      </div>

      {carregando && <Carregando />}

      {nada && (
        <div className="mt-4">
          <Aviso tipo="ok">
            Nada a unificar: todas as prateleiras já estão com o mesmo custo.
          </Aviso>
        </div>
      )}

      {previa && !nada && (
        <>
          <div className="mt-4">
            <Aviso tipo="info">
              <b>{previa.produtos} produto(s)</b> com prateleiras discordando.{" "}
              <b>{previa.prateleiras_reavaliadas}</b> com saldo serão{" "}
              <b>reavaliadas</b> — o estoque muda{" "}
              <b>
                {previa.efeito_no_estoque >= 0 ? "+" : ""}
                {reais(previa.efeito_no_estoque)}
              </b>
              , o que {previa.efeito_no_estoque >= 0 ? "REDUZ" : "AUMENTA"} o CMV do período
              em <b>{reais(Math.abs(previa.efeito_no_estoque))}</b>.{" "}
              {previa.prateleiras_so_preenchidas > 0 && (
                <>
                  Outras <b>{previa.prateleiras_so_preenchidas}</b> estão com saldo zero e só
                  passam a saber o custo — sem efeito nenhum.
                </>
              )}
            </Aviso>
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Produto</th>
                  <th>Local</th>
                  <th className="num">Saldo</th>
                  <th className="num">Custo hoje</th>
                  <th className="num">Passa a ser</th>
                  <th className="num">No estoque</th>
                </tr>
              </thead>
              <tbody>
                {previa.linhas.slice(0, 200).map((l) => (
                  <tr key={`${l.id_produto}-${l.local}`}>
                    <td>
                      {l.produto}
                      {l.codigo && (
                        <span className="mono ml-2 text-[12px] text-suave">{l.codigo}</span>
                      )}
                    </td>
                    <td className="text-suave">{l.local}</td>
                    <td className="num mono">{qtd(l.quantidade)}</td>
                    <td className="num mono text-suave">{custo(l.custo_medio)}</td>
                    <td className="num mono">{custo(l.custo_novo)}</td>
                    <td className={`num mono ${l.diferenca < 0 ? "text-erro" : ""}`}>
                      {l.quantidade === 0 ? "—" : reais(l.diferenca)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {previa.linhas.length > 200 && (
              <p className="mt-2 text-[13px] text-suave">
                Mostrando as 200 primeiras de {previa.linhas.length} — o botão trata todas.
              </p>
            )}
          </div>
        </>
      )}

      {previa && confirmando && (
        <Confirmacao
          titulo="Unificar o custo das prateleiras?"
          rotuloConfirmar="Unificar"
          ocupado={lancando}
          aoConfirmar={() => void unificar()}
          aoCancelar={() => setConfirmando(false)}
        >
          <b>{previa.prateleiras_reavaliadas}</b> prateleira(s) serão reavaliadas, mexendo{" "}
          <b>{reais(previa.efeito_no_estoque)}</b> no estoque. Cada uma vira um lançamento de
          ajuste de custo no razão, num lote só — e o razão não se apaga: desfazer depois é
          estornar um por um.
        </Confirmacao>
      )}

      {previa === null && !carregando && (
        <div className="mt-3">
          <Vazio>
            Clique em conferir para ver quais produtos têm custo diferente entre as
            prateleiras.
          </Vazio>
        </div>
      )}
    </Cartao>
  );
}
