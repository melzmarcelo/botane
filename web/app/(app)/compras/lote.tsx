"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Aviso, Carregando, Etiqueta, Modal } from "@/components/ui";
import { useAviso } from "@/components/aviso-flutuante";
import { reais } from "@/lib/cadastros";
import { lancarLote, previaDoLote, type NotaDoLote, type PreviaDoLote } from "@/lib/compras";
import { dataBr } from "./tipos";

/**
 * Lançar de uma vez as notas que já estão conciliadas.
 *
 * 🔑 **Por que existe (05/10/2026).** No ar havia 94 notas prontas esperando um
 * clique cada, R$ 50 mil de compra fora do estoque — e enquanto esperam, a
 * venda sai sem saldo e o CMV fica sem a compra. Ninguém faz noventa idas à
 * tela da nota.
 *
 * 🔑 **A prévia é do servidor, e é o lançamento ensaiado**: o que aparece como
 * "pronta" passou pela mesma função que lança. A tela não decide nada.
 *
 * ⚠️ **O que trava vem ANTES das notas travadas, e por CADASTRO.** A trava
 * quase nunca é da nota: é um produto sem unidade de estoque, e o mesmo produto
 * segura dezenas. Completar um cadastro solta todas as notas dele.
 * ⚠️ **"Conferir" não tem caixa de marcar.** A nota declara uma conversão
 * diferente da do cadastro; lançar assim põe a quantidade errada num razão que
 * não se apaga. Só na tela da nota, com alguém olhando.
 */
