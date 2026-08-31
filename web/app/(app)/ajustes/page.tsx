"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local, reais } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";

/**
 * Ajuste de estoque — o lançamento feito À MÃO.
 *
 * Entrada, saída, perda e transferência moravam como botões na tela de saldos,
 * que é onde se CONSULTA. Consultar e lançar são gestos diferentes: um é do dia
 * a dia de quem confere, o outro é do momento em que alguém precisa acertar o
 * estoque. Aqui a pessoa escolhe o tipo primeiro e o formulário se molda a ele.
 *
 * O que NÃO entra aqui: o que tem porta própria — nota de entrada (Compras),
 * produção (Produção), contagem (Inventário) e venda (importação do PDV). Este
 * é o caminho do que não nasce de um documento.
 */

type Motivo = { id: number; nome: string };
type SaldoDoProduto = {
  id_local: number;
  local: string;
  quantidade: number;
  um_estoque: string | null;
};

type PreviaSaldo = {
  produto: string;
  um: string | null;
  saldo_atual: number;
  saldo_novo: number;
  diferenca: number;
  movimento: string;
  custo_medio: number;
  valor: number;
  efeito_no_cmv: number;
};

type PreviaCusto = {
  produto: string;
  saldo: number;
  um: string | null;
  custo_atual: number;
  custo_novo: number;
  valor_atual: number;
  valor_novo: number;
  diferenca: number;
  efeito_no_cmv: number;
};

type Tipo = "entrada" | "saida" | "perda" | "transferencia" | "saldo" | "custo";

type Movimento = {
  id: number;
  data_movimento: string;
  tipo: string;
  rotulo: string;
  produto: string;
  local: string;
  quantidade: number;
  custo_unitario: number;
  custo_total: number;
  motivo: string | null;
  observacao: string | null;
  usuario: string | null;
  estornado: boolean;
};

const TIPOS: {
  id: Tipo;
  nome: string;
  chave: string;
  descricao: string;
}[] = [
  {
    id: "entrada",
    nome: "Entrada",
    chave: "estoque.entradas",
    descricao:
      "Compra sem nota, sobra de contagem, devolução do cliente. O custo informado é o de aquisição: já com frete e desconto dentro.",
  },
  {
    id: "saida",
    nome: "Saída",
    chave: "estoque.saidas",
    descricao:
      "Consumo interno, cortesia, degustação. Sai pelo custo médio do estoque, sem passar por ficha.",
  },
  {
    id: "perda",
    nome: "Perda",
    chave: "estoque.perdas",
    descricao: "Quebra, vencimento, sobra descartada. Perda com nome vira decisão; perda anônima vira desconfiança.",
  },
  {
    id: "transferencia",
    nome: "Transferência",
    chave: "estoque.transferencias",
    descricao:
      "Mudar de local sem mudar de dono. Não cria nem destrói valor: sai de um lado pelo médio e entra do outro pelo mesmo.",
  },
  {
    id: "saldo",
    nome: "Ajuste de estoque",
    // 🔑 A permissão existia desde o começo — "ajustar saldo fora do
    // inventário" — sem nenhuma funcionalidade atrás dela. É esta.
    chave: "estoque.ajuste",
    descricao:
      "A prateleira tem 12 e o sistema diz 15. Aqui se informa quanto REALMENTE tem, e o sistema lança a sobra ou a falta — que aparece no CMV como ajuste de inventário.",
  },
  {
    id: "custo",
    nome: "Ajuste de custo",
    // ⚠️ Chave PRÓPRIA: mexer na quantidade é dizer que a prateleira tem outra
    // coisa; mexer no custo é dizer que o dinheiro é outro. Quem confere a
    // despensa não precisa desse poder — e por isso o cartão nem aparece para
    // quem não tem a chave.
    chave: "estoque.custo",
    descricao:
      "Corrige o custo médio de quem já está em estoque. A quantidade não muda — só quanto ela vale. Muda o CMV do período.",
  },
];

// Só os movimentos que nascem AQUI. O razão inteiro tem tela própria.
const TIPOS_DA_MAO = ["ENTRADA_MANUAL", "SAIDA_CONSUMO_INTERNO", "SAIDA_PERDA",
                      "TRANSFERENCIA_SAIDA", "TRANSFERENCIA_ENTRADA", "AJUSTE_CUSTO"];

