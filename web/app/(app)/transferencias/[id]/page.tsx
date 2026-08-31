"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";

/**
 * Uma remessa: o que foi despachado, e a conferência de quem recebe.
 *
 * 🔑 **É aqui que o razão se mexe — nas duas lojas, no mesmo instante.** Até o
 * recebimento nada foi lançado: a quantidade continua no estoque da origem. Por
 * isso cancelar não estorna nada, e por isso receber duas vezes é recusado.
 *
 * 🔑 **O que não chegou vira PERDA na origem, não sobra de saldo.** Deixar a
 * diferença na prateleira de quem mandou faria a próxima contagem cobrir o
 * buraco como *ajuste de inventário* — que é onde a diferença some sem nome.
 */

type Item = {
  id: number;
  id_produto: number;
  nome: string;
  codigo: string;
  um_estoque: string | null;
  qtd_enviada: number;
  qtd_recebida: number | null;
  saldo_origem: number;
  observacao: string | null;
  id_movimento_saida: number | null;
  id_movimento_entrada: number | null;
  id_movimento_perda: number | null;
};

type Remessa = {
  id: number;
  status: string;
  enviada_em: string;
  recebida_em: string | null;
  observacao: string | null;
  observacao_recebimento: string | null;
  id_unidade_origem: number;
  id_unidade_destino: number;
  loja_origem: string;
  loja_destino: string;
  local_origem: string;
  local_destino: string;
  enviada_por: string | null;
  recebida_por: string | null;
  itens: Item[];
};

type Motivo = { id: number; nome: string };

const quando = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });

const numero = (n: number) =>
  n.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 4 });