export default function LancarLote({
  aoFechar,
  aoLancar,
}: {
  aoFechar: () => void;
  /** A lista de notas por trás da janela precisa se atualizar. */
  aoLancar: () => void;
}) {
  const aviso = useAviso();
  const [previa, setPrevia] = useState<PreviaDoLote | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  /** As prontas que a pessoa DESMARCOU. O padrão é lançar todas. */
  const [fora, setFora] = useState<Set<number>>(new Set());
  /** As que o servidor recusou na hora de lançar, com o motivo de cada uma. */
  const [recusadas, setRecusadas] = useState<NotaDoLote[]>([]);

  async function carregar() {
    setErro("");
    try {
      setPrevia(await previaDoLote());
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a prévia");
    }
  }

  useEffect(() => {
    void carregar();
  }, []);

  const prontas = useMemo(() => previa?.notas.filter((n) => n.situacao === "pronta") ?? [], [previa]);
  const conferir = useMemo(() => previa?.notas.filter((n) => n.situacao === "conferir") ?? [], [previa]);
  const travadas = useMemo(() => previa?.notas.filter((n) => n.situacao === "travada") ?? [], [previa]);
  const escolhidas = prontas.filter((n) => !fora.has(n.id));
  const valorEscolhido = escolhidas.reduce((s, n) => s + n.valor_total, 0);

  const alternar = (id: number) =>
    setFora((atuais) => {
      const novas = new Set(atuais);
      if (novas.has(id)) novas.delete(id);
      else novas.add(id);
      return novas;
    });

  async function lancar() {
    setOcupado(true);
    try {
      const r = await lancarLote(escolhidas.map((n) => n.id));
      if (r.notas) aviso.sucesso(r.message);
      else aviso.erro(r.message);
      aoLancar();
      if (r.fora.length === 0) {
        aoFechar();
        return;
      }
      // Alguma mudou de situação entre a prévia e o clique: fica na tela com o
      // motivo, e a prévia é refeita com o que sobrou.
      setRecusadas(r.fora);
      setFora(new Set());
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível lançar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      titulo="Lançar as notas conciliadas"
      descricao="As notas sem item pendente desta loja, da mais antiga para a mais nova"
      aoFechar={aoFechar}
      largura="940px"
      rodape={
        <div className="flex flex-wrap items-center justify-end gap-3">
          {previa && (
            <span className="text-[13.5px] text-suave">
              {escolhidas.length} nota(s) · <b className="text-tinta">{reais(valorEscolhido)}</b>
            </span>
          )}
          <button className="btn btn-secundario" onClick={aoFechar}>
            Fechar
          </button>
          <button
            className="btn btn-primario"
            aria-busy={ocupado}
            disabled={ocupado || escolhidas.length === 0}
            onClick={lancar}
          >
            {ocupado ? "Lançando…" : `Lançar ${escolhidas.length} nota(s) no estoque`}
          </button>
        </div>
      }
    >
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!previa && !erro && <Carregando />}

      {previa && (
        <div className="flex flex-col gap-5">
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Bloco rotulo="Prontas para lançar" n={previa.resumo.pronta.notas}
                   valor={previa.resumo.pronta.valor} cor="erva" />
            <Bloco rotulo="Pedem conferência" n={previa.resumo.conferir.notas}
                   valor={previa.resumo.conferir.valor} cor="alerta" />
            <Bloco rotulo="Travadas" n={previa.resumo.travada.notas}
                   valor={previa.resumo.travada.valor} cor="neutro" />
          </dl>

          {recusadas.length > 0 && (
            <Aviso tipo="erro">
              <b>{recusadas.length} nota(s) não entraram</b>, porque mudaram desde a prévia:
              <ul className="mt-1 list-disc pl-5">
                {recusadas.slice(0, 5).map((n) => (
                  <li key={n.id}>
                    NF {n.numero ?? n.id} — {n.motivo}
                  </li>
                ))}
              </ul>
            </Aviso>
          )}

          {prontas.length > 0 ? (
            <section>
              <h3 className="text-[15px] font-semibold">Prontas</h3>
              <div className="mt-2 grid-rolante">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th className="w-[44px]">
                        <span className="sr-only">Lançar</span>
                      </th>
                      <th>Nota</th>
                      <th>Data</th>
                      <th className="num">Itens</th>
                      <th className="num">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prontas.map((n) => (
                      <tr key={n.id}>
                        <td>
                          <input
                            type="checkbox"
                            className="h-4 w-4 cursor-pointer accent-erva"
                            checked={!fora.has(n.id)}
                            onChange={() => alternar(n.id)}
                            aria-label={`Lançar a NF ${n.numero ?? n.id}`}
                          />
                        </td>
                        <td>
                          <Link href={`/compras/${n.id}`} className="link-registro" target="_blank">
                            NF {n.numero ?? n.id}
                          </Link>
                          <span className="block text-[13px] text-suave">{n.fornecedor}</span>
                        </td>
                        <td>
                          {dataBr(n.data)}
                          {/* ⚠️ A nota atrasada: já há movimento depois da data dela. */}
                          {!!n.fora_de_ordem && (
                            <span className="block text-[12px] text-alerta"
                                  title="Já há movimento desses produtos com data posterior à desta nota. Depois de lançar, reprocesse-os em Estoque ▸ Saldos e movimentos para o custo das saídas acompanhar.">
                              {n.fora_de_ordem} produto(s) a reprocessar
                            </span>
                          )}
                        </td>
                        <td className="num tabular-nums">{n.itens}</td>
                        <td className="num tabular-nums">{reais(n.valor_total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <Aviso tipo="info">Nenhuma nota está pronta para lançar agora.</Aviso>
          )}

          {previa.destrava.length > 0 && (
            <section>
              <h3 className="text-[15px] font-semibold">O que destrava mais notas</h3>
              <p className="prosa mt-1 text-[13.5px] text-suave">
                A trava quase sempre é do cadastro, não da nota. Completar um destes solta
                todas as notas em que ele aparece.
              </p>
              <div className="mt-2 grid-rolante">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Produto</th>
                      <th>O que falta</th>
                      <th className="num">Notas paradas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previa.destrava.slice(0, 12).map((p) => (
                      <tr key={p.id}>
                        <td>
                          <Link href={`/produtos/${p.id}`} className="link-registro" target="_blank">
                            {p.nome}
                          </Link>
                          {p.codigo && <span className="mono block text-[12px] text-suave">{p.codigo}</span>}
                        </td>
                        <td>
                          {p.causa === "sem_unidade"
                            ? "Unidade de estoque"
                            : "Está arquivado — a nota precisa apontar para o cadastro em uso"}
                        </td>
                        <td className="num tabular-nums">{p.notas}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <Parada
            titulo="Pedem conferência"
            explica="A nota declara uma conversão diferente da do cadastro. Lançar assim poria a quantidade errada no estoque, e o estoque não se apaga — abra a nota e resolva lá."
            notas={conferir}
            cor="alerta"
          />
          <Parada
            titulo="Travadas"
            explica="O lançamento recusaria estas, pelo motivo ao lado."
            notas={travadas}
            cor="neutro"
          />
        </div>
      )}
    </Modal>
  );
}

function Bloco({ rotulo, n, valor, cor }: {
  rotulo: string; n: number; valor: number; cor: "erva" | "alerta" | "neutro";
}) {
  return (
    <div className="rounded-xl border border-linha bg-superficie p-4">
      <dt className="flex items-center gap-2 text-[13px] text-suave">
        <Etiqueta cor={cor}>{n}</Etiqueta>
        {rotulo}
      </dt>
      <dd className="mt-1 text-[20px] font-bold tabular-nums">{reais(valor)}</dd>
    </div>
  );
}

/** As notas que o lote não lança, com o porquê de cada uma. Fechada por padrão. */
function Parada({ titulo, explica, notas, cor }: {
  titulo: string; explica: string; notas: NotaDoLote[]; cor: "alerta" | "neutro";
}) {
  if (notas.length === 0) return null;
  return (
    <details>
      <summary className="cursor-pointer text-[15px] font-semibold">
        {titulo} <Etiqueta cor={cor}>{notas.length}</Etiqueta>
      </summary>
      <p className="prosa mt-1 text-[13.5px] text-suave">{explica}</p>
      <div className="mt-2 grid-rolante">
        <table className="tabela">
          <thead>
            <tr>
              <th>Nota</th>
              <th>Motivo</th>
              <th className="num">Valor</th>
            </tr>
          </thead>
          <tbody>
            {notas.map((n) => (
              <tr key={n.id}>
                <td>
                  <Link href={`/compras/${n.id}`} className="link-registro" target="_blank">
                    NF {n.numero ?? n.id}
                  </Link>
                  <span className="block text-[13px] text-suave">{n.fornecedor}</span>
                </td>
                <td className="text-[13.5px]">{n.motivo}</td>
                <td className="num tabular-nums">{reais(n.valor_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
