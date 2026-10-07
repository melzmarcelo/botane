"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { useSessao } from "@/lib/sessao";
import ExplicaTela from "@/components/explica-tela";
import PlantaDoSalao from "./planta";
import {
  CARACTERISTICAS,
  FORMATOS,
  gravarPlanta,
  criarMesasEmLote,
  criarSalao,
  excluirMesa,
  excluirSalao,
  lerSalao,
  mudarMesa,
  mudarSalao,
  rotuloDaCaracteristica,
  simularGrupo,
  type Caracteristica,
  type DadosDoSalao,
  type Formato,
  type Mesa,
  type Simulacao,
} from "@/lib/salao";

/**
 * O salão da casa: salões, mesas e quantos lugares cada uma tem.
 *
 * 🔑 **Pedido do dono (14/09/2026):** *"para controle interno, ter o cadastro de
 * salões, cadastro de mesas, lugares por mesas."* E, depois de ver a primeira
 * versão: *"poderia ser separado por salão."*
 *
 * 🔑 **Um salão de cada vez, em abas**, com a aba no ENDEREÇO: recarregar,
 * voltar e guardar o link caem no mesmo salão.
 *
 * 🔑 **A mesa se edita num PAINEL, com Salvar e Desfazer** (06/10/2026, primeira
 * entrega do estudo `docs/salao-estudo.md`). Até aqui cada campo da tabela
 * gravava ao perder o foco: um número digitado errado já valia para a
 * disponibilidade no instante em que o cursor saía, e nada na tela dizia que
 * tinha gravado. Agora a tabela só MOSTRA; clicar na linha abre a mesa ao lado, e
 * nada vale antes do Salvar.
 * ⚠️ **Lugares e máximo são botões de − / +**, não campo de digitar: "60" por
 * engano num campo numérico era um toque a mais no teclado.
 *
 * 🔑 **`Lugares` e `máximo` são dois números de propósito.** Lugares é o
 * confortável; máximo é com a cadeira extra. A alocação usa o máximo.
 *
 * 🔑 **"Junta com" é a mesa vizinha que encosta nesta**, e vale nos dois
 * sentidos: o servidor grava dos dois lados e solta o par antigo.
 *
 * 🔑 **A tela confere o próprio cadastro**: avisa quando o site aceita mais
 * gente do que cabe, e responde "onde um grupo de N sentaria?" pela MESMA regra
 * da disponibilidade (`GET /reservas/salao/simular`) — a conta não é refeita
 * aqui.
 *
 * 🔑 **A planta** (07/10/2026, segunda entrega do estudo): as mesas desenhadas
 * onde estão, arrastáveis — `planta.tsx`. A LISTA continua num botão ao lado,
 * para quem prefere tabela e para o celular; a escolha mora no endereço.
 * ⚠️ O desenho mostra o RASCUNHO da mesa aberta (formato, lugares, nome): mudar
 * o formato no painel já muda a planta, antes do Salvar.
 *
 * ⚠️ **Desligar o salão tira as mesas dele da disponibilidade sem apagar
 * cadastro** — é a Varanda no inverno. Salão com mesa não se exclui.
 */

/** O que o painel edita: uma CÓPIA da mesa. Só o Salvar a leva ao servidor. */
type Rascunho = {
  nome: string;
  lugares: number;
  capacidade_max: number;
  ativo: boolean;
  caracteristicas: Caracteristica[];
  formato: Formato;
  junta_com: number | null;
};

const rascunhoDe = (m: Mesa): Rascunho => ({
  nome: m.nome,
  lugares: m.lugares,
  capacidade_max: m.capacidade_max,
  ativo: m.ativo,
  caracteristicas: [...(m.caracteristicas ?? [])],
  formato: m.formato ?? "QUADRADA",
  junta_com: m.junta_com,
});

const iguais = (a: Rascunho, b: Rascunho) =>
  a.nome.trim() === b.nome.trim() &&
  a.lugares === b.lugares &&
  a.capacidade_max === b.capacidade_max &&
  a.ativo === b.ativo &&
  a.formato === b.formato &&
  a.junta_com === b.junta_com &&
  [...a.caracteristicas].sort().join() === [...b.caracteristicas].sort().join();

