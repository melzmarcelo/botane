"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

/**
 * O código de barras que a NOTA já trouxe, e que o cadastro não tem.
 *
 * 🔑 **A maior fonte gratuita de EAN é a própria compra** (08/09/2026). Medido
 * na base real: 2.019 dos 3.183 produtos não têm código de barras nenhum — e
 * nenhuma API de GTIN ajuda quem não tem o número. O XML da NF-e traz `cEAN`,
 * o parser já o guarda, e ele ficava parado ali.
 *
 * 🔑 **Esta tela SUGERE; quem decide é quem está olhando** — a mesma distinção
 * da tela de duplicados, e pelo mesmo motivo: o sinal é forte, mas é um sinal.
 *
 * ⚠️ **A armadilha que exige a confirmação humana**: `cEAN` é o GTIN da unidade
 * COMERCIAL. Se a nota vende caixa com 12, o código é o da CAIXA — e gravá-lo
 * no produto rotula errado o que se conta na prateleira. Por isso a linha
 * mostra a unidade da nota ao lado da do estoque, e marca quando divergem.
 */

type Linha = {
  id_produto: number;
  codigo: string;
  nome: string;
  um_estoque: string | null;
  codigo_barras: string;
  um_nota: string | null;
  descricao_fornecedor: string | null;
  nota: string | null;
  data_emissao: string | null;
  fornecedor: string | null;
  unidade_diverge: boolean;
};

type Conflito = Omit<Linha, "unidade_diverge"> & { motivo: string };

type Resposta = {
  linhas: Linha[];
  conflitos: Conflito[];
  total: number;
  com_unidade_diferente: number;
};

export default function PaginaEanDasNotas() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const podeEditar = pode("cadastros.produtos");

  const [dados, setDados] = useState<Resposta | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [gravando, setGravando] = useState(false);
  // ⚠️ **Nasce VAZIO, não marcado.** Marcar tudo por padrão faria o clique de
  // "aplicar" gravar centenas de códigos que ninguém olhou — que é exatamente
  // o que esta tela existe para não fazer.
  const [escolhidos, setEscolhidos] = useState<Set<number>>(new Set());

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const r = await api.get<Resposta>("/produtos/ean-das-notas");
      setDados(r);
      setEscolhidos(new Set());
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível carregar");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  function alternar(id: number) {
    setEscolhidos((atual) => {
      const proximo = new Set(atual);
      if (proximo.has(id)) proximo.delete(id);
      else proximo.add(id);
      return proximo;
    });
  }

  async function aplicar() {
    setGravando(true);
    try {
      const r = await api.post<{ gravados: number; message: string }>(
        "/produtos/ean-das-notas",
        { ids_produto: [...escolhidos] },
      );
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar");
    } finally {
      setGravando(false);
    }
  }

  const linhas = dados?.linhas ?? [];
  const conflitos = dados?.conflitos ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/produtos" className="link-voltar">
          produtos
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Código de barras das notas
        </h1>
        <p className="mt-1 text-suave">
          O EAN que o fornecedor declarou na nota fiscal, para os produtos que não
          têm nenhum cadastrado.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {carregando ? (
        <Carregando />
      ) : (
        <>
          <Cartao
            titulo={`${linhas.length} produto(s) podem ganhar código`}
            descricao="Nada é gravado sem você marcar e confirmar."
          >
            {!linhas.length ? (
              <Vazio>
                Nenhum produto sem código de barras aparece em nota com EAN. Ou já
                está tudo preenchido, ou as notas desses produtos não trouxeram o
                código — muitos fornecedores mandam “SEM GTIN”.
              </Vazio>
            ) : (
              <div className="flex flex-col gap-4">
                {/* ⚠️ **O aviso da CAIXA vem antes da lista**, não depois: é a
                    única coisa que faria alguém desmarcar uma linha, e depois da
                    tabela ninguém leria. */}
                {!!dados?.com_unidade_diferente && (
                  <Aviso tipo="info">
                    <b>{dados.com_unidade_diferente}</b> linha(s) vêm de uma nota em
                    unidade diferente da de estoque. Nesses casos o código pode ser
                    o da <b>embalagem</b> (a caixa), não o da unidade que você conta
                    na prateleira — confira antes de marcar.
                  </Aviso>
                )}

                <div className="overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th className="w-8"></th>
                        <th>Produto</th>
                        <th>Código de barras</th>
                        <th>Unidade</th>
                        <th>De onde veio</th>
                      </tr>
                    </thead>
                    <tbody>
                      {linhas.map((l) => (
                        <tr key={l.id_produto}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Aplicar em ${l.nome}`}
                              checked={escolhidos.has(l.id_produto)}
                              onChange={() => alternar(l.id_produto)}
                              disabled={!podeEditar}
                            />
                          </td>
                          <td>
                            <Link
                              href={`/produtos/${l.id_produto}`}
                              className="link-registro"
                            >
                              {l.nome}
                            </Link>
                            <span className="block text-[12.5px] text-suave">
                              {l.codigo}
                            </span>
                          </td>
                          <td className="mono">{l.codigo_barras}</td>
                          <td>
                            {l.unidade_diverge ? (
                              <>
                                <Etiqueta cor="alerta">
                                  nota {l.um_nota} · estoque {l.um_estoque}
                                </Etiqueta>
                                <span className="block text-[12.5px] text-suave">
                                  pode ser o código da embalagem
                                </span>
                              </>
                            ) : (
                              <span className="text-suave">{l.um_estoque}</span>
                            )}
                          </td>
                          <td className="text-[13px] text-suave">
                            {l.fornecedor ?? "—"}
                            <span className="block">
                              nota {l.nota ?? "—"}
                              {l.descricao_fornecedor
                                ? ` · ${l.descricao_fornecedor}`
                                : ""}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {podeEditar && (
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      className="btn btn-primario"
                      disabled={gravando || escolhidos.size === 0}
                      onClick={() => void aplicar()}
                    >
                      {gravando
                        ? "Gravando…"
                        : `Aplicar em ${escolhidos.size} produto(s)`}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secundario"
                      onClick={() =>
                        setEscolhidos(new Set(linhas.map((l) => l.id_produto)))
                      }
                    >
                      Marcar todos
                    </button>
                    {escolhidos.size > 0 && (
                      <button
                        type="button"
                        className="btn btn-secundario"
                        onClick={() => setEscolhidos(new Set())}
                      >
                        Limpar
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </Cartao>

          {/* 🔑 **Os conflitos ficam à vista, e não escondidos.** Sumir com eles
              faria a conta não fechar: quem vê "80 produtos sem código" e uma
              lista de 60 quer saber dos outros 20. E cada motivo aponta um
              problema real do cadastro — de-para errado ou EAN digitado errado
              pelo emitente. */}
          {!!conflitos.length && (
            <Cartao
              titulo={`${conflitos.length} não dá para aplicar`}
              descricao="O código existe na nota, mas não pode ser gravado — cada linha diz por quê."
            >
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Produto</th>
                      <th>Código na nota</th>
                      <th>Por quê</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conflitos.map((c) => (
                      <tr key={`${c.id_produto}-${c.codigo_barras}`}>
                        <td>
                          <Link
                            href={`/produtos/${c.id_produto}`}
                            className="link-registro"
                          >
                            {c.nome}
                          </Link>
                        </td>
                        <td className="mono">{c.codigo_barras}</td>
                        <td className="text-[13px] text-suave">{c.motivo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Cartao>
          )}
        </>
      )}
    </div>
  );
}
