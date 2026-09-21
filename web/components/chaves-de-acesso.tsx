"use client";

import { ReactNode, useCallback, useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta, Modal, Vazio } from "@/components/ui";
import { FonteDeChaves, TokenApi, TokenApiCriado, situacaoDoToken } from "@/lib/tokens-api";

const PRAZOS = [
  { dias: 30, rotulo: "30 dias" },
  { dias: 90, rotulo: "90 dias" },
  { dias: 180, rotulo: "6 meses" },
  { dias: 365, rotulo: "1 ano" },
];

const quando = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";

/**
 * As chaves de acesso de máquina de um usuário — o que o Claude usa para entrar.
 *
 * Dois lugares usam: o cadastro do usuário (administrador, com "Gerar chave") e
 * o Perfil (a própria pessoa, que vê e desconecta o Claude dela). Quem decide
 * o que dá para fazer é a `fonte` — sem `criar`, não há botão de gerar.
 *
 * 🔑 **A chave aparece UMA vez**, no cartão logo depois de gerada. O servidor só
 * guarda o hash; fechar o cartão sem copiar é gerar outra.
 * ⚠️ Só leitura: o servidor recusa qualquer alteração feita com ela, e a tela
 * diz isso para ninguém gerar uma chave esperando que o Claude lance nota.
 * ⚠️ `fonte` precisa ser ESTÁVEL entre renderizações (`useMemo` em quem chama):
 * ela entra na dependência do carregamento.
 */