export default function SalaoDaCasa() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [dados, setDados] = useState<DadosDoSalao | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [novoSalao, setNovoSalao] = useState("");
  const [criandoSalao, setCriandoSalao] = useState(false);
  const [lote, setLote] = useState(false);
  // A mesa aberta no painel, e o que foi mexido nela.
  const [idAberta, setIdAberta] = useState<number | null>(null);
  const [rascunho, setRascunho] = useState<Rascunho | null>(null);
  const [excluindo, setExcluindo] = useState<Mesa | null>(null);
  // ⚠️ Sem atraso: aba é clique, não digitação.
  const [abaUrl, setAbaUrl] = useEstadoNaUrl<string>("salao", "", { atraso: 0 });
  const [ver, setVer] = useEstadoNaUrl<string>("ver", "planta", { atraso: 0 });

  const carregar = useCallback(async () => {
    try {
      setDados(await lerSalao());
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o salão");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function agir(acao: () => Promise<{ message: string }>): Promise<boolean> {
    setOcupado(true);
    try {
      const r = await acao();
      aviso.sucesso(r.message);
      await carregar();
      return true;
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
      // ⚠️ Recarrega TAMBÉM no erro: a lista ao lado tem de mostrar o que está
      // gravado, não o que se tentou gravar.
      await carregar();
      return false;
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  const podeEditar = pode("reservas.configurar");
  // ⚠️ Endereço apontando para salão que não existe mais cai no primeiro.
  const aberto =
    dados.saloes.find((s) => String(s.id) === abaUrl) ?? dados.saloes[0] ?? null;
  const minhas = aberto ? dados.mesas.filter((m) => m.id_salao === aberto.id) : [];
  const mesaAberta = minhas.find((m) => m.id === idAberta) ?? null;
  const original = mesaAberta ? rascunhoDe(mesaAberta) : null;
  const mexido = !!(rascunho && original && !iguais(rascunho, original));

  function abrirMesa(m: Mesa | null) {
    setIdAberta(m?.id ?? null);
    setRascunho(m ? rascunhoDe(m) : null);
  }

  async function salvarMesa() {
    if (!mesaAberta || !rascunho || !original) return;
    // Só o que MUDOU vai no corpo — e a junta só se foi mexida (ver `mudarMesa`).
    const corpo: Parameters<typeof mudarMesa>[1] = {};
    if (rascunho.nome.trim() !== original.nome) corpo.nome = rascunho.nome.trim();
    if (rascunho.lugares !== original.lugares) corpo.lugares = rascunho.lugares;
    if (rascunho.capacidade_max !== original.capacidade_max) {
      corpo.capacidade_max = rascunho.capacidade_max;
    }
    if (rascunho.ativo !== original.ativo) corpo.ativo = rascunho.ativo;
    if ([...rascunho.caracteristicas].sort().join() !== [...original.caracteristicas].sort().join()) {
      corpo.caracteristicas = rascunho.caracteristicas;
    }
    if (rascunho.formato !== original.formato) corpo.formato = rascunho.formato;
    if (rascunho.junta_com !== original.junta_com) corpo.junta_com = rascunho.junta_com;
    const id = mesaAberta.id;
    const deu = await agir(() => mudarMesa(id, corpo));
    // Gravou: o painel passa a mostrar o que ficou. Recusou: o rascunho continua
    // na tela, para a pessoa corrigir sem digitar tudo de novo.
    if (deu) setRascunho(null);
  }

  // Depois de gravar, o painel relê a mesa do que o servidor devolveu.
  const emEdicao = rascunho ?? original;

  // A planta desenha o que está no painel, mesmo antes do Salvar.
  const desenhadas = minhas.map((m) =>
    m.id === idAberta && rascunho
      ? { ...m, nome: rascunho.nome, lugares: rascunho.lugares, ativo: rascunho.ativo,
          capacidade_max: rascunho.capacidade_max, formato: rascunho.formato }
      : m,
  );
  const naPlanta = ver !== "lista";

  const tetoPassa =
    dados.teto_online !== null && dados.mesas_ativas > 0 && dados.teto_online > dados.maior_grupo;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="titulo">Salão</h1>
        <ExplicaTela>
          Onde as pessoas sentam. É daqui que a disponibilidade vai dizer se cabe.
        </ExplicaTela>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { n: dados.mesas_ativas, r: "mesas ativas" },
          { n: dados.lugares, r: "lugares confortáveis" },
          { n: dados.capacidade_max, r: "com a cadeira extra" },
          { n: dados.maior_grupo, r: "maior grupo que cabe" },
        ].map((t) => (
          <div key={t.r} className="cartao px-4 py-3">
            <b className="mono block text-[26px] leading-none">{t.n}</b>
            <span className="text-[12.5px] text-suave">{t.r}</span>
          </div>
        ))}
      </div>

      {/* 🔑 O aviso que só existia na Configuração: quem cria o problema é quem
          mexe nas mesas, e é aqui que ele precisa aparecer. */}
      {tetoPassa && (
        <Aviso tipo="info">
          O site aceita grupos de até <b>{dados.teto_online}</b> pessoas, mas o maior que
          cabe hoje é <b>{dados.maior_grupo}</b>. Quem pedir mais não acha horário nenhum —
          e não sabe por quê. Junte mesas, aumente o máximo de uma delas ou baixe o teto em
          Configurações.
        </Aviso>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {dados.saloes.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={aberto?.id === s.id}
            aria-label={`salão ${s.nome}`}
            className={`rounded-full border px-3.5 py-1.5 text-[13.5px] ${
              aberto?.id === s.id
                ? "border-erva bg-erva-claro font-medium text-erva"
                : "border-linha2 text-suave hover:border-erva"
            }`}
            onClick={() => {
              setAbaUrl(String(s.id));
              abrirMesa(null);
            }}
          >
            {s.nome}
            <span className="mono ml-2 text-[11.5px] opacity-70">{s.mesas}</span>
            {!s.ativo && <span className="ml-2 text-[11px]">desligado</span>}
          </button>
        ))}

        {podeEditar &&
          (criandoSalao ? (
            <span className="flex items-center gap-2">
              <input
                className="campo"
                autoFocus
                placeholder="Nome do salão"
                aria-label="nome do novo salão"
                value={novoSalao}
                onChange={(e) => setNovoSalao(e.target.value)}
              />
              <button
                className="btn btn-secundario"
                aria-busy={ocupado}
                disabled={ocupado || !novoSalao.trim()}
                onClick={() =>
                  void agir(async () => {
                    const r = await criarSalao(novoSalao.trim(), dados.saloes.length);
                    setNovoSalao("");
                    setCriandoSalao(false);
                    setAbaUrl(String(r.id));
                    abrirMesa(null);
                    return r;
                  })
                }
              >
                criar
              </button>
              <button className="link-acao" onClick={() => setCriandoSalao(false)}>
                cancelar
              </button>
            </span>
          ) : (
            <button
              type="button"
              className="rounded-full border border-dashed border-linha2 px-3.5 py-1.5 text-[13.5px] text-suave hover:border-erva"
              onClick={() => setCriandoSalao(true)}
            >
              + salão
            </button>
          ))}
      </div>

      {!aberto ? (
        <Aviso tipo="info">
          Nenhum salão cadastrado ainda. Crie o primeiro — Salão principal, Varanda — e
          depois acrescente as mesas dele.
        </Aviso>
      ) : (
        <Cartao
          titulo={aberto.nome}
          descricao="Lugares é o confortável; máximo é com a cadeira extra — a alocação usa o máximo."
          acao={
            podeEditar && (
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secundario"
                  aria-busy={ocupado}
                  disabled={ocupado}
                  onClick={() => setLote((v) => !v)}
                >
                  + várias mesas
                </button>
                <button
                  className="btn btn-secundario"
                  aria-busy={ocupado}
                  disabled={ocupado}
                  onClick={() =>
                    void agir(() =>
                      criarMesasEmLote({ id_salao: aberto.id, quantidade: 1, lugares: 2 }),
                    )
                  }
                >
                  + mesa
                </button>
              </div>
            )
          }
        >
          {podeEditar && (
            <DadosDoSalaoAberto
              key={`salao-${aberto.id}-${aberto.nome}`}
              nome={aberto.nome}
              ativo={aberto.ativo}
              temMesas={minhas.length > 0}
              ocupado={ocupado}
              aoRenomear={(nome) => void agir(() => mudarSalao(aberto.id, { nome }))}
              aoLigar={(ativo) => void agir(() => mudarSalao(aberto.id, { ativo }))}
              aoExcluir={() =>
                void agir(async () => {
                  const r = await excluirSalao(aberto.id);
                  setAbaUrl("");
                  return r;
                })
              }
            />
          )}

          {lote && podeEditar && (
            <FormularioDeLote
              idSalao={aberto.id}
              ocupado={ocupado}
              aoCriar={(corpo) =>
                void agir(async () => {
                  const r = await criarMesasEmLote(corpo);
                  setLote(false);
                  return r;
                })
              }
              aoFechar={() => setLote(false)}
            />
          )}

          {!minhas.length ? (
            <p className="px-1 py-6 text-center text-[14px] text-suave">
              Nenhuma mesa neste salão ainda. Use <b>+ várias mesas</b> para montar o salão
              de uma vez.
            </p>
          ) : (
            <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_330px]">
              <div className="flex min-w-0 flex-col gap-3">
              <div className="inline-flex self-start overflow-hidden rounded-[9px] border border-linha2"
                   role="group" aria-label="como ver o salão">
                {([["planta", "Planta"], ["lista", "Lista"]] as const).map(([v, r]) => (
                  <button key={v} type="button" aria-pressed={naPlanta === (v === "planta")}
                          className={`px-3.5 py-1.5 text-[13.5px] ${
                            naPlanta === (v === "planta") ? "bg-erva text-white" : "text-suave"}`}
                          onClick={() => setVer(v)}>
                    {r}
                  </button>
                ))}
              </div>
              {naPlanta ? (
                <PlantaDoSalao
                  key={`planta-${aberto.id}`}
                  mesas={desenhadas}
                  idAberta={idAberta}
                  salaoAtivo={aberto.ativo}
                  podeEditar={podeEditar}
                  ocupado={ocupado}
                  aoAbrir={(id) => abrirMesa(minhas.find((m) => m.id === id) ?? null)}
                  aoSalvar={(posicoes) => agir(() => gravarPlanta(posicoes))}
                />
              ) : (
              <div className="grid-rolante">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th className="min-w-[90px]">Mesa</th>
                      <th className="num w-[90px]">Lugares</th>
                      <th className="num w-[90px]">Máximo</th>
                      <th className="min-w-[140px]">Características</th>
                      <th className="min-w-[110px]">Junta com</th>
                      <th className="w-[100px]">Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {minhas.map((m) => (
                      <tr
                        key={m.id}
                        aria-label={`mesa ${m.nome}`}
                        aria-selected={idAberta === m.id}
                        tabIndex={0}
                        className={`cursor-pointer ${idAberta === m.id ? "bg-erva-claro" : ""} ${
                          m.ativo && aberto.ativo ? "" : "text-suave"
                        }`}
                        onClick={() => abrirMesa(m)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            abrirMesa(m);
                          }
                        }}
                      >
                        <td className="mono font-medium">{m.nome}</td>
                        <td className="num mono">{m.lugares}</td>
                        <td className="num mono">{m.capacidade_max}</td>
                        <td>
                          {m.caracteristicas?.length ? (
                            <span className="flex flex-wrap gap-1">
                              {m.caracteristicas.map((c) => (
                                <Etiqueta key={c}>{rotuloDaCaracteristica(c)}</Etiqueta>
                              ))}
                            </span>
                          ) : (
                            <span className="text-suave">—</span>
                          )}
                        </td>
                        <td className="mono">
                          {m.junta_com_nome ?? <span className="text-suave">—</span>}
                        </td>
                        <td>
                          {m.ativo ? (
                            <Etiqueta cor="erva">ativa</Etiqueta>
                          ) : (
                            <Etiqueta cor="alerta">desligada</Etiqueta>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              )}
              </div>

              <aside className="rounded-xl border border-linha2 p-4" aria-label="mesa aberta">
                {!mesaAberta || !emEdicao ? (
                  <>
                    <p className="rotulo">Mesa</p>
                    <p className="mt-1 font-medium">Nenhuma selecionada</p>
                    <p className="mt-2 text-[13px] text-suave">
                      Clique numa mesa para ver{podeEditar ? " e editar" : ""}.
                      {podeEditar && " As mudanças só valem depois de Salvar."}
                    </p>
                  </>
                ) : (
                  <PainelDaMesa
                    mesa={mesaAberta}
                    valor={emEdicao}
                    mexido={mexido}
                    ocupado={ocupado}
                    podeEditar={podeEditar}
                    outras={dados.mesas
                      .filter((x) => x.id !== mesaAberta.id)
                      .map((x) => ({
                        id: x.id,
                        // ⚠️ A junta NÃO se limita ao salão (a da porta da varanda
                        // encosta na do canto do principal), mas o nome do salão
                        // viaja junto: "03" sozinho não diz de onde é.
                        rotulo:
                          x.id_salao !== mesaAberta.id_salao
                            ? `${x.nome} · ${dados.saloes.find((s) => s.id === x.id_salao)?.nome ?? ""}`
                            : x.nome,
                      }))}
                    aoMudar={(parte) => setRascunho({ ...emEdicao, ...parte })}
                    aoSalvar={() => void salvarMesa()}
                    aoDesfazer={() => setRascunho(null)}
                    aoExcluir={() => setExcluindo(mesaAberta)}
                  />
                )}
              </aside>
            </div>
          )}
        </Cartao>
      )}

      {dados.mesas_ativas > 0 && (
        <ConferenciaDoCadastro
          // ⚠️ `key` no que muda a resposta: mexer numa mesa refaz a pergunta.
          key={`${dados.maior_grupo}-${dados.capacidade_max}-${dados.mesas_ativas}`}
          maiorGrupo={dados.maior_grupo}
          teto={dados.teto_online}
        />
      )}

      {excluindo && (
        <Confirmacao
          titulo="Excluir a mesa?"
          rotuloConfirmar="Excluir"
          perigo
          ocupado={ocupado}
          aoCancelar={() => setExcluindo(null)}
          aoConfirmar={() => {
            const m = excluindo;
            setExcluindo(null);
            abrirMesa(null);
            void agir(() => excluirMesa(m.id));
          }}
        >
          <p>
            A mesa <b>{excluindo.nome}</b> sai do cadastro. Se alguma reserva já sentou
            nela, o sistema recusa — nesse caso, desligue em vez de excluir.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}

/**
 * O nome e a situação do salão aberto.
 *
 * ⚠️ **O nome também tem Salvar** — pela mesma razão das mesas: gravar ao sair
 * do campo não deixava ver que gravou. "Atende" continua imediato: é um
 * interruptor, e interruptor que pede confirmação deixa de ser um.
 */
function DadosDoSalaoAberto({
  nome,
  ativo,
  temMesas,
  ocupado,
  aoRenomear,
  aoLigar,
  aoExcluir,
}: {
  nome: string;
  ativo: boolean;
  temMesas: boolean;
  ocupado: boolean;
  aoRenomear: (nome: string) => void;
  aoLigar: (ativo: boolean) => void;
  aoExcluir: () => void;
}) {
  const [texto, setTexto] = useState(nome);
  const mudou = texto.trim() !== nome && texto.trim().length > 0;
  return (
    <div className="mb-4 flex flex-wrap items-end gap-4 border-b border-linha2 pb-4">
      <Campo rotulo="Nome do salão" className="min-w-[220px] flex-1">
        <input
          className="campo"
          aria-label={`nome do salão ${nome}`}
          value={texto}
          maxLength={60}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && mudou) aoRenomear(texto.trim());
          }}
        />
      </Campo>
      {mudou && (
        <div className="flex items-center gap-2 pb-0.5">
          <button className="btn btn-primario" aria-busy={ocupado} disabled={ocupado}
                  onClick={() => aoRenomear(texto.trim())}>
            Salvar nome
          </button>
          <button className="link-acao" onClick={() => setTexto(nome)}>
            desfazer
          </button>
        </div>
      )}
      <label className="flex items-center gap-2 pb-2 text-[14px]">
        <input
          type="checkbox"
          aria-label={`salão ${nome} ativo`}
          checked={ativo}
          disabled={ocupado}
          onChange={(e) => aoLigar(e.target.checked)}
        />
        Atende
      </label>
      <div className="pb-2">
        {/* Salão com mesa não se exclui: o servidor recusa de qualquer jeito, e
            oferecer o botão só para dar erro seria armadilha. */}
        {!temMesas ? (
          <button className="link-acao link-acao-erro" aria-label={`excluir salão ${nome}`}
                  onClick={aoExcluir}>
            excluir salão
          </button>
        ) : (
          <span className="text-[12.5px] text-suave">tem mesas — desligue em vez de excluir</span>
        )}
      </div>
    </div>
  );
}

/** Um número que se muda de um em um — sem campo para digitar errado. */
function Passo({
  rotulo,
  valor,
  minimo,
  maximo,
  desabilitado,
  aoMudar,
}: {
  rotulo: string;
  valor: number;
  minimo: number;
  maximo: number;
  desabilitado: boolean;
  aoMudar: (n: number) => void;
}) {
  return (
    <div className="flex items-center overflow-hidden rounded-[9px] border border-linha2">
      <button type="button" className="h-9 w-9 bg-superficie2 text-[17px] disabled:opacity-40"
              aria-label={`menos ${rotulo}`} disabled={desabilitado || valor <= minimo}
              onClick={() => aoMudar(valor - 1)}>
        −
      </button>
      <output className="mono flex-1 text-center" aria-label={rotulo}>{valor}</output>
      <button type="button" className="h-9 w-9 bg-superficie2 text-[17px] disabled:opacity-40"
              aria-label={`mais ${rotulo}`} disabled={desabilitado || valor >= maximo}
              onClick={() => aoMudar(valor + 1)}>
        +
      </button>
    </div>
  );
}

function PainelDaMesa({
  mesa,
  valor,
  mexido,
  ocupado,
  podeEditar,
  outras,
  aoMudar,
  aoSalvar,
  aoDesfazer,
  aoExcluir,
}: {
  mesa: Mesa;
  valor: Rascunho;
  mexido: boolean;
  ocupado: boolean;
  podeEditar: boolean;
  outras: { id: number; rotulo: string }[];
  aoMudar: (parte: Partial<Rascunho>) => void;
  aoSalvar: () => void;
  aoDesfazer: () => void;
  aoExcluir: () => void;
}) {
  const travado = !podeEditar || ocupado;
  const nomeVazio = !valor.nome.trim();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (mexido && !nomeVazio) aoSalvar();
      }}
    >
      <p className="rotulo">Mesa {mesa.nome}</p>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Campo rotulo="Nome" className="col-span-2">
          <input className="campo mono" aria-label="nome da mesa" maxLength={20}
                 disabled={travado} value={valor.nome}
                 onChange={(e) => aoMudar({ nome: e.target.value })} />
        </Campo>
        <Campo rotulo="Lugares" dica="o confortável">
          <Passo rotulo="lugares" valor={valor.lugares} minimo={1} maximo={40}
                 desabilitado={travado}
                 aoMudar={(n) =>
                   // ⚠️ O máximo nunca fica abaixo do confortável — a regra do banco,
                   // resolvida aqui para a pessoa não levar um erro por subir um número.
                   aoMudar({ lugares: n, capacidade_max: Math.max(valor.capacidade_max, n) })
                 } />
        </Campo>
        <Campo rotulo="Máximo" dica="com a cadeira extra">
          <Passo rotulo="máximo" valor={valor.capacidade_max} minimo={1} maximo={60}
                 desabilitado={travado}
                 aoMudar={(n) => aoMudar({ capacidade_max: n, lugares: Math.min(valor.lugares, n) })} />
        </Campo>
        <div className="col-span-2">
          <span className="rotulo-campo">Características</span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {CARACTERISTICAS.map((c) => {
              const marcada = valor.caracteristicas.includes(c.chave);
              return (
                <button
                  key={c.chave}
                  type="button"
                  aria-pressed={marcada}
                  disabled={travado}
                  className={`rounded-lg border px-2.5 py-1 text-[12.5px] ${
                    marcada
                      ? "border-erva bg-erva-claro font-medium text-erva"
                      : "border-linha2 text-suave hover:border-erva"
                  }`}
                  onClick={() =>
                    aoMudar({
                      caracteristicas: marcada
                        ? valor.caracteristicas.filter((x) => x !== c.chave)
                        : [...valor.caracteristicas, c.chave],
                    })
                  }
                >
                  {c.rotulo}
                </button>
              );
            })}
          </div>
        </div>
        <Campo rotulo="Formato" dica="como aparece na planta" className="col-span-2">
          <select className="campo" aria-label="formato da mesa" disabled={travado}
                  value={valor.formato}
                  onChange={(e) => aoMudar({ formato: e.target.value as Formato })}>
            {FORMATOS.map((f) => (
              <option key={f.chave} value={f.chave}>{f.rotulo}</option>
            ))}
          </select>
        </Campo>
        <Campo rotulo="Junta com" dica="a vizinha que encosta nesta" className="col-span-2">
          <select className="campo" aria-label="mesa que junta com esta" disabled={travado}
                  value={valor.junta_com ?? ""}
                  onChange={(e) =>
                    aoMudar({ junta_com: e.target.value ? Number(e.target.value) : null })
                  }>
            <option value="">—</option>
            {outras.map((x) => (
              <option key={x.id} value={x.id}>{x.rotulo}</option>
            ))}
          </select>
        </Campo>
        <label className="col-span-2 flex items-center gap-2 text-[14px]">
          <input type="checkbox" aria-label="mesa ativa" disabled={travado}
                 checked={valor.ativo} onChange={(e) => aoMudar({ ativo: e.target.checked })} />
          Mesa ativa
        </label>
      </div>

      {podeEditar && (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button type="submit" className="btn btn-primario" aria-busy={ocupado}
                    disabled={ocupado || !mexido || nomeVazio}>
              Salvar
            </button>
            <button type="button" className="btn btn-secundario" disabled={ocupado || !mexido}
                    onClick={aoDesfazer}>
              Desfazer
            </button>
            {mexido && <span className="text-[12.5px] text-alerta">alterações não salvas</span>}
          </div>
          <p className="mt-2 text-[12.5px] text-suave">
            A junta vale nos dois sentidos: salvar grava dos dois lados e solta o par
            anterior.
          </p>
          <p className="mt-3">
            <button type="button" className="link-acao link-acao-erro"
                    aria-label={`excluir mesa ${mesa.nome}`} disabled={ocupado}
                    onClick={aoExcluir}>
              excluir mesa
            </button>
          </p>
        </>
      )}
    </form>
  );
}

