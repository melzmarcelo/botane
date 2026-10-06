"use client";

import { useCallback, useMemo, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import {
  conferirReferencia,
  corrigirReferencia,
  type ConferenciaDeReferencia,
} from "@/lib/custo-referencia";
import { custo, numeroParaCusto, reais, textoParaNumero } from "@/lib/numeros";
import LinkProduto from "@/components/link-produto";

/**
 * Conferir e corrigir o custo de REFERÊNCIA — o que veio do Omie.
 *
 * 🔑 **Pedido do dono (05/10/2026):** um vinho vendido a R$ 109,00 aparecia
 * custando R$ 264,00, o preço da caixa de seis, enquanto o razão do mesmo
 * produto saía a R$ 44,00. A referência não tinha tela de edição: o número
 * ficava errado até a primeira nota chegar.
 *
 * ⚠️ **Só vem marcado o que duas testemunhas confirmam** (`confianca: "alta"`).
 * O resto é palpite do sistema e precisa de um sim de alguém, linha a linha.
 *
 * ⚠️ **O campo é editável de propósito.** A sugestão é o melhor que o sistema
 * sabe; quem tem a nota na mão sabe mais.
 *
 * ⚠️ **Não é razão.** Corrigir a referência não cria movimento nem mexe em
 * saldo — por isso não aparece em "Últimos ajustes".
 */
export default function CustoReferencia() {
  const aviso = useAviso();
  const [previa, setPrevia] = useState<ConferenciaDeReferencia | null>(null);
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [valores, setValores] = useState<Record<number, string>>({});
  const [carregando, setCarregando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [gravando, setGravando] = useState(false);

  const conferir = useCallback(async () => {
    setCarregando(true);
    try {
      const p = await conferirReferencia();
      setPrevia(p);
      setMarcados(
        new Set(p.linhas.filter((l) => l.confianca === "alta").map((l) => l.id_produto)),
      );
      setValores(
        Object.fromEntries(
          p.linhas.map((l) => [l.id_produto, l.sugerido ? numeroParaCusto(l.sugerido) : ""]),
        ),
      );
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível conferir");
    } finally {
      setCarregando(false);
    }
  }, [aviso]);

  // O que vai ao servidor: só o marcado e com número válido.
  const itens = useMemo(
    () =>
      (previa?.linhas ?? [])
        .filter((l) => marcados.has(l.id_produto))
        .map((l) => ({
          id_produto: l.id_produto,
          custo: textoParaNumero(valores[l.id_produto] ?? "") ?? 0,
        }))
        .filter((i) => i.custo > 0),
    [previa, marcados, valores],
  );

  function alternar(id: number) {
    setMarcados((atual) => {
      const novo = new Set(atual);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  }

  async function corrigir() {
    setGravando(true);
    try {
      const r = await corrigirReferencia(itens);
      aviso.sucesso(r.message);
      setConfirmando(false);
      await conferir();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível corrigir");
    } finally {
      setGravando(false);
      setConfirmando(false);
    }
  }

  const nada = previa && previa.suspeitos === 0;

  return (
    <Cartao
      titulo="Custo de referência a conferir"
      descricao="Produtos que ainda não receberam nota e são custeados pelo valor que veio do Omie — quando ele não bate com o estoque ou passa do preço de venda."
    >
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn btn-secundario" onClick={() => void conferir()}
                disabled={carregando}>
          {carregando ? "Conferindo…" : "Conferir os custos de referência"}
        </button>
        {previa && !nada && (
          <button type="button" className="btn btn-primario" disabled={!itens.length || gravando}
                  aria-busy={gravando} onClick={() => setConfirmando(true)}>
            Corrigir {itens.length} marcado(s)
          </button>
        )}
      </div>

      {carregando && <Carregando />}

      {nada && (
        <div className="mt-4">
          <Aviso tipo="ok">
            Nada a conferir: {previa.analisados} produto(s) custeados pela referência, e
            nenhum discorda do estoque nem passa do preço de venda.
          </Aviso>
        </div>
      )}

      {previa && !nada && (
        <>
          <div className="mt-4">
            <Aviso tipo="info">
              <b>{previa.suspeitos} produto(s)</b> com a referência suspeita, de{" "}
              {previa.analisados} custeados por ela. <b>{previa.certos}</b> já vêm marcados: o
              custo registrado no estoque confirma a correção. Os outros são palpite — marque
              só o que conferir, e troque o valor se souber o certo.
            </Aviso>
          </div>

          <div className="mt-3 grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th></th>
                  <th>Produto</th>
                  <th className="num">Referência hoje</th>
                  <th className="num">No estoque</th>
                  <th className="num">Preço de venda</th>
                  <th className="num">Passa a ser</th>
                </tr>
              </thead>
              <tbody>
                {previa.linhas.map((l) => (
                  <tr key={l.id_produto}>
                    <td>
                      <input type="checkbox" className="h-4 w-4 cursor-pointer accent-erva"
                             aria-label={`Corrigir ${l.produto}`}
                             checked={marcados.has(l.id_produto)}
                             onChange={() => alternar(l.id_produto)} />
                    </td>
                    <td>
                      <LinkProduto id={l.id_produto}>{l.produto}</LinkProduto>
                      {l.codigo && (
                        <span className="mono ml-2 text-[12px] text-suave">{l.codigo}</span>
                      )}
                      <span className="block text-[12.5px] text-suave">{l.motivo}</span>
                      {l.confianca === "conferir" && (
                        <span className="block">
                          <Etiqueta cor="alerta">conferir</Etiqueta>
                        </span>
                      )}
                    </td>
                    <td className="num mono text-erro">
                      {custo(l.referencia)}
                      {l.um && <span className="block text-[12px] text-suave">por {l.um}</span>}
                    </td>
                    <td className="num mono">{l.razao === null ? "—" : custo(l.razao)}</td>
                    <td className="num mono text-suave">
                      {l.preco === null ? "—" : reais(l.preco)}
                    </td>
                    <td className="num">
                      <input
                        className="campo mono w-28 text-right"
                        inputMode="decimal"
                        aria-label={`Custo certo de ${l.produto}`}
                        value={valores[l.id_produto] ?? ""}
                        onFocus={(e) => e.currentTarget.select()}
                        onChange={(e) =>
                          setValores((v) => ({ ...v, [l.id_produto]: e.target.value }))
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {confirmando && (
        <Confirmacao
          titulo="Corrigir o custo de referência?"
          rotuloConfirmar="Corrigir"
          ocupado={gravando}
          aoConfirmar={() => void corrigir()}
          aoCancelar={() => setConfirmando(false)}
        >
          <b>{itens.length}</b> produto(s) passam a ter o custo informado. Fichas, CMV
          teórico e a Precificação usam o número novo na hora, e as vendas do período em
          aberto que congelaram a referência antiga são recalculadas. Mês fechado não muda.
        </Confirmacao>
      )}

      {previa === null && !carregando && (
        <div className="mt-3">
          <Vazio>
            Clique em conferir para ver os produtos cujo custo de referência parece ser o
            preço da embalagem, e não o da unidade.
          </Vazio>
        </div>
      )}
    </Cartao>
  );
}