// Ajuste mexe no razão: produto que não controla estoque não tem o que ajustar.
const PRODUTOS = fonteProdutos((p) => p.controla_estoque);

const VAZIO = {
  id_produto: "",
  quantidade: "",
  custo_unitario: "",
  // O custo CERTO, não a diferença: pedir a diferença obrigaria a fazer a
  // conta de cabeça, que é onde o erro entra.
  custo_novo: "",
  quantidade_certa: "",
  id_local: "",
  id_local_destino: "",
  id_motivo_perda: "",
  documento: "",
  observacao: "",
  lote: "",
  validade: "",
};

const qtd = (n: number | string) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

export default function PaginaAjustes() {
  const aviso = useAviso();
  const { pode } = useSessao();

  const permitidos = TIPOS.filter((t) => pode(t.chave));
  const [tipo, setTipo] = useState<Tipo | null>(null);
  const [produto, setProduto] = useState<{ id: number; rotulo: string } | null>(null);
  const [locais, setLocais] = useState<Local[]>([]);
  const [locaisTodos, setLocaisTodos] = useState<Local[]>([]);
  /** Este local é de outra loja que não a atual? Só então o nome dela importa. */
  const outraLoja = (l: Local) =>
    !!l.loja && locais.length > 0 && l.id_unidade !== locais[0]?.id_unidade;
  const [motivos, setMotivos] = useState<Motivo[]>([]);
  const [recentes, setRecentes] = useState<Movimento[] | null>(null);
  const [f, setF] = useState({ ...VAZIO });
  const [erro, setErro] = useState("");
  const [confirmando, setConfirmando] = useState<Movimento | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [previaCusto, setPreviaCusto] = useState<PreviaCusto | null>(null);
  const [previaSaldo, setPreviaSaldo] = useState<PreviaSaldo | null>(null);
  // Onde este produto TEM saldo. `null` = ainda não perguntamos.
  const [ondeTem, setOndeTem] = useState<SaldoDoProduto[] | null>(null);

  const carregarRecentes = useCallback(async () => {
    try {
      const tudo = await Promise.all(
        TIPOS_DA_MAO.map((t) =>
          api.get<Movimento[]>(`/estoque/movimentos?tipo=${t}&limite=10`),
        ),
      );
      setRecentes(
        tudo.flat().sort((a, b) => b.id - a.id).slice(0, 12),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    api.get<Local[]>("/locais").then(setLocais).catch(() => {});
    // 🔑 **O destino da transferência pode ser a prateleira da OUTRA loja** — é
    // o que a casa faz quando a matriz produz e manda para a filial. Só as
    // lojas que a pessoa enxerga vêm; o servidor barra o resto.
    api.get<Local[]>("/locais?todas_lojas=true").then(setLocaisTodos).catch(() => {});
    api.get<Motivo[]>("/estoque/motivos-perda").then(setMotivos).catch(() => {});
    void carregarRecentes();
  }, [carregarRecentes]);

  // O primeiro tipo permitido já vem escolhido: quem abriu esta tela veio
  // lançar alguma coisa, e um formulário fechado seria um clique a mais.
  useEffect(() => {
    if (!tipo && permitidos.length) escolher(permitidos[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [permitidos.length]);

  function escolher(novo: Tipo) {
    setTipo(novo);
    setProduto(null);
    setF({
      ...VAZIO,
      id_local: String(locais.find((l) => l.principal)?.id ?? locais[0]?.id ?? ""),
    });
  }

  // O local padrão só existe depois que a lista chega.
  useEffect(() => {
    setF((a) =>
      a.id_local
        ? a
        : { ...a, id_local: String(locais.find((l) => l.principal)?.id ?? locais[0]?.id ?? "") },
    );
  }, [locais]);

  /**
   * O que o ajuste de custo faria, perguntado ao SERVIDOR.
   *
   * ⚠️ Ele entra no razão e só sai por estorno — quem confirma precisa ver a
   * diferença em REAIS, não em custo unitário, que é onde o erro de casa
   * decimal se esconde. E o efeito no CMV vem com o sinal certo, que é
   * contraintuitivo: estoque mais caro, CMV MENOR.
   */
  const conferirCusto = useCallback(async () => {
    if (!f.id_produto || !f.custo_novo.trim()) {
      setPreviaCusto(null);
      setPreviaSaldo(null);
      return;
    }
    try {
      const r = await api.post<{ linhas: PreviaCusto[] }>("/ajustes/custo/previa", {
        linhas: [
          {
            id_produto: Number(f.id_produto),
            custo_novo: Number(f.custo_novo.replace(",", ".")),
            id_local: f.id_local ? Number(f.id_local) : null,
          },
        ],
      });
      setPreviaCusto(r.linhas?.[0] ?? null);
    } catch {
      // Prévia é conforto, não trava: se ela falhar, o lançamento ainda
      // responde com a mensagem certa do servidor.
      setPreviaCusto(null);
      setPreviaSaldo(null);
    }
  }, [f.id_produto, f.custo_novo, f.id_local]);

  /**
   * Onde este produto tem saldo.
   *
   * 🔑 **A lista de locais tinha TODOS os locais da casa** — 93 numa base real —
   * enquanto o produto costuma estar em um. Escolher o errado não dava erro na
   * hora: numa saída, o razão registrava a baixa por um local onde o insumo
   * nunca passou, criando saldo NEGATIVO com custo provisório. É o mesmo
   * defeito que a produção já tinha tido.
   *
   * ⚠️ Na ENTRADA a lista continua inteira: a primeira entrada de um produto
   * novo não tem saldo em lugar nenhum, e restringir ali impediria de cadastrar
   * o estoque inicial.
   */
  useEffect(() => {
    if (!f.id_produto) {
      setOndeTem(null);
      return;
    }
    let cancelado = false;
    api
      .get<SaldoDoProduto[]>(`/estoque/saldos?id_produto=${f.id_produto}`)
      .then((linhas) => {
        if (cancelado) return;
        const comSaldo = linhas.filter((l) => Number(l.quantidade) !== 0);
        setOndeTem(comSaldo);
        // Um só: escolhe sozinho. Obrigar a abrir um seletor de uma opção é
        // atrito puro — e é onde alguém deixa o padrão errado passar.
        if (comSaldo.length === 1) {
          setF((a) => ({ ...a, id_local: String(comSaldo[0].id_local) }));
        }
      })
      .catch(() => {
        // Falhar aqui não pode travar o lançamento: cai para a lista inteira.
        if (!cancelado) setOndeTem(null);
      });
    return () => {
      cancelado = true;
    };
  }, [f.id_produto]);

  /**
   * Os locais que o seletor oferece.
   *
   * Onde o produto TEM saldo, para não escolher a prateleira errada. Mas o
   * filtro é conforto, não trava:
   *
   * ⚠️ **Sem saldo em lugar nenhum, a lista volta INTEIRA.** Lançar perda ou
   * saída de algo que o sistema acha que é zero é legítimo — o razão aceita e
   * marca o custo como provisório. Bloquear ali obrigaria a inventar uma
   * entrada antes, que é pior: cria uma compra que não houve.
   *
   * ⚠️ Entrada e o DESTINO da transferência também aceitam qualquer local —
   * as duas põem mercadoria onde ela ainda não está.
   */
  const locaisDoTipo =
    tipo === "entrada" || ondeTem === null || ondeTem.length === 0
      ? locais
      : locais.filter((l) => ondeTem.some((o) => o.id_local === l.id));

  const quantoTem = (idLocal: number) =>
    ondeTem?.find((o) => o.id_local === idLocal);

  /** O que o acerto de saldo faria, perguntado ao SERVIDOR. */
  const conferirSaldo = useCallback(async () => {
    if (!f.id_produto || !f.quantidade_certa.trim()) {
      setPreviaSaldo(null);
      return;
    }
    try {
      setPreviaSaldo(
        await api.post<PreviaSaldo>("/ajustes/estoque/previa", {
          id_produto: Number(f.id_produto),
          quantidade_certa: Number(f.quantidade_certa.replace(",", ".")),
          id_local: f.id_local ? Number(f.id_local) : null,
        }),
      );
    } catch {
      setPreviaSaldo(null);
    }
  }, [f.id_produto, f.quantidade_certa, f.id_local]);

  async function lancar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    const base = {
      id_produto: Number(f.id_produto),
      quantidade: Number(f.quantidade.replace(",", ".")),
      id_local: f.id_local ? Number(f.id_local) : null,
      observacao: f.observacao || null,
    };
    try {
      if (tipo === "saldo") {
        const r = await api.post<{
          saldo_anterior: number;
          saldo_novo: number;
          movimento: string;
          valor: number;
        }>("/ajustes/estoque", {
          id_produto: base.id_produto,
          quantidade_certa: Number(f.quantidade_certa.replace(",", ".")),
          id_local: base.id_local,
          observacao: base.observacao,
        });
        aviso.sucesso(
          `Saldo acertado de ${qtd(r.saldo_anterior)} para ${qtd(r.saldo_novo)} — ` +
            `${r.movimento} de ${reais(Math.abs(r.valor))}.`,
        );
      } else if (tipo === "custo") {
        const r = await api.post<{
          lancados: number;
          diferenca_total: number;
          linhas: { custo_anterior: number; custo_novo: number }[];
        }>("/ajustes/custo", {
          observacao: base.observacao,
          linhas: [
            {
              id_produto: base.id_produto,
              custo_novo: Number(f.custo_novo.replace(",", ".")),
              id_local: base.id_local,
            },
          ],
        });
        const l = r.linhas?.[0];
        aviso.sucesso(
          `Custo corrigido de ${reais(Number(l?.custo_anterior))} para ` +
            `${reais(Number(l?.custo_novo))} — ${reais(r.diferenca_total)} de diferença no estoque.`,
        );
      } else if (tipo === "entrada") {
        const r = await api.post<{ custo_medio: number }>("/estoque/entradas", {
          ...base,
          custo_unitario: Number(f.custo_unitario.replace(",", ".")),
          documento: f.documento || null,
          lote: f.lote || null,
          validade: f.validade || null,
        });
        aviso.sucesso(`Entrada lançada. Novo custo médio: ${reais(Number(r.custo_medio))}`);
      } else if (tipo === "transferencia") {
        await api.post("/estoque/transferencias", {
          id_produto: base.id_produto,
          quantidade: base.quantidade,
          id_local_origem: Number(f.id_local),
          id_local_destino: Number(f.id_local_destino),
          observacao: base.observacao,
        });
        aviso.sucesso("Transferência lançada.");
      } else {
        const r = await api.post<{
          custo_unitario: number;
          custo_provisorio: boolean;
          message: string;
        }>("/estoque/saidas", {
          ...base,
          tipo: tipo === "perda" ? "SAIDA_PERDA" : "SAIDA_CONSUMO_INTERNO",
          id_motivo_perda: f.id_motivo_perda ? Number(f.id_motivo_perda) : null,
        });
        // A frase de qual lote saiu vem pronta do servidor: escrevê-la de novo
        // aqui seria a segunda versão da mesma regra.
        aviso.sucesso(
          `${r.message ?? "Saída lançada"} — ${reais(Number(r.custo_unitario))} por unidade.` +
            (r.custo_provisorio ? " Custo provisório: não havia saldo suficiente." : ""),
        );
      }
      // O formulário fica ABERTO e limpo: quem ajusta um item costuma ajustar o
      // próximo, e fechar obrigaria a escolher o tipo de novo.
      setF((a) => ({ ...VAZIO, id_local: a.id_local }));
      setProduto(null);
      setPreviaCusto(null);
      setPreviaSaldo(null);
      await carregarRecentes();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível lançar");
    } finally {
      setSalvando(false);
    }
  }

  async function estornar(m: Movimento) {
    try {
      await api.post(`/estoque/movimentos/${m.id}/estornar`, { motivo: "estorno pela tela" });
      aviso.sucesso("Movimento estornado — o original continua no razão, com a contrapartida.");
      await carregarRecentes();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível estornar");
    }
  }

  if (!permitidos.length) {
    return (
      <Cartao titulo="Ajustes de estoque">
        <Vazio>Você não tem permissão para lançar ajustes.</Vazio>
      </Cartao>
    );
  }

  const atual = TIPOS.find((t) => t.id === tipo);
  const semLocalDestino = locais.length < 2;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Estoque</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
          Ajustes de estoque
        </h1>
        <p className="mt-1 max-w-[68ch] text-suave">
          O lançamento feito à mão, para o que não nasce de um documento. Nota de entrada,
          produção, contagem e venda têm caminho próprio — e nada aqui é apagado: correção
          entra como estorno.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao titulo="Que ajuste é este?">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {permitidos.map((t) => {
            const escolhido = t.id === tipo;
            const bloqueado = t.id === "transferencia" && semLocalDestino;
            return (
              <button
                key={t.id}
                type="button"
                disabled={bloqueado}
                onClick={() => escolher(t.id)}
                aria-pressed={escolhido}
                className={`rounded border p-3 text-left transition-colors ${
                  escolhido
                    ? "border-erva bg-erva-claro"
                    : "border-linha2 bg-superficie hover:border-erva"
                } ${bloqueado ? "cursor-not-allowed opacity-55" : ""}`}
              >
                <span
                  className={`block text-[15px] font-semibold ${escolhido ? "text-erva" : ""}`}
                >
                  {t.nome}
                </span>
                <span className="mt-1 block text-[12.5px] leading-snug text-suave">
                  {bloqueado ? "Precisa de mais de um local de estoque." : t.descricao}
                </span>
              </button>
            );
          })}
        </div>
      </Cartao>

      {atual && (
        <Cartao titulo={`Lançar ${atual.nome.toLowerCase()}`}>
          <form onSubmit={lancar} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Produto" className="sm:col-span-2" dica="código ou nome, e Tab">
              <BuscaCadastro
                fonte={PRODUTOS}
                required
                selecionado={produto}
                aoEscolher={(i: ItemBusca | null) => {
                  setProduto(i ? { id: i.id, rotulo: rotuloDe(i) } : null);
                  setF((a) => ({ ...a, id_produto: i ? String(i.id) : "" }));
                  // Trocar o produto invalida a prévia: sem isso ela
                  // mostraria o número de outro item.
                  setPreviaCusto(null);
                  setPreviaSaldo(null);
      setPreviaSaldo(null);
                }}
              />
            </Campo>
            {/* ⚠️ O ajuste de custo NÃO tem quantidade: é o que o separa dos
                outros quatro. Mostrar o campo desabilitado sugeriria que
                alguma quantidade se move. */}
            {tipo !== "custo" && tipo !== "saldo" && (
              <Campo rotulo="Quantidade">
                <input
                  className="campo mono"
                  type="number"
                  step="0.001"
                  min="0.001"
                  required
                  value={f.quantidade}
                  onChange={(e) => setF({ ...f, quantidade: e.target.value })}
                />
              </Campo>
            )}
            {tipo === "saldo" && (
              <Campo rotulo="Quantidade que REALMENTE tem">
                <input
                  className="campo mono"
                  type="number"
                  step="0.001"
                  min="0"
                  required
                  value={f.quantidade_certa}
                  onChange={(e) => setF({ ...f, quantidade_certa: e.target.value })}
                  // A prévia é do SERVIDOR, no blur — a mesma regra do ajuste
                  // de custo, e pelo mesmo motivo.
                  onBlur={() => void conferirSaldo()}
                />
              </Campo>
            )}
            {tipo === "custo" && (
              <Campo rotulo="Custo médio certo (R$)">
                <input
                  className="campo mono"
                  type="number"
                  step="0.000001"
                  min="0"
                  required
                  value={f.custo_novo}
                  onChange={(e) => setF({ ...f, custo_novo: e.target.value })}
                  // A prévia é pedida ao SERVIDOR quando o campo perde o foco.
                  // Refazer a conta aqui criaria a segunda versão da mesma
                  // regra, e as duas divergiriam no primeiro caso de borda.
                  onBlur={() => void conferirCusto()}
                />
              </Campo>
            )}
            {tipo === "entrada" && (
              <Campo rotulo="Custo unitário (R$)">
                <input
                  className="campo mono"
                  type="number"
                  step="0.000001"
                  min="0"
                  required
                  value={f.custo_unitario}
                  onChange={(e) => setF({ ...f, custo_unitario: e.target.value })}
                />
              </Campo>
            )}
            <Campo
              rotulo={tipo === "transferencia" ? "De qual local" : "Local"}
              dica={
                tipo !== "entrada" && ondeTem && ondeTem.length > 1
                  ? `Este produto está em ${ondeTem.length} locais.`
                  : undefined
              }
            >
              <select
                className="campo"
                value={f.id_local}
                onChange={(e) => {
                  setF({ ...f, id_local: e.target.value });
                  // Trocar de prateleira muda os números da prévia.
                  setPreviaSaldo(null);
                  setPreviaCusto(null);
                }}
              >
                {locaisDoTipo.map((l) => {
                  const tem = quantoTem(l.id);
                  return (
                    <option key={l.id} value={l.id}>
                      {/* A quantidade no rótulo é o que faz a escolha ser
                          consciente em vez de um chute entre nomes. */}
                      {l.nome}
                      {tem ? ` — ${qtd(tem.quantidade)} ${tem.um_estoque ?? ""}` : ""}
                    </option>
                  );
                })}
              </select>
            </Campo>
            {tipo === "transferencia" && (
              <Campo rotulo="Para qual local">
                <select
                  className="campo"
                  required
                  value={f.id_local_destino}
                  onChange={(e) => setF({ ...f, id_local_destino: e.target.value })}
                >
                  <option value="">— escolha —</option>
                  {(locaisTodos.length ? locaisTodos : locais)
                    .filter((l) => l.id.toString() !== f.id_local)
                    .map((l) => (
                      <option key={l.id} value={l.id}>
                        {/* ⚠️ O nome da loja entra quando há mais de uma: sem
                            ele a lista mostraria dois "Estoque" e quem escolhe
                            não teria como saber qual é qual. */}
                        {l.nome}
                        {outraLoja(l) ? ` · ${l.loja}` : ""}
                      </option>
                    ))}
                </select>
              </Campo>
            )}
            {tipo === "perda" && (
              <Campo rotulo="Motivo">
                <select
                  className="campo"
                  required
                  value={f.id_motivo_perda}
                  onChange={(e) => setF({ ...f, id_motivo_perda: e.target.value })}
                >
                  <option value="">— escolha —</option>
                  {motivos.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.nome}
                    </option>
                  ))}
                </select>
              </Campo>
            )}
            {tipo === "entrada" && (
              <>
                <Campo rotulo="Documento" dica="nº da nota, se houver">
                  <input
                    className="campo"
                    value={f.documento}
                    onChange={(e) => setF({ ...f, documento: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Lote" dica="opcional">
                  <input
                    className="campo mono"
                    value={f.lote}
                    onChange={(e) => setF({ ...f, lote: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Validade" dica="opcional">
                  <input
                    className="campo"
                    type="date"
                    value={f.validade}
                    onChange={(e) => setF({ ...f, validade: e.target.value })}
                  />
                </Campo>
              </>
            )}
            <Campo rotulo="Observação" className="sm:col-span-2">
              <input
                className="campo"
                placeholder="o que aconteceu"
                value={f.observacao}
                onChange={(e) => setF({ ...f, observacao: e.target.value })}
              />
            </Campo>
            <div className="flex items-end">
              <button className="btn btn-primario" type="submit" disabled={salvando}>
                {salvando ? "Lançando…" : `Lançar ${atual.nome.toLowerCase()}`}
              </button>
            </div>
          </form>

          {/*
            ⚠️ A prévia fica DEPOIS do formulário e antes de qualquer outra
            coisa: o ajuste de custo entra no razão e só sai por estorno. E o
            sinal do efeito no CMV é contraintuitivo — subir o custo aumenta o
            estoque final, e o CMV é `inicial + compras − final`, então o CMV
            CAI. Sem essa frase escrita, o número muda e ninguém sabe por quê.
          */}
          {tipo === "saldo" && previaSaldo && (
            <div className="mt-4">
              <Aviso tipo="info">
                <b>{previaSaldo.produto}</b>: o sistema tem{" "}
                {qtd(previaSaldo.saldo_atual)} {previaSaldo.um} e passa a ter{" "}
                {qtd(previaSaldo.saldo_novo)} — <b>{previaSaldo.movimento}</b> de{" "}
                {qtd(Math.abs(previaSaldo.diferenca))} {previaSaldo.um}, que valem{" "}
                <b>{reais(Math.abs(previaSaldo.valor))}</b> pelo custo médio de{" "}
                {reais(previaSaldo.custo_medio)}.{" "}
                {/* ⚠️ Aqui o sinal NÃO se inverte, ao contrário do ajuste de
                    custo: falta baixa o estoque final, e o CMV é
                    `inicial + compras − final` — menos estoque, CMV maior. */}
                {previaSaldo.efeito_no_cmv !== 0 && (
                  <>
                    Isto {previaSaldo.efeito_no_cmv > 0 ? "AUMENTA" : "REDUZ"} o CMV do
                    período em <b>{reais(Math.abs(previaSaldo.efeito_no_cmv))}</b>.
                  </>
                )}
              </Aviso>
            </div>
          )}

          {tipo === "custo" && previaCusto && (
            <div className="mt-4">
              <Aviso tipo="info">
                <b>{previaCusto.produto}</b>: {qtd(previaCusto.saldo)} {previaCusto.um} a{" "}
                {reais(previaCusto.custo_atual)} valem {reais(previaCusto.valor_atual)}. A{" "}
                {reais(previaCusto.custo_novo)} passam a valer{" "}
                {reais(previaCusto.valor_novo)} —{" "}
                <b>
                  {previaCusto.diferenca >= 0 ? "+" : ""}
                  {reais(previaCusto.diferenca)}
                </b>{" "}
                no estoque, o que{" "}
                {previaCusto.efeito_no_cmv < 0 ? "REDUZ" : "AUMENTA"} o CMV do período em{" "}
                <b>{reais(Math.abs(previaCusto.efeito_no_cmv))}</b>.
              </Aviso>
            </div>
          )}
        </Cartao>
      )}

      <Cartao
        titulo="Últimos ajustes"
        descricao="O que foi lançado à mão — conferir aqui evita o ajuste em dobro."
      >
        {!recentes ? (
          <Carregando />
        ) : !recentes.length ? (
          <Vazio>Nenhum ajuste lançado ainda.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Quando</th>
                  <th>O quê</th>
                  <th>Produto</th>
                  <th className="num">Qtd</th>
                  <th className="num">Custo total</th>
                  <th>Quem</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {recentes.map((m) => (
                  <tr key={m.id} className={m.estornado ? "opacity-55" : ""}>
                    <td className="mono whitespace-nowrap text-[13px]">
                      {new Date(m.data_movimento).toLocaleString("pt-BR", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td>
                      <span className="whitespace-nowrap">{m.rotulo}</span>
                      {m.motivo && (
                        <span className="block text-[12.5px] text-suave">{m.motivo}</span>
                      )}
                      {m.estornado && (
                        <span className="block">
                          <Etiqueta cor="alerta">estornado</Etiqueta>
                        </span>
                      )}
                    </td>
                    <td>
                      {m.produto}
                      <span className="block text-[12.5px] text-suave">{m.local}</span>
                    </td>
                    <td className={`num ${Number(m.quantidade) < 0 ? "text-erro" : "text-erva"}`}>
                      {Number(m.quantidade) > 0 ? "+" : ""}
                      {qtd(m.quantidade)}
                    </td>
                    <td className="num">{reais(Number(m.custo_total))}</td>
                    <td className="text-[13px] text-suave">{m.usuario ?? "—"}</td>
                    <td className="num">
                      {!m.estornado && pode("estoque.ajuste") && (
                        <button
                          className="link-acao link-acao-erro"
                          onClick={() => setConfirmando(m)}
                        >
                          estornar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      {confirmando && (
        <Confirmacao
          titulo="Confirmar o estorno"
          rotuloConfirmar="Estornar"
          perigo
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => {
            const m = confirmando;
            setConfirmando(null);
            void estornar(m);
          }}
        >
          <p>
            Estornar <b>{confirmando.rotulo}</b> de <b>{confirmando.produto}</b>?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            O movimento original CONTINUA no razão — o estorno entra como a contrapartida,
            apontando para ele. É assim que o histórico segue fiel ao que aconteceu.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