/**
 * "Onde um grupo de N sentaria?" — a conferência do cadastro.
 *
 * 🔑 **A resposta vem do servidor**, pela mesma `alocar` da disponibilidade. A
 * tela não refaz a conta: duas versões da regra divergiriam na primeira mudança,
 * e esta passaria a prometer o que a agenda não entrega.
 * ⚠️ Com o salão VAZIO: isto confere o cadastro, não o dia.
 */
function ConferenciaDoCadastro({ maiorGrupo, teto }: { maiorGrupo: number; teto: number | null }) {
  const limite = Math.max(maiorGrupo, teto ?? 0, 2) + 2;
  const [pessoas, setPessoas] = useState(Math.min(4, limite));
  const [r, setR] = useState<Simulacao | null>(null);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    let vivo = true;
    // Um respiro: arrastar o controle não deve disparar um pedido por pixel.
    const espera = setTimeout(() => {
      simularGrupo(pessoas)
        .then((x) => vivo && (setR(x), setFalhou(false)))
        .catch(() => vivo && setFalhou(true));
    }, 150);
    return () => {
      vivo = false;
      clearTimeout(espera);
    };
  }, [pessoas]);

  return (
    <Cartao
      titulo="Onde um grupo sentaria?"
      descricao="A mesma regra da disponibilidade, com o salão vazio: a menor mesa que serve, e mesa inteira antes de junta."
    >
      <div className="flex flex-wrap items-center gap-4">
        <Campo rotulo="Pessoas no grupo" className="w-full sm:w-[280px]">
          <input type="range" className="w-full accent-erva" min={1} max={limite}
                 aria-label="pessoas no grupo" value={pessoas}
                 onChange={(e) => setPessoas(Number(e.target.value))} />
        </Campo>
        <b className="mono text-[24px] leading-none">{pessoas}</b>
        <p className="min-w-[220px] flex-1 text-[14.5px]" role="status" aria-live="polite">
          {falhou ? (
            <span className="text-erro">Não foi possível consultar.</span>
          ) : !r || r.pessoas !== pessoas ? (
            <span className="text-suave">consultando…</span>
          ) : !r.cabe ? (
            <>
              <span className="font-medium text-erro">Não cabe.</span> O maior grupo que o
              salão acomoda é de <b>{r.maior_grupo}</b>
              {r.teto_online !== null && pessoas <= r.teto_online && (
                <> — e o site aceita pedir até {r.teto_online}</>
              )}
              .
            </>
          ) : r.como === "mesa" ? (
            <>
              Senta na mesa <b>{r.mesas[0].nome}</b>
              {r.mesas[0].salao && <> ({r.mesas[0].salao})</>} — a menor que serve, para até{" "}
              {r.capacidade}.
            </>
          ) : (
            <>
              Nenhuma mesa sozinha serve. Junta{" "}
              <b>{r.mesas.map((m) => m.nome).join(" + ")}</b>, que acomodam {r.capacidade}.
            </>
          )}
        </p>
      </div>
    </Cartao>
  );
}