export default function PaginaRemessa() {
  const { id } = useParams<{ id: string }>();
  const aviso = useAviso();
  // ⚠️ A loja vem da SESSÃO, não do localStorage cru: ele fica vazio até alguém
  // mexer no seletor, e a comparação contra zero escondia os DOIS botões —
  // quem abrisse a remessa não tinha o que fazer com ela.
  const { pode, unidade: minhaLoja } = useSessao();

  const [r, setR] = useState<Remessa | null>(null);
  const [erro, setErro] = useState("");
  const [motivos, setMotivos] = useState<Motivo[]>([]);
  // O que quem confere digitou. Vazio quer dizer "chegou o que foi mandado" —
  // o caso comum não se digita, marca-se a exceção.
  const [conferido, setConferido] = useState<Record<number, string>>({});
  const [motivoPerda, setMotivoPerda] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [confirmar, setConfirmar] = useState<"receber" | "cancelar" | null>(null);

  const carregar = useCallback(async () => {
    try {
      setR(await api.get<Remessa>(`/transferencias/${id}`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
    api.get<Motivo[]>("/estoque/motivos-perda").then(setMotivos).catch(() => {});
  }, [carregar]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!r) return <Carregando />;

  const aberta = r.status === "EM_TRANSITO";
  // ⚠️ Quem recebe é o DESTINO — o servidor barra o resto, e a tela não pode
  // oferecer um botão que vai levar 403.
  const podeReceber = aberta && pode("estoque.transferencia_receber")
    && minhaLoja === r.id_unidade_destino;
  const podeCancelar = aberta && pode("estoque.transferencias")
    && minhaLoja === r.id_unidade_origem;

  const recebidaDe = (item: Item) => {
    const digitado = conferido[item.id];
    if (digitado === undefined || digitado === "") return item.qtd_enviada;
    return Number(digitado.replace(",", ".")) || 0;
  };
  const faltaDe = (item: Item) => item.qtd_enviada - recebidaDe(item);
  const temFalta = r.itens.some((i) => faltaDe(i) > 0);
  // ⚠️ **A baixa acontece AGORA, no recebimento** — e a origem pode ter vendido
  // ou consumido o item enquanto a mercadoria viajava. O razão aceita saldo
  // negativo (com custo provisório), mas quem confirma tem de ver antes: o
  // aviso é a prévia que toda ação irreversível da casa mostra.
  const negativarao = r.itens.filter((i) => i.qtd_enviada > i.saldo_origem);

  async function receber() {
    if (!r) return;
    setSalvando(true);
    try {
      const resposta = await api.post<{ message: string }>(`/transferencias/${r.id}/receber`, {
        itens: r.itens.map((i) => ({
          id_item: i.id,
          qtd_recebida: recebidaDe(i),
          id_motivo_perda: motivoPerda ? Number(motivoPerda) : null,
        })),
        observacao: observacao || null,
      });
      aviso.sucesso(resposta.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao receber");
    } finally {
      setSalvando(false);
      setConfirmar(null);
    }
  }

  async function cancelar() {
    if (!r) return;
    setSalvando(true);
    try {
      const resposta = await api.post<{ message: string }>(`/transferencias/${r.id}/cancelar`, {});
      aviso.sucesso(resposta.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao cancelar");
    } finally {
      setSalvando(false);
      setConfirmar(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Link href="/transferencias" className="link-voltar self-start">
        ← Remessas
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="rotulo">Estoque</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Remessa #{r.id}
          </h1>
          <p className="mt-1 text-suave">
            {r.loja_origem} · {r.local_origem} → {r.loja_destino} · {r.local_destino}
          </p>
        </div>
        <Etiqueta cor={aberta ? "alerta" : r.status === "RECEBIDA" ? "erva" : "neutro"}>
          {aberta ? "em trânsito" : r.status === "RECEBIDA" ? "recebida" : "cancelada"}
        </Etiqueta>
      </header>

      {aberta && (
        <Aviso tipo="info">
          Nada foi lançado no estoque ainda: a quantidade{" "}
          <strong>continua contando em {r.loja_origem}</strong>. Ela sai de lá e entra em{" "}
          {r.loja_destino} no instante em que esta remessa for recebida.
        </Aviso>
      )}

      <Cartao>
        <dl className="grid gap-4 sm:grid-cols-3">
          <div>
            <dt className="rotulo">Enviada</dt>
            <dd>
              {quando(r.enviada_em)}
              {r.enviada_por && <span className="text-suave"> · {r.enviada_por}</span>}
            </dd>
          </div>
          <div>
            <dt className="rotulo">Recebida</dt>
            <dd>
              {r.recebida_em ? (
                <>
                  {quando(r.recebida_em)}
                  {r.recebida_por && <span className="text-suave"> · {r.recebida_por}</span>}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt className="rotulo">Observação</dt>
            <dd>{r.observacao || "—"}</dd>
          </div>
        </dl>
      </Cartao>

      <Cartao>
        {!r.itens.length ? (
          <Vazio>Remessa sem itens.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Produto</th>
                  <th className="text-right" style={{ width: 120, minWidth: 120 }}>
                    Enviado
                  </th>
                  <th className="text-right" style={{ width: 130, minWidth: 130 }}>
                    {podeReceber ? "Chegou" : "Recebido"}
                  </th>
                  <th className="text-right" style={{ width: 120, minWidth: 120 }}>
                    Diferença
                  </th>
                  {!aberta && <th>Movimentos</th>}
                </tr>
              </thead>
              <tbody>
                {r.itens.map((item) => {
                  const falta = faltaDe(item);
                  return (
                    <tr key={item.id}>
                      <td>
                        <Link href={`/produtos/${item.id_produto}`} className="link-registro">
                          {item.nome}
                        </Link>
                        <div className="text-suave mono text-[12px]">{item.codigo}</div>
                      </td>
                      <td className="mono text-right">
                        {numero(item.qtd_enviada)} {item.um_estoque}
                      </td>
                      <td className="text-right">
                        {podeReceber ? (
                          <input
                            type="number"
                            step="any"
                            min="0"
                            className="campo campo-toque text-right"
                            aria-label={`Quantidade recebida de ${item.nome}`}
                            placeholder={numero(item.qtd_enviada)}
                            value={conferido[item.id] ?? ""}
                            onChange={(e) =>
                              setConferido({ ...conferido, [item.id]: e.target.value })
                            }
                          />
                        ) : (
                          <span className="mono">
                            {item.qtd_recebida === null
                              ? "—"
                              : `${numero(item.qtd_recebida)} ${item.um_estoque ?? ""}`}
                          </span>
                        )}
                      </td>
                      <td className="mono text-right">
                        {aberta
                          ? falta > 0
                            ? `−${numero(falta)}`
                            : falta < 0
                              ? `+${numero(-falta)}`
                              : "—"
                          : item.id_movimento_perda
                            ? `−${numero(item.qtd_enviada - (item.qtd_recebida ?? 0))}`
                            : "—"}
                      </td>
                      {!aberta && (
                        <td className="text-[12.5px] text-suave">
                          {item.id_movimento_saida ? `saída #${item.id_movimento_saida}` : ""}
                          {item.id_movimento_entrada
                            ? ` · entrada #${item.id_movimento_entrada}`
                            : ""}
                          {/* A perda ganha nome no razão: quem conferir depois
                              precisa achar o movimento, não deduzir que houve um. */}
                          {item.id_movimento_perda ? ` · perda #${item.id_movimento_perda}` : ""}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      {podeReceber && (
        <Cartao>
          <h2 className="text-[17px] font-semibold">Conferir e receber</h2>
          <p className="mt-1 max-w-[72ch] text-suave">
            Deixe o campo em branco no que chegou completo. O que vier a menos é lançado como{" "}
            <strong>perda em {r.loja_origem}</strong> — a mercadoria saiu da prateleira de lá do
            mesmo jeito, e deixá-la no saldo faria a falta reaparecer na contagem seguinte sem nome.
          </p>
          {negativarao.length > 0 && (
            <div className="mt-4">
              <Aviso tipo="info">
                O saldo de {r.loja_origem} já não cobre o que foi despachado —{" "}
                {negativarao.map((i) => i.nome).join(", ")}. A baixa acontece agora, então a
                prateleira de lá fica <strong>negativa</strong>, com custo provisório até a
                próxima entrada. Costuma querer dizer que faltou lançar uma compra.
              </Aviso>
            </div>
          )}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {temFalta && (
              <Campo rotulo="Motivo da perda">
                <select
                  className="campo"
                  value={motivoPerda}
                  onChange={(e) => setMotivoPerda(e.target.value)}
                >
                  <option value="">— sem motivo —</option>
                  {motivos.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.nome}
                    </option>
                  ))}
                </select>
              </Campo>
            )}
            <Campo rotulo="Observação do recebimento">
              <input
                className="campo"
                value={observacao}
                onChange={(e) => setObservacao(e.target.value)}
                placeholder="Caixa amassada, faltou um pote…"
              />
            </Campo>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-primario"
              disabled={salvando}
              onClick={() => setConfirmar("receber")}
            >
              Receber no estoque
            </button>
          </div>
        </Cartao>
      )}

      {podeCancelar && (
        <Cartao>
          <h2 className="text-[17px] font-semibold">Cancelar a remessa</h2>
          <p className="mt-1 max-w-[72ch] text-suave">
            A mercadoria volta a ser só de {r.loja_origem} — que é onde ela nunca deixou de contar.{" "}
            <strong>Nada é estornado</strong>, porque nada foi lançado.
          </p>
          <button
            type="button"
            className="btn mt-4"
            disabled={salvando}
            onClick={() => setConfirmar("cancelar")}
          >
            Cancelar remessa
          </button>
        </Cartao>
      )}

      {confirmar === "receber" && (
        <Confirmacao
          titulo="Receber esta remessa?"
          rotuloConfirmar="Receber"
          ocupado={salvando}
          aoConfirmar={receber}
          aoCancelar={() => setConfirmar(null)}
        >
          {/* ⚠️ O diálogo diz o que a AÇÃO faz, não "tem certeza": é o momento
              em que dois razões se mexem, e depois só se conserta por estorno. */}
          Sai do estoque de {r.loja_origem} e entra em {r.loja_destino}, pelo mesmo custo.
          {temFalta && ` O que não chegou é lançado como perda em ${r.loja_origem}.`}
        </Confirmacao>
      )}
      {confirmar === "cancelar" && (
        <Confirmacao
          titulo="Cancelar esta remessa?"
          rotuloConfirmar="Cancelar remessa"
          perigo
          ocupado={salvando}
          aoConfirmar={cancelar}
          aoCancelar={() => setConfirmar(null)}
        >
          A mercadoria continua em {r.loja_origem}. Nada é lançado nem estornado.
        </Confirmacao>
      )}

      {!aberta && r.status === "RECEBIDA" && (
        <p className="text-[13.5px] text-suave">
          Recebida. Para desfazer, o caminho agora é estornar os movimentos no{" "}
          <Link href="/estoque">razão</Link> — o estoque já se mexeu nas duas lojas.
        </p>
      )}
    </div>
  );
}
