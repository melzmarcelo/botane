"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";

/**
 * Cadastros que parecem ser o mesmo produto.
 *
 * O sistema recebe produto por três portas — o catálogo do Omie (o que a casa
 * compra), o cardápio do PDV (o que a casa vende) e a mão de quem cadastra.
 * Nenhuma chave impede o mesmo produto de existir duas vezes: entre portas não
 * há chave nenhuma, e dentro de uma a chave garante que o *identificador* não
 * repita, não que o *produto* não repita.
 *
 * ⚠️ **O estrago tem duas formas.** Entre portas, é estoque fantasma: a compra
 * entra por um cadastro, a venda não sai por nenhum (o item do cardápio nasce
 * sem controlar estoque) e a sobra aparece na contagem como "ajuste de
 * inventário". Dentro de uma, é custo partido: a próxima compra vai para o
 * gêmeo e o custo médio passa a existir em vários lugares.
 *
 * ⚠️ **A tela SUGERE; quem decide é gente.** Unir dois produtos diferentes de
 * verdade não tem desfazer.
 */

type Cadastro = {
  id: number;
  codigo: string;
  nome: string;
  origem: string;
  tipo: string;
  status: string;
  categoria: string | null;
  um_estoque: string | null;
  controla_estoque: boolean;
  movimentos: number;
  fichas: number;
  vendido: number;
  pode_ser_absorvido: boolean;
};

type Grupo = { score: number; quantos: number; origens: string[]; cadastros: Cadastro[] };
type Resposta = { minimo: number; total: number; grupos: Grupo[] };

const ORIGENS: Record<string, string> = {
  OMIE: "Omie",
  PDV: "cardápio",
  CASA: "cadastrado aqui",
  AMBOS: "Omie + cardápio",
};

/** O que este cadastro carrega de passado — é por isto que se escolhe qual fica. */
function historia(c: Cadastro): string {
  const partes: string[] = [];
  if (c.movimentos) partes.push(`${c.movimentos} movimento(s)`);
  if (c.fichas) partes.push(`${c.fichas} ficha(s)`);
  if (c.vendido) partes.push(`${c.vendido} vendido(s)`);
  return partes.join(" · ");
}

