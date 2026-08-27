"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Etiqueta } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";

/**
 * Dizer que outro cadastro é o mesmo produto que este — e fundir os dois.
 *
 * ⚠️ **Nada aqui adivinha.** Existiu uma tela que cruzava os nomes por
 * semelhança, e ela errava nos dois sentidos: não achava "BEB CERV HEINEKEN
 * 350ML" contra "CERVEJA HEINEKEN PILSEN" (63,8% — o mesmo produto) e juntava
 * "CAKE BOARD N19" com "CAKE BOARD N21", que são tamanhos diferentes. Nenhum
 * piso de semelhança separa os dois casos, porque a diferença não está no
 * texto. Quem reconhece produto é quem está olhando a tela.
 *
 * ⚠️ **A prévia vem antes do botão, sempre.** Fusão não tem desfazer: quem
 * confirma precisa ver com que nome o produto vai ficar, que campos serão
 * completados, quantos itens de venda mudam de dono — e, quando não dá, o que
 * exatamente trava.
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
};

const PRODUTOS = fonteProdutos();

const DE_ONDE: Record<string, string> = {
  omie: "do cadastro do Omie",
  pdv: "do cadastro do PDV",
  "cadastro que fica": "do cadastro que fica",
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
  const [escolhido, setEscolhido] = useState<{ id: number; rotulo: string } | null>(null);
  // ⚠️ LIGADO por padrão: sem a baixa, o resultado seria "comprou 15, vendeu 10,
  // saldo 15", e as 10 faltando apareceriam na primeira contagem como ajuste de
  // inventário — onde a diferença some sem nome.
  const [baixar, setBaixar] = useState(true);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const conferir = useCallback(async () => {
    setErro("");
    setPrevia(null);
    if (!escolhido) return;
    if (escolhido.id === idProduto) {
      setErro("É o mesmo cadastro. Escolha o outro.");
      return;
    }
    try {
      setPrevia(
        await api.get<Previa>(`/produtos/${idProduto}/vincular/previa?id_sai=${escolhido.id}`),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível conferir");
    }
  }, [escolhido, idProduto]);

  useEffect(() => {
    void conferir();
  }, [conferir]);

  async function fundir() {
    if (!escolhido) return;
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/produtos/${idProduto}/vincular`, {
        id_sai: escolhido.id,
        baixar_vendas: baixar,
      });
      aviso.sucesso(r.message);
      aoFundir();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível vincular");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8">
      <div className="w-full max-w-[720px] rounded border border-linha bg-superficie p-5 shadow-lg">
        <p className="rotulo">Vincular cadastros</p>
        <h2 className="mt-1 text-[20px] font-bold tracking-tight">
          Qual outro cadastro é este mesmo produto?
        </h2>
        <p className="mt-2 text-[13.5px] leading-snug text-suave">
          O que você escolher será <b>fundido neste</b> e ficará inativo. A descrição fica com o
          nome do lado do Omie e a descrição curta com o do PDV; os códigos das duas integrações
          passam para cá, e os campos em branco se completam.
        </p>

        <div className="mt-4">
          <Campo rotulo="O outro cadastro" dica="código ou nome — a semelhança não importa">
            <BuscaCadastro
              fonte={PRODUTOS}
              selecionado={escolhido}
              aoEscolher={(item: ItemBusca | null) =>
                setEscolhido(item ? { id: item.id, rotulo: rotuloDe(item) } : null)
              }
            />
          </Campo>
        </div>

        {erro && (
          <div className="mt-4">
            <Aviso tipo="erro">{erro}</Aviso>
          </div>
        )}

        {previa && (
          <div className="mt-5 flex flex-col gap-4">
            {/* ⚠️ O que TRAVA vem antes de tudo: com história do lado errado, a
                fusão não acontece, e a pessoa precisa saber disso antes de ler o
                resultado que não vai valer. */}
            {!previa.pode && (
              <Aviso tipo="erro">
                Os dois cadastros têm história e nenhum pode ser absorvido —{" "}
                <b>{previa.sai.nome}</b> {previa.impedimentos.join("; ")}. Juntar duas histórias
                de estoque exigiria reescrever o razão, que é append-only. Desative um deles à
                mão e siga com o outro.
              </Aviso>
            )}

            {/* ⚠️ **A direção é dos FATOS, não da tela.** Antes, escolher um
                cadastro com história levava "não pode ser absorvido… faça a
                fusão a partir dele" — uma recusa que já sabia a resposta e ainda
                exigia refazer o caminho. Agora o sistema resolve e DIZ por quê:
                trocar a direção calado seria pior, porque a pessoa confirmaria
                achando que o cadastro que abriu é o que fica. */}
            {previa.invertido && (
              <Aviso tipo="info">
                A direção foi invertida: <b>{previa.fica.nome}</b> é que fica, porque{" "}
                {previa.motivo_da_direcao}. O cadastro que você abriu é o que sai.
              </Aviso>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              {[
                { rotulo: "Fica", lado: previa.fica },
                { rotulo: "Sai (vira inativo)", lado: previa.sai },
              ].map(({ rotulo, lado }) => (
                <div key={rotulo} className="rounded border border-linha p-3">
                  <p className="rotulo">{rotulo}</p>
                  <p className="mt-1 font-semibold">{lado.nome}</p>
                  <p className="text-[12.5px] text-suave">
                    <span className="mono">{lado.codigo}</span> · {lado.tipo.toLowerCase()}
                    {lado.um_estoque ? ` · ${lado.um_estoque}` : " · sem unidade"}
                    {lado.controla_estoque ? " · controla estoque" : ""}
                  </p>
                  <p className="mt-1 text-[12.5px] text-suave">
                    Omie: <b>{lado.codigo_omie ?? "—"}</b> · PDV: <b>{lado.codigo_pdv ?? "—"}</b>
                  </p>
                  <p className="mt-1.5 text-[12.5px]">
                    {historia(lado) ? (
                      <Etiqueta cor="erva">{historia(lado)}</Etiqueta>
                    ) : (
                      <span className="text-suave">sem história</span>
                    )}
                  </p>
                </div>
              ))}
            </div>

            <div className="rounded border border-linha bg-fundo p-3">
              <p className="rotulo">Como fica</p>
              <dl className="mt-2 grid gap-1.5 text-[13.5px]">
                <div className="flex flex-wrap gap-x-2">
                  <dt className="text-suave">descrição</dt>
                  <dd className="font-semibold">{previa.resultado.nome}</dd>
                  <dd className="text-[12.5px] text-suave">
                    ({DE_ONDE[previa.resultado.de_onde.nome] ?? previa.resultado.de_onde.nome})
                  </dd>
                </div>
                <div className="flex flex-wrap gap-x-2">
                  <dt className="text-suave">descrição curta</dt>
                  <dd className="font-semibold">{previa.resultado.nome_curto ?? "—"}</dd>
                  <dd className="text-[12.5px] text-suave">
                    (
                    {DE_ONDE[previa.resultado.de_onde.nome_curto] ??
                      previa.resultado.de_onde.nome_curto}
                    )
                  </dd>
                </div>
                <div className="flex flex-wrap gap-x-2">
                  <dt className="text-suave">códigos</dt>
                  <dd>
                    Omie <b>{previa.resultado.codigo_omie ?? "—"}</b> · PDV{" "}
                    <b>{previa.resultado.codigo_pdv ?? "—"}</b>
                  </dd>
                </div>
                {!!previa.completa.length && (
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-suave">completa</dt>
                    <dd>{previa.completa.join(", ")}</dd>
                  </div>
                )}
                {previa.itens_de_venda > 0 && (
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-suave">itens de venda que mudam de dono</dt>
                    <dd>{previa.itens_de_venda}</dd>
                  </div>
                )}
              </dl>
              {/* ⚠️ **A baixa do que foi vendido e nunca saiu.** É o que fecha a
                  conta: o item do cardápio vendia sem baixar estoque, e sem esta
                  saída o saldo continuaria dizendo que a mercadoria está na
                  prateleira. O número aparece ANTES do botão, com o saldo que
                  vai sobrar — é movimento de estoque, não pode ser surpresa. */}
              {previa.baixa ? (
                <label className="mt-3 flex items-start gap-2 rounded border border-linha bg-superficie p-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 accent-erva"
                    checked={baixar}
                    onChange={(e) => setBaixar(e.target.checked)}
                  />
                  <span className="text-[13px] leading-snug">
                    Baixar do estoque as{" "}
                    <b>
                      {previa.baixa.quantidade}
                      {previa.baixa.um ? ` ${previa.baixa.um}` : ""}
                    </b>{" "}
                    que <b>{previa.sai.nome}</b> vendeu e nunca saíram da prateleira.
                    <span className="mt-1 block text-suave">
                      Saldo {previa.baixa.saldo_atual} → <b>{previa.baixa.saldo_depois}</b>
                      {previa.baixa.local ? ` em ${previa.baixa.local}` : ""} · a saída entra
                      com a data de <b>hoje</b>, não no passado.
                    </span>
                    {previa.baixa.fica_negativo && (
                      <span className="mt-1 block text-alerta">
                        ⚠️ O saldo fica <b>negativo</b>. O razão aceita — a saída sai por custo
                        provisório e a próxima entrada revaloriza —, mas vale conferir se a
                        compra correspondente já foi lançada.
                      </span>
                    )}
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
                  Nada a baixar do estoque: o cadastro que sai não tem venda, ou o que fica não
                  controla estoque.
                </p>
              )}
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-wrap gap-2">
          <button
            className="btn btn-primario"
            type="button"
            disabled={ocupado || !previa || !previa.pode}
            onClick={fundir}
          >
            {ocupado ? "Vinculando…" : "Vincular e fundir"}
          </button>
          <button className="btn btn-secundario" type="button" onClick={aoFechar}>
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