export default function ChavesDeAcesso({
  fonte,
  titulo = "Chaves de acesso",
  descricao,
  topo,
}: {
  fonte: FonteDeChaves;
  titulo?: string;
  descricao: string;
  /** O que vem antes da lista — no Perfil, o endereço do conector. */
  topo?: ReactNode;
}) {
  const aviso = useAviso();
  const [chaves, setChaves] = useState<TokenApi[] | null>(null);
  const [erro, setErro] = useState("");
  const [gerando, setGerando] = useState(false);
  const [nome, setNome] = useState("Claude");
  const [dias, setDias] = useState(90);
  // ⚠️ Nasce SÓ LEITURA: alterar é a exceção, e quem gera tem de dizer que quer.
  const [podeAlterar, setPodeAlterar] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [criada, setCriada] = useState<TokenApiCriado | null>(null);
  const [revogando, setRevogando] = useState<TokenApi | null>(null);

  const carregar = useCallback(async () => {
    try {
      setChaves(await fonte.listar());
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar as chaves");
    }
  }, [fonte]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function gerar() {
    if (!fonte.criar) return;
    setOcupado(true);
    try {
      const c = await fonte.criar(nome.trim(), dias, !podeAlterar);
      setCriada(c);
      setGerando(false);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar a chave");
    } finally {
      setOcupado(false);
    }
  }

  async function revogar() {
    if (!revogando) return;
    setOcupado(true);
    try {
      await fonte.revogar(revogando.id);
      aviso.sucesso("Chave revogada — ela para de funcionar agora.");
      if (criada?.id === revogando.id) setCriada(null);
      setRevogando(null);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível revogar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao
      titulo={titulo}
      descricao={descricao}
      acao={
        fonte.criar && (
          <button type="button" className="btn btn-secundario" onClick={() => setGerando(true)}>
            Gerar chave
          </button>
        )
      }
    >
      {topo}

      {criada && (
        // ⚠️ `div` com a forma do `Aviso`, e não o `Aviso`: ele é um `<p>`, e
        // parágrafo com botões dentro é HTML inválido (erro de hidratação).
        <div className="aviso aviso-ok mb-4" role="status">
          <p className="font-semibold">Copie agora — esta chave não aparece de novo.</p>
          <p className="mono mt-2 break-all text-[13px]">{criada.token}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-secundario"
              onClick={() => {
                void navigator.clipboard.writeText(criada.token);
                aviso.sucesso("Chave copiada");
              }}
            >
              Copiar
            </button>
            <button type="button" className="link-acao" onClick={() => setCriada(null)}>
              já copiei, fechar
            </button>
          </div>
        </div>
      )}

      {erro ? (
        <Aviso tipo="erro">{erro}</Aviso>
      ) : !chaves ? (
        <Carregando />
      ) : !chaves.length ? (
        <Vazio>Nenhuma chave gerada.</Vazio>
      ) : (
        <div className="grid-rolante">
          <table className="tabela">
            <thead>
              <tr>
                <th>Chave</th>
                <th>Situação</th>
                <th>Vence</th>
                <th>Último uso</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {chaves.map((t) => {
                const s = situacaoDoToken(t);
                return (
                  <tr key={t.id} className={s === "viva" ? "" : "opacity-55"}>
                    <td>
                      <span className="font-semibold">{t.nome}</span>
                      <span className="ml-2 align-middle">
                        {t.origem === "oauth" && <Etiqueta>conectado pelo Claude</Etiqueta>}
                        {!t.somente_leitura && <Etiqueta cor="alerta">altera</Etiqueta>}
                      </span>
                      <span className="mono block text-[12.5px] text-suave">{t.prefixo}…</span>
                      <span className="block text-[12.5px] text-suave">
                        criada {quando(t.criado_em)}
                        {t.criado_por ? ` por ${t.criado_por}` : ""}
                      </span>
                    </td>
                    <td>
                      <Etiqueta cor={s === "viva" ? "erva" : "alerta"}>{s}</Etiqueta>
                    </td>
                    <td className="whitespace-nowrap">{quando(t.revogado_em ?? t.vence_em)}</td>
                    <td className="whitespace-nowrap">{t.ultimo_uso_em ? quando(t.ultimo_uso_em) : "nunca"}</td>
                    <td>
                      {s === "viva" && (
                        <button
                          type="button"
                          className="link-acao link-acao-erro"
                          onClick={() => setRevogando(t)}
                        >
                          revogar
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {gerando && (
        <Modal
          titulo="Gerar chave de acesso"
          descricao="A chave age como esta pessoa. Guarde-a como uma senha."
          aoFechar={() => setGerando(false)}
          largura="480px"
          rodape={
            <div className="flex justify-end gap-2">
              <button type="button" className="btn btn-secundario" onClick={() => setGerando(false)}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn-primario"
                onClick={() => void gerar()}
                disabled={ocupado || !nome.trim()}
                aria-busy={ocupado}
              >
                {ocupado ? "…" : "Gerar"}
              </button>
            </div>
          }
        >
          <div className="flex flex-col gap-4">
            <Campo rotulo="Para que é" dica="Um nome para reconhecer depois — ex.: “Claude do notebook”.">
              <input
                className="campo"
                value={nome}
                maxLength={80}
                onChange={(e) => setNome(e.target.value)}
                autoFocus
              />
            </Campo>
            {/* 🔑 A conexão feita pelo claude.ai é sempre só leitura; alterar só
                por uma chave gerada aqui, de propósito. */}
            <Campo rotulo="O que ela pode fazer">
              <select
                className="campo"
                value={podeAlterar ? "alterar" : "ler"}
                onChange={(e) => setPodeAlterar(e.target.value === "alterar")}
              >
                <option value="ler">Só consultar</option>
                <option value="alterar">Consultar e alterar cadastros</option>
              </select>
            </Campo>
            {podeAlterar && (
              <p className="aviso aviso-info text-[13.5px]" role="status">
                Com esta chave o Claude pode conciliar notas, corrigir e criar produtos e
                lançar notas no estoque — sempre como esta pessoa, e cada alteração fica
                marcada na Auditoria. Lançamento no estoque só se desfaz por estorno.
              </p>
            )}
            <Campo rotulo="Vale por">
              <select className="campo" value={dias} onChange={(e) => setDias(Number(e.target.value))}>
                {PRAZOS.map((p) => (
                  <option key={p.dias} value={p.dias}>
                    {p.rotulo}
                  </option>
                ))}
              </select>
            </Campo>
          </div>
        </Modal>
      )}

      {revogando && (
        <Confirmacao
          titulo="Revogar a chave?"
          rotuloConfirmar="Revogar"
          perigo
          ocupado={ocupado}
          aoConfirmar={() => void revogar()}
          aoCancelar={() => setRevogando(null)}
        >
          <p>
            <strong>{revogando.nome}</strong> ({revogando.prefixo}…) para de funcionar na hora. O
            Claude que a usa vai receber “chave inválida” até alguém configurar uma nova.
          </p>
        </Confirmacao>
      )}
    </Cartao>
  );
}