export default function PaginaDuplicados() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeUnificar = pode("cadastros.produtos");

  const [dados, setDados] = useState<Resposta | null>(null);
  const [erro, setErro] = useState("");
  const [minimo, setMinimo] = useState(80);
  const [soEntrePortas, setSoEntrePortas] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [confirmando, setConfirmando] = useState<{ manter: Cadastro; absorver: Cadastro } | null>(
    null,
  );

  const carregar = useCallback(async () => {
    setDados(null);
    try {
      setDados(
        await api.get<Resposta>(
          `/produtos/duplicados?minimo=${minimo}&so_entre_portas=${soEntrePortas}`,
        ),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [minimo, soEntrePortas]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function unificar(manter: Cadastro, absorver: Cadastro) {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/produtos/${manter.id}/unificar`, {
        id_absorver: absorver.id,
      });
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível unificar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/produtos" className="link-voltar">
          produtos
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Possíveis duplicados
        </h1>
        <p className="mt-2 max-w-[72ch] text-suave">
          O mesmo produto pode ter mais de um cadastro — entrando por portas diferentes (o
          catálogo do Omie e o cardápio do PDV) ou repetido dentro da mesma. A chave única
          garante que o <b>código</b> não repita; não que o produto não repita.
        </p>
      </header>

      {/* ⚠️ O aviso é a razão de a tela existir, e vem antes da lista: sem ele,
          "dois cadastros parecidos" parece questão de arrumação. */}
      <Aviso tipo="info">
        Duplicado não avisa — ele vira número errado. Entre portas: a compra entra no estoque
        por um cadastro e a venda não sai por nenhum, então a sobra aparece na contagem como{" "}
        <b>ajuste de inventário</b>. Dentro de uma: a próxima compra vai para o gêmeo e o{" "}
        <b>custo médio passa a existir em vários lugares</b> — cada ficha puxa o de um deles.
      </Aviso>

      <Cartao
        titulo={dados ? `${dados.total} grupo(s)` : "Conferindo"}
        descricao="Cada grupo é um produto que aparece mais de uma vez. Confira antes de unificar."
        acao={
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-[13.5px]">
              <input
                type="checkbox"
                className="h-4 w-4 accent-erva"
                checked={soEntrePortas}
                onChange={(e) => setSoEntrePortas(e.target.checked)}
              />
              só entre Omie e cardápio
            </label>
            <select
              className="campo max-w-[170px]"
              value={minimo}
              onChange={(e) => setMinimo(Number(e.target.value))}
            >
              <option value={95}>a partir de 95%</option>
              <option value={90}>a partir de 90%</option>
              <option value={80}>a partir de 80%</option>
              <option value={70}>a partir de 70%</option>
            </select>
          </div>
        }
      >
        {!dados ? (
          <Carregando />
        ) : !dados.grupos.length ? (
          <Vazio>
            Nenhum grupo acima de {minimo}%
            {soEntrePortas ? " entre o Omie e o cardápio" : ""}. Cada produto tem um cadastro
            só — ou os nomes são diferentes demais para o palpite valer.
          </Vazio>
        ) : (
          <div className="flex flex-col gap-4">
            {dados.grupos.map((g, i) => (
              <div key={i} className="rounded border border-linha p-4">
                <p className="rotulo mb-3">
                  {g.quantos} cadastros · {g.score}% parecidos ·{" "}
                  {g.origens.map((o) => ORIGENS[o] ?? o).join(" + ")}
                </p>
                <ul className="flex flex-col gap-px bg-linha">
                  {g.cadastros.map((c, n) => (
                    <li
                      key={c.id}
                      className="flex flex-wrap items-center justify-between gap-3 bg-superficie py-2"
                    >
                      <div className="min-w-0">
                        <Link
                          href={`/produtos/${c.id}`}
                          className="font-semibold hover:text-erva"
                        >
                          {c.nome}
                        </Link>
                        <span className="block text-[12.5px] text-suave">
                          <span className="mono">{c.codigo}</span> ·{" "}
                          {ORIGENS[c.origem] ?? c.origem} · {c.tipo.toLowerCase()}
                          {c.um_estoque ? ` · ${c.um_estoque}` : " · sem unidade"}
                          {c.controla_estoque ? " · controla estoque" : ""}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {historia(c) ? (
                          <Etiqueta cor="erva">{historia(c)}</Etiqueta>
                        ) : (
                          <span className="text-[12.5px] text-suave">sem história</span>
                        )}
                        {/* ⚠️ O botão fica no cadastro que FICA e o diálogo diz o
                            nome do que sai — "unificar" sozinho não deixa claro
                            quem some, e escolher a direção errada é o engano
                            natural aqui. O primeiro da lista é o que carrega
                            mais passado; a sugestão está na ordem, não travada. */}
                        {podeUnificar && g.quantos > 1 && n > 0 && (
                          <button
                            className="btn btn-secundario"
                            disabled={ocupado || !c.pode_ser_absorvido}
                            title={
                              c.pode_ser_absorvido
                                ? `Absorver em “${g.cadastros[0].nome}”`
                                : "Tem história e não pode ser absorvido"
                            }
                            onClick={() =>
                              setConfirmando({ manter: g.cadastros[0], absorver: c })
                            }
                          >
                            Absorver no primeiro
                          </button>
                        )}
                        {n === 0 && <Etiqueta cor="neutro">sugerido manter</Etiqueta>}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Cartao>

      {confirmando && (
        <Confirmacao
          titulo="Unificar os dois cadastros"
          rotuloConfirmar="Unificar"
          perigo
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => {
            const c = confirmando;
            setConfirmando(null);
            void unificar(c.manter, c.absorver);
          }}
        >
          <p>
            Fica <b>{confirmando.manter.nome}</b> e sai <b>{confirmando.absorver.nome}</b>.
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            O vínculo com o PDV, o código do Omie, o EAN e os itens de venda passam para o que
            fica. O outro vira <b>inativo</b> — não é apagado, porque a auditoria continua
            apontando para ele.
          </p>
          <p className="mt-2 text-[13.5px] text-suave">
            As vendas que já passaram <b>não</b> baixam estoque retroativamente: o razão é
            append-only e inventar lançamento no passado seria pior que a falta dele. O que isto
            conserta é daqui para a frente.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