/**
 * Montar o salão de uma vez.
 *
 * 🔑 **É o trabalho real do cadastro, e acontece uma vez só**: no dia em que a
 * casa entra no sistema. Clicar "+ mesa" doze vezes e renomear cada uma é
 * exatamente quando ninguém tem paciência — e cadastro mal feito no primeiro dia
 * é o que faz a disponibilidade responder errado no segundo.
 */
function FormularioDeLote({
  idSalao,
  ocupado,
  aoCriar,
  aoFechar,
}: {
  idSalao: number;
  ocupado: boolean;
  aoCriar: (corpo: Record<string, unknown>) => void;
  aoFechar: () => void;
}) {
  const [quantidade, setQuantidade] = useState(4);
  const [lugares, setLugares] = useState(4);
  const [maximo, setMaximo] = useState(4);
  const [prefixo, setPrefixo] = useState("");

  return (
    <div className="mb-4 rounded-xl border border-linha2 bg-superficie2 p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo rotulo="Quantas mesas" dica="até 50 de uma vez">
          <input
            className="campo mono text-right"
            type="number"
            min={1}
            max={50}
            aria-label="quantas mesas criar"
            value={quantidade}
            onChange={(e) => setQuantidade(Number(e.target.value))}
          />
        </Campo>
        <Campo rotulo="Lugares em cada" dica="o confortável">
          <input
            className="campo mono text-right"
            type="number"
            min={1}
            aria-label="lugares de cada mesa do lote"
            value={lugares}
            onChange={(e) => {
              const n = Number(e.target.value);
              setLugares(n);
              // ⚠️ O máximo acompanha enquanto ninguém o separou: quem não tem
              // cadeira extra não devia precisar mexer em dois campos.
              if (maximo < n) setMaximo(n);
            }}
          />
        </Campo>
        <Campo rotulo="Máximo em cada" dica="com a cadeira extra">
          <input
            className="campo mono text-right"
            type="number"
            min={1}
            aria-label="máximo de cada mesa do lote"
            value={maximo}
            onChange={(e) => setMaximo(Number(e.target.value))}
          />
        </Campo>
        <Campo rotulo="Prefixo (opcional)" dica='"V" dá V01, V02…'>
          <input
            className="campo"
            maxLength={6}
            aria-label="prefixo do nome das mesas"
            value={prefixo}
            onChange={(e) => setPrefixo(e.target.value)}
          />
        </Campo>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          className="btn btn-primario"
          aria-busy={ocupado}
          disabled={ocupado || quantidade < 1 || maximo < lugares}
          onClick={() =>
            aoCriar({
              id_salao: idSalao,
              quantidade,
              lugares,
              capacidade_max: maximo,
              prefixo: prefixo.trim(),
            })
          }
        >
          Criar {quantidade} mesa{quantidade === 1 ? "" : "s"}
        </button>
        <button className="link-acao" onClick={aoFechar}>
          cancelar
        </button>
        {/* ⚠️ O nome é único por LOJA: o lote pula o que já existe em vez de
            recusar, e é justo dizer isso antes de a pessoa clicar. */}
        <span className="text-[12.5px] text-suave">
          A numeração começa no primeiro nome livre — mesas que já existem são puladas.
        </span>
      </div>
    </div>
  );
}
