"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Etiqueta } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";

/**
 * Dizer que outros cadastros são o mesmo produto que este — e fundir todos.
 *
 * 🔑 **VÁRIOS de uma vez, porque o caso é o ABACATE.** O catálogo do Omie cria
 * um cadastro por CÓDIGO, e o mesmo abacate aparece uma vez para cada
 * fornecedor que já o vendeu. Juntar um a um seria abrir esta janela cinco
 * vezes, e a quinta já não lembraria o que a primeira decidiu.
 *
 * 🔑 **E o "Como fica" mostra as LINHAS DE CÓDIGO EXTERNO que vão sobrar.** É o
 * que faz a fusão ser confiável aqui: o código do Omie de cada absorvido não se
 * perde — ele vira um apelido do principal, e é por ele que a próxima nota
 * daquele fornecedor cai no cadastro certo, sem criar o duplicado de novo.
 *
 * ⚠️ **Nada aqui adivinha.** Existiu uma tela que cruzava os nomes por
 * semelhança, e ela errava nos dois sentidos: não achava "BEB CERV HEINEKEN
 * 350ML" contra "CERVEJA HEINEKEN PILSEN" (63,8% — o mesmo produto) e juntava
 * "CAKE BOARD N19" com "CAKE BOARD N21", que são tamanhos diferentes. Nenhum
 * piso de semelhança separa os dois casos, porque a diferença não está no
 * texto. Quem reconhece produto é quem está olhando a tela.
 *
 * ⚠️ **A prévia vem antes do botão, sempre.** Fusão não tem desfazer.
 */

type Lado = {
  id: number;
  codigo: string;
  nome: string;
  nome_curto: string | null;
  tipo: string;
  status: string;
  categoria: string | null;
  um_estoque: string | null;
  controla_estoque: boolean;
  codigo_omie: string | null;
  codigo_pdv: string | null;
  movimentos: number;
  fichas: number;
  vendido: number;
};

type LinhaDeCodigo = {
  sistema: string;
  codigo: string;
  /** "principal" · "vira apelido" · "já aponta" */
  origem: string;
  descricao: string | null;
};

type Previa = {
  fica: Lado;
  sai: Lado;
  impedimentos: string[];
  pode: boolean;
  /** A direção foi resolvida pelos FATOS, e pode não ser a da tela. */
  invertido: boolean;
  motivo_da_direcao: string | null;
  resultado: {
    nome: string;
    nome_curto: string | null;
    de_onde: { nome: string; nome_curto: string };
    codigo_omie: string | null;
    codigo_pdv: string | null;
    codigo_barras: string | null;
  };
  codigos_externos: LinhaDeCodigo[];
  itens_de_venda: number;
  /** O que foi vendido pelo absorvido e nunca saiu do estoque. */
  baixa: {
    quantidade: number;
    um: string | null;
    saldo_atual: number;
    saldo_depois: number;
    fica_negativo: boolean;
    local: string | null;
  } | null;
  completa: string[];
  id_fica: number;
  id_sai: number;
};

const PRODUTOS = fonteProdutos();

const DE_ONDE: Record<string, string> = {
  omie: "do cadastro do Omie",
  pdv: "do cadastro do PDV",
  "cadastro que fica": "do cadastro que fica",
};

const SISTEMA: Record<string, string> = {
  OMIE: "código na nota do fornecedor",
  OMIE_PRODUTO: "código do produto no Omie",
  PDV_LEGAL: "código no cardápio do PDV",
};

/** O que este cadastro carrega de passado — é o que decide qual dos dois fica. */
function historia(l: Lado): string {
  const partes: string[] = [];
  if (l.movimentos) partes.push(`${l.movimentos} movimento(s) no razão`);
  if (l.fichas) partes.push(`${l.fichas} ficha(s)`);
  if (l.vendido) partes.push(`${l.vendido} vendido(s)`);
  return partes.join(" · ");
}

export default function Vincular({
  idProduto,
  aoFechar,
  aoFundir,
}: {
  idProduto: number;
  aoFechar: () => void;
  aoFundir: () => void;
}) {
  const aviso = useAviso();
  // 🔑 Uma LISTA: o abacate do catálogo do Omie tem um cadastro por fornecedor,
  // e juntar um a um seria abrir esta janela cinco vezes.
  const [escolhidos, setEscolhidos] = useState<{ id: number; rotulo: string }[]>([]);
  // ⚠️ LIGADO por padrão: sem a baixa, o resultado seria "comprou 15, vendeu 10,
  // saldo 15", e as 10 faltando apareceriam na primeira contagem como ajuste de
  // inventário — onde a diferença some sem nome.
  const [baixar, setBaixar] = useState(true);
  const [previas, setPrevias] = useState<Previa[]>([]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const conferir = useCallback(async () => {
    setErro("");
    if (!escolhidos.length) {
      setPrevias([]);
      return;
    }
    try {
      // ⚠️ Uma prévia POR cadastro: a direção é resolvida pelos fatos de cada
      // par, e um deles pode inverter — é isso que a tela precisa mostrar.
      setPrevias(
        await Promise.all(
          escolhidos.map((e) =>
            api.get<Previa>(`/produtos/${idProduto}/vincular/previa?id_sai=${e.id}`),
          ),
        ),
      );
    } catch (e) {
      setPrevias([]);
      setErro(e instanceof Error ? e.message : "Não foi possível conferir");
    }
  }, [escolhidos, idProduto]);

  useEffect(() => {
    void conferir();
  }, [conferir]);

  function acrescentar(item: ItemBusca | null) {
    if (!item) return;
    if (item.id === idProduto) {
      setErro("É o mesmo cadastro. Escolha outro.");
      return;
    }
    setErro("");
    setEscolhidos((a) => (a.some((x) => x.id === item.id)
      ? a
      : [...a, { id: item.id, rotulo: rotuloDe(item) }]));
  }

  const principal = previas[0]?.fica ?? null;
  // ⚠️ **Todos têm de cair no MESMO principal.** A direção é dos fatos: um
  // cadastro com história puxa a fusão para o lado dele, e aí o sobrevivente
  // seria outro. Misturar isso num lote só faria a pessoa confirmar uma coisa
  // e acontecer outra.
  const divergentes = previas.filter((p) => principal && p.id_fica !== principal.id);
  const travados = previas.filter((p) => !p.pode);
  const podeFundir = !!previas.length && !divergentes.length && !travados.length;

  // As linhas de código do resultado, juntando todas as prévias sem repetir.
  const codigos: LinhaDeCodigo[] = [];
  for (const p of previas) {
    for (const c of p.codigos_externos ?? []) {
      if (!codigos.some((x) => x.sistema === c.sistema && x.codigo === c.codigo)) {
        codigos.push(c);
      }
    }
  }
  const comBaixa = previas.filter((p) => p.baixa);

  async function fundir() {
    setOcupado(true);
    let feitos = 0;
    try {
      // ⚠️ **Um pedido por cadastro, em ordem.** Cada fusão é a mesma operação
      // repetida, e parar no meio deixa as anteriores feitas — que é um estado
      // bom, não um pela metade. A mensagem diz quantas foram.
      for (const p of previas) {
        await api.post(`/produtos/${idProduto}/vincular`, {
          id_sai: p.id_sai,
          baixar_vendas: baixar,
        });
        feitos += 1;
      }
      aviso.sucesso(
        feitos === 1
          ? `“${previas[0].sai.nome}” foi fundido em “${previas[0].fica.nome}”.`
          : `${feitos} cadastros foram fundidos em “${previas[0].fica.nome}”.`,
      );
      aoFundir();
    } catch (e) {
      aviso.erro(
        (e instanceof Error ? e.message : "Não foi possível vincular")
        + (feitos ? ` — ${feitos} já tinha(m) sido fundido(s) antes da falha.` : ""),
      );
      if (feitos) aoFundir();
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8">
      <div className="w-full max-w-[720px] rounded-[14px] border border-linha bg-superficie p-5 shadow-lg">
        <p className="rotulo">Vincular cadastros</p>
        <h2 className="mt-1 text-[20px] font-bold tracking-tight">
          Que outros cadastros são este mesmo produto?
        </h2>
        <p className="mt-2 text-[13.5px] leading-snug text-suave">
          O que você escolher será <b>fundido neste</b> e ficará inativo. A descrição fica com o
          nome do lado do Omie e a descrição curta com o do PDV; os campos em branco se
          completam, e <b>o código de cada absorvido continua caindo aqui</b> — é por ele que a
          próxima nota daquele fornecedor entra no cadastro certo.
        </p>

        <div className="mt-4">
          <Campo
            rotulo="Acrescentar cadastro"
            dica="código ou nome — pode escolher vários, um de cada vez"
          >
            {/* ⚠️ **`key` para REMONTAR o campo a cada escolha.** Ele guarda o
                texto digitado em estado próprio e só o sincroniza quando o
                `selecionado` muda — passando `null` sempre, o nome do produto
                anterior ficaria no campo depois de acrescentado, e o próximo
                seria digitado por cima dele. */}
            <BuscaCadastro
              key={escolhidos.length}
              fonte={PRODUTOS}
              selecionado={null}
              aoEscolher={acrescentar}
            />
          </Campo>
        </div>

        {!!escolhidos.length && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {escolhidos.map((e) => (
              <li key={e.id}>
                <span className="inline-flex items-center gap-2 rounded-full border border-linha px-3 py-1 text-[13px]">
                  {e.rotulo}
                  <button
                    type="button"
                    aria-label={`tirar ${e.rotulo}`}
                    className="text-suave"
                    onClick={() => setEscolhidos((a) => a.filter((x) => x.id !== e.id))}
                  >
                    ×
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        {erro && (
          <div className="mt-4">
            <Aviso tipo="erro">{erro}</Aviso>
          </div>
        )}

        {!!previas.length && (
          <div className="mt-5 flex flex-col gap-4">
            {/* ⚠️ O que TRAVA vem antes de tudo: com história do lado errado, a
                fusão não acontece, e a pessoa precisa saber disso antes de ler o
                resultado que não vai valer. */}
            {travados.map((p) => (
              <Aviso key={`trava-${p.id_sai}`} tipo="erro">
                <b>{p.sai.nome}</b> não pode ser absorvido: {p.impedimentos.join("; ")}. Juntar
                duas histórias de estoque exigiria reescrever o razão, que é append-only. Tire
                este da lista — o código dele ainda pode apontar para cá pelo item da nota.
              </Aviso>
            ))}

            {/* ⚠️ **A direção é dos FATOS, não da tela**, e num lote isso vira
                trava: se um dos escolhidos puxa a fusão para o lado dele, o
                sobrevivente seria outro e a pessoa confirmaria uma coisa
                acontecendo outra. */}
            {divergentes.map((p) => (
              <Aviso key={`inv-${p.id_sai}`} tipo="erro">
                <b>{p.sai.nome}</b> ficaria como o cadastro principal, e não este — porque{" "}
                {p.motivo_da_direcao}. Tire-o da lista e refaça a partir dele.
              </Aviso>
            ))}

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[10px] border border-linha p-3">
                <p className="rotulo">Fica</p>
                <p className="mt-1 font-semibold">{principal?.nome}</p>
                <p className="text-[12.5px] text-suave">
                  <span className="mono">{principal?.codigo}</span> ·{" "}
                  {principal?.tipo.toLowerCase()}
                  {principal?.um_estoque ? ` · ${principal.um_estoque}` : " · sem unidade"}
                  {principal?.controla_estoque ? " · controla estoque" : ""}
                </p>
                <p className="mt-1.5 text-[12.5px]">
                  {principal && historia(principal) ? (
                    <Etiqueta cor="erva">{historia(principal)}</Etiqueta>
                  ) : (
                    <span className="text-suave">sem história</span>
                  )}
                </p>
              </div>

              <div className="rounded-[10px] border border-linha p-3">
                <p className="rotulo">Sai (vira inativo)</p>
                <ul className="mt-1 flex flex-col gap-2">
                  {previas.map((p) => (
                    <li key={p.id_sai}>
                      <p className="font-semibold">{p.sai.nome}</p>
                      <p className="text-[12.5px] text-suave">
                        <span className="mono">{p.sai.codigo}</span> · Omie{" "}
                        <b>{p.sai.codigo_omie ?? "—"}</b> · PDV <b>{p.sai.codigo_pdv ?? "—"}</b>
                      </p>
                      {historia(p.sai) && (
                        <p className="mt-0.5 text-[12.5px]">
                          <Etiqueta cor="alerta">{historia(p.sai)}</Etiqueta>
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="rounded-[10px] border border-linha bg-fundo p-3">
              <p className="rotulo">Como fica</p>
              <dl className="mt-2 grid gap-1.5 text-[13.5px]">
                <div className="flex flex-wrap gap-x-2">
                  <dt className="text-suave">descrição</dt>
                  <dd className="font-semibold">{previas[0].resultado.nome}</dd>
                  <dd className="text-[12.5px] text-suave">
                    (
                    {DE_ONDE[previas[0].resultado.de_onde.nome]
                      ?? previas[0].resultado.de_onde.nome}
                    )
                  </dd>
                </div>
                <div className="flex flex-wrap gap-x-2">
                  <dt className="text-suave">descrição curta</dt>
                  <dd className="font-semibold">{previas[0].resultado.nome_curto ?? "—"}</dd>
                </div>
                {!!previas[0].completa.length && (
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-suave">completa</dt>
                    <dd>{previas[0].completa.join(", ")}</dd>
                  </div>
                )}
                {previas.some((p) => p.itens_de_venda > 0) && (
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-suave">itens de venda que mudam de dono</dt>
                    <dd>{previas.reduce((s, p) => s + p.itens_de_venda, 0)}</dd>
                  </div>
                )}
              </dl>

              {/* 🔑 **As linhas de código externo — o coração deste ajuste.** O
                  `codigo_omie` do absorvido era DESCARTADO na fusão, e a próxima
                  nota que o trouxesse não achava o principal: o item caía na
                  fila de pendências e quem clicasse em "criar produto" recriava
                  o duplicado. Aqui a pessoa vê, antes de confirmar, por quais
                  códigos este cadastro vai passar a responder. */}
              <p className="rotulo mt-4">Códigos que passam a cair neste cadastro</p>
              <div className="mt-1.5 overflow-x-auto">
                <table className="tabela" id="codigos-do-resultado">
                  <thead>
                    <tr>
                      <th>De onde</th>
                      <th>Código</th>
                      <th>Descrição</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {codigos.map((c) => (
                      <tr key={`${c.sistema}-${c.codigo}`}>
                        <td className="text-suave">{SISTEMA[c.sistema] ?? c.sistema}</td>
                        <td className="mono">{c.codigo}</td>
                        <td className="text-suave">{c.descricao ?? "—"}</td>
                        <td>
                          <Etiqueta cor={c.origem === "principal" ? "erva" : "neutro"}>
                            {c.origem}
                          </Etiqueta>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* ⚠️ **A baixa do que foi vendido e nunca saiu.** É o que fecha a
                  conta: o item do cardápio vendia sem baixar estoque, e sem esta
                  saída o saldo continuaria dizendo que a mercadoria está na
                  prateleira. O número aparece ANTES do botão — é movimento de
                  estoque, não pode ser surpresa. */}
              {comBaixa.length ? (
                <label className="mt-3 flex items-start gap-2 rounded-[10px] border border-linha bg-superficie p-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 accent-erva"
                    checked={baixar}
                    onChange={(e) => setBaixar(e.target.checked)}
                  />
                  <span className="text-[13px] leading-snug">
                    Baixar do estoque o que foi vendido e nunca saiu da prateleira:
                    <span className="mt-1 block">
                      {comBaixa.map((p) => (
                        <span key={p.id_sai} className="block text-suave">
                          <b>{p.sai.nome}</b>: {p.baixa!.quantidade}
                          {p.baixa!.um ? ` ${p.baixa!.um}` : ""} · saldo{" "}
                          {p.baixa!.saldo_atual} → <b>{p.baixa!.saldo_depois}</b>
                          {p.baixa!.fica_negativo && (
                            <span className="text-alerta"> ⚠️ fica negativo</span>
                          )}
                        </span>
                      ))}
                    </span>
                    <span className="mt-1 block text-suave">
                      A saída entra com a data de <b>hoje</b>, não no passado.
                    </span>
                    {!baixar && (
                      <span className="mt-1 block text-suave">
                        Sem a baixa, essas unidades vão aparecer como <b>ajuste de inventário</b>{" "}
                        na primeira contagem.
                      </span>
                    )}
                  </span>
                </label>
              ) : (
                <p className="mt-3 text-[12.5px] leading-snug text-suave">
                  Nada a baixar do estoque: os cadastros que saem não têm venda, ou o que fica
                  não controla estoque.
                </p>
              )}
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-wrap gap-2">
          <button
            className="btn btn-primario"
            type="button"
            disabled={ocupado || !podeFundir}
            onClick={fundir}
          >
            {ocupado
              ? "Vinculando…"
              : previas.length > 1
                ? `Vincular e fundir os ${previas.length}`
                : "Vincular e fundir"}
          </button>
          <button className="btn btn-secundario" type="button" onClick={aoFechar}>
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
