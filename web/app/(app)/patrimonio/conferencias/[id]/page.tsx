"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BotaoExportar from "@/components/exportar";
import LeitorQr, { leitorDisponivel } from "@/components/leitor-qr";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta, Modal, Vazio } from "@/components/ui";
import Voltar from "@/components/voltar";
import {
  cancelarConferencia, conferencia, dataBr, desfazerLeitura, fecharConferencia, lerPlaqueta,
  marcarConferindo, type Conferencia, type ItemConferencia,
} from "@/lib/patrimonio";
import { useSessao } from "@/lib/sessao";

/**
 * Uma conferência do patrimônio: ler as plaquetas e fechar (etapa 3, migração 140).
 *
 * 🔑 **Três jeitos de ler, e todos caem no mesmo lugar** (`POST …/leituras`):
 *   1. a câmera DENTRO da tela (Chrome do Android — `LeitorQr`), plaqueta atrás de plaqueta;
 *   2. o campo de texto: o leitor de código USB/Bluetooth "digita" o link e dá Enter, ou
 *      a pessoa digita o código (PAT-0003) ou o apelido da casa;
 *   3. a câmera COMUM do celular (iPhone): ela abre a plaqueta no sistema, e como ESTE
 *      aparelho está marcado como "conferindo", `/patrimonio/b/…` conta a leitura.
 * ⚠️ **Uma linha só diz o que aconteceu com a última leitura** (`#conferencia-ultima`) — com
 * o celular na mão ninguém lê uma lista para saber se a plaqueta entrou.
 */
export default function PaginaConferencia() {
  const { id } = useParams<{ id: string }>();
  const idc = Number(id);
  const { pode } = useSessao();
  const aviso = useAviso();
  const podeConferir = pode("patrimonio.conferir");
  const [c, setC] = useState<Conferencia | null>(null);
  const [erro, setErro] = useState("");
  const [texto, setTexto] = useState("");
  const [ultima, setUltima] = useState<{ ok: boolean; msg: string } | null>(null);
  const [camera, setCamera] = useState(false);
  const [temCamera, setTemCamera] = useState(false);
  const [fechando, setFechando] = useState(false);
  const [cancelando, setCancelando] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const campo = useRef<HTMLInputElement>(null);

  const carregar = useCallback(() => {
    conferencia(idc).then(setC).catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, [idc]);

  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => { setTemCamera(leitorDisponivel()); }, []);
  // Quem abre a conferência aberta neste aparelho passa a ser "o aparelho que confere":
  // a plaqueta lida pela câmera comum conta aqui (ver `/patrimonio/b/…`).
  useEffect(() => {
    if (c && podeConferir) marcarConferindo(c.status === "ABERTA" ? c.id : null);
  }, [c, podeConferir]);

  const ler = useCallback(async (lido: string) => {
    const t = lido.trim();
    if (!t) return;
    try {
      const r = await lerPlaqueta(idc, t);
      setUltima({ ok: !r.ja_lido, msg: r.message });
      setTexto("");
      // O contador anda JUNTO com a mensagem (a leitura já devolve a contagem); as listas
      // vêm na recarga, logo depois.
      setC((atual) => atual && { ...atual, ...r.contagem });
      carregar();
    } catch (e) {
      setUltima({ ok: false, msg: e instanceof Error ? e.message : "Não foi possível ler" });
    } finally {
      campo.current?.focus();
    }
  }, [idc, carregar]);

  async function desfazer(i: ItemConferencia) {
    try {
      setC(await desfazerLeitura(idc, i.id));
      setUltima({ ok: true, msg: `${i.codigo}: leitura desfeita.` });
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível desfazer");
    }
  }

  async function cancelar() {
    setOcupado(true);
    try {
      const r = await cancelarConferencia(idc);
      marcarConferindo(null);
      aviso.sucesso(r.message);
      setCancelando(false);
      setC(r);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível cancelar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <div className="flex flex-col gap-4"><Voltar href="/patrimonio/conferencias">conferências</Voltar><Aviso tipo="erro">{erro}</Aviso></div>;
  if (!c) return <Carregando />;

  const aberta = c.status === "ABERTA";
  const faltam = c.itens.filter((i) => i.esperado && !i.lido_em);
  const deFora = c.itens.filter((i) => !i.esperado);
  const lidos = c.itens.filter((i) => i.esperado && i.lido_em);

  const tabela = (itens: ItemConferencia[], idTabela: string, comDesfazer: boolean) => (
    <div className="grid-rolante">
      <table className="tabela" id={idTabela}>
        <thead>
          <tr><th>Plaqueta</th><th>Equipamento</th><th>Setor · local</th><th>Situação</th>
            {!aberta && <th>Resultado</th>}{comDesfazer && aberta && podeConferir && <th></th>}</tr>
        </thead>
        <tbody>
          {itens.map((i) => (
            <tr key={i.id}>
              <td className="mono whitespace-nowrap">
                <Link href={`/patrimonio/${i.id_bem}`} className="link-registro font-semibold">{i.codigo}</Link>
                {i.apelido && <span className="block text-[12px] text-suave">{i.apelido}</span>}
              </td>
              <td>
                {i.descricao}
                {i.lido_em && (
                  <span className="block text-[12px] text-suave">
                    lido {new Date(i.lido_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                    {i.lido_por_nome ? ` · ${i.lido_por_nome}` : ""}
                  </span>
                )}
              </td>
              <td>
                {i.setor ?? "—"}{i.local && <span className="text-suave"> · {i.local}</span>}
                {!i.esperado && i.setor_antes !== c.setor && (
                  <span className="block text-[12px] text-alerta">o sistema o punha em {i.setor_antes ?? "nenhum setor"}</span>
                )}
              </td>
              <td>{i.situacao_txt}</td>
              {!aberta && <td>{i.resultado_txt ?? "—"}</td>}
              {comDesfazer && aberta && podeConferir && (
                <td><button type="button" className="link-acao" onClick={() => void desfazer(i)}>desfazer</button></td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/patrimonio/conferencias">conferências</Voltar>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Conferência nº {c.id} · {c.escopo}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[13.5px]">
          <Etiqueta cor={aberta ? "alerta" : c.status === "FECHADA" ? "erva" : "neutro"}>{c.status_txt}</Etiqueta>
          <span className="text-suave">
            aberta em {dataBr(c.aberta_em)}{c.aberta_por_nome ? ` por ${c.aberta_por_nome}` : ""}
            {c.fechada_em ? ` · encerrada em ${dataBr(c.fechada_em)}${c.fechada_por_nome ? ` por ${c.fechada_por_nome}` : ""}` : ""}
          </span>
          <BotaoExportar className="link-acao" rotulo="folha da conferência" formatoPadrao="pdf"
                         relatorio={`conferencia-patrimonio/${c.id}`}
                         avulso={{ rotulo: "Folha da conferência",
                                   descricao: aberta ? "Com o que falta ler — dá para conferir no papel."
                                                     : "O resultado de cada bem, para assinar." }} />
        </div>
        {c.observacao && <p className="mt-2 text-[14px] text-suave">{c.observacao}</p>}
      </header>

      {/* O progresso é a pergunta do meio da volta: quanto falta. Grudado no topo porque
          no celular ele sai da tela na primeira rolagem — como no inventário. */}
      <div className="sticky top-0 z-20 -mx-4 border-b border-linha bg-papel/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6"
           id="conferencia-progresso">
        <p className="text-[15px]">
          <b>{c.lidos}</b> de <b>{c.esperados}</b> lidos · <b>{c.faltam}</b> faltam
          {c.de_fora > 0 && <> · <b>{c.de_fora}</b> de outro setor</>}
        </p>
      </div>

      {aberta && podeConferir && (
        <Cartao titulo="Ler plaqueta"
                descricao="Aponte a câmera, use o leitor de código ou digite o código (PAT-0001) ou o apelido.">
          <form className="flex flex-wrap items-center gap-2"
                onSubmit={(e) => { e.preventDefault(); void ler(texto); }}>
            <input ref={campo} className="campo max-w-[320px]" id="conferencia-leitura" autoFocus
                   autoComplete="off" value={texto} onChange={(e) => setTexto(e.target.value)}
                   placeholder="PAT-0001" aria-label="código da plaqueta" />
            <button type="submit" className="btn btn-primario" id="conferencia-ler" disabled={!texto.trim()}>
              Ler
            </button>
            {temCamera && !camera && (
              <button type="button" className="btn btn-secundario" id="conferencia-camera"
                      onClick={() => setCamera(true)}>
                Ler com a câmera
              </button>
            )}
          </form>
          {camera && <div className="mt-3"><LeitorQr onLer={(t) => void ler(t)} onFechar={() => setCamera(false)} /></div>}
          {ultima && (
            <p role="status" id="conferencia-ultima"
               className={`mt-3 text-[15px] font-medium ${ultima.ok ? "text-erva" : "text-alerta"}`}>
              {ultima.msg}
            </p>
          )}
          {!temCamera && (
            <p className="mt-3 text-[13px] text-suave">
              Neste aparelho a câmera não lê dentro da tela: abra a câmera do celular e aponte
              para a plaqueta — o link abre o sistema e a leitura conta nesta conferência.
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2 border-t border-linha pt-4">
            <button type="button" className="btn btn-primario" id="conferencia-fechar"
                    onClick={() => setFechando(true)}>
              Fechar a conferência
            </button>
            <button type="button" className="btn btn-secundario" id="conferencia-cancelar"
                    onClick={() => setCancelando(true)}>
              Cancelar sem aplicar
            </button>
          </div>
        </Cartao>
      )}

      <Cartao titulo={aberta ? `Faltam ler (${faltam.length})` : `Não encontrados (${faltam.length})`}>
        {faltam.length ? tabela(faltam, "conferencia-faltam", false)
          : <Vazio>{aberta ? "Todos os esperados já foram lidos." : "Todos os esperados foram vistos."}</Vazio>}
      </Cartao>
      {deFora.length > 0 && (
        <Cartao titulo={`Achados aqui, mas de outro setor (${deFora.length})`}
                descricao={aberta ? "No fechamento, eles vêm para este setor." : undefined}>
          {tabela(deFora, "conferencia-de-fora", true)}
        </Cartao>
      )}
      <Cartao titulo={`Lidos (${lidos.length})`}>
        {lidos.length ? tabela(lidos, "conferencia-lidos", true) : <Vazio>Nenhuma plaqueta lida ainda.</Vazio>}
      </Cartao>

      {fechando && (
        <JanelaFechar c={c} faltam={faltam} aoFechar={() => setFechando(false)}
                      aoConcluir={(r) => { marcarConferindo(null); setFechando(false); setC(r); }} />
      )}
      {cancelando && (
        <Confirmacao titulo="Cancelar a conferência?" perigo ocupado={ocupado}
                     rotuloConfirmar="Cancelar a conferência" rotuloCancelar="Voltar"
                     aoConfirmar={() => void cancelar()} aoCancelar={() => setCancelando(false)}>
          Nenhum bem muda: nem conferido, nem transferido, nem baixado. As leituras ficam só
          como registro.
        </Confirmacao>
      )}
    </div>
  );
}

/**
 * O fechamento: o que não apareceu, bem a bem — manter ou dar baixa.
 * ⚠️ **Manter é o padrão**: o equipamento no conserto ou emprestado não pode sumir do
 * cadastro porque não estava na hora da volta.
 */
function JanelaFechar({ c, faltam, aoFechar, aoConcluir }: {
  c: Conferencia;
  faltam: ItemConferencia[];
  aoFechar: () => void;
  aoConcluir: (r: Conferencia) => void;
}) {
  const aviso = useAviso();
  const [baixar, setBaixar] = useState<number[]>([]);
  const [motivo, setMotivo] = useState("");
  const [transferir, setTransferir] = useState(true);
  const [confirmar, setConfirmar] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const aConfirmar = c.itens.filter((i) => i.lido_em && i.situacao === "A_CONFIRMAR").length;

  async function fechar() {
    setOcupado(true);
    try {
      const r = await fecharConferencia(c.id, {
        baixar, motivo_baixa: motivo.trim() || null, transferir, confirmar,
      });
      aviso.sucesso(r.message);
      aoConcluir(r);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível fechar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal titulo="Fechar a conferência" aoFechar={aoFechar}
           descricao={`${c.lidos} de ${c.esperados} lidos. O que foi visto fica com a data de hoje.`}
           rodape={
             <div className="flex flex-wrap justify-end gap-2">
               <button type="button" className="btn btn-secundario" onClick={aoFechar}>Voltar</button>
               <button type="button" className="btn btn-primario" id="conferencia-confirmar-fechar"
                       disabled={ocupado} aria-busy={ocupado} onClick={() => void fechar()}>
                 Fechar{baixar.length ? ` e baixar ${baixar.length}` : ""}
               </button>
             </div>
           }>
      <div className="flex flex-col gap-4">
        {c.id_setor && c.de_fora > 0 && (
          <label className="flex items-start gap-2 text-[14px]">
            <input type="checkbox" id="conferencia-transferir" checked={transferir}
                   onChange={(e) => setTransferir(e.target.checked)} />
            <span>Trazer para <b>{c.escopo}</b> os {c.de_fora} bem(ns) achado(s) aqui que o sistema
              punha em outro setor (o local de lá sai).</span>
          </label>
        )}
        {aConfirmar > 0 && (
          <label className="flex items-start gap-2 text-[14px]">
            <input type="checkbox" id="conferencia-confirmar" checked={confirmar}
                   onChange={(e) => setConfirmar(e.target.checked)} />
            <span>Os {aConfirmar} lido(s) que estavam “A confirmar” passam a <b>Em uso</b> — a
              conferência viu que eles existem.</span>
          </label>
        )}
        {faltam.length ? (
          <div>
            <p className="mb-2 text-[14px]">
              <b>{faltam.length}</b> {faltam.length === 1 ? "não apareceu" : "não apareceram"}. Marque só os que <b>saíram da casa</b> — o
              resto continua no cadastro, como “não encontrado” nesta conferência.
            </p>
            <ul className="flex flex-col gap-1" id="conferencia-baixar">
              {faltam.map((i) => (
                <li key={i.id}>
                  <label className="flex items-center gap-2 text-[14px]">
                    <input type="checkbox" checked={baixar.includes(i.id)} data-codigo={i.codigo}
                           onChange={(e) => setBaixar((b) => e.target.checked ? [...b, i.id] : b.filter((x) => x !== i.id))} />
                    <span><span className="mono">{i.codigo}</span> · {i.descricao}</span>
                    <span className="text-[12px] text-suave">dar baixa</span>
                  </label>
                </li>
              ))}
            </ul>
            {baixar.length > 0 && (
              <div className="mt-3">
                <Campo rotulo="Motivo da baixa" opcional
                       dica={`se ficar vazio: “Não encontrado na conferência nº ${c.id}”`}>
                  <input className="campo" id="conferencia-motivo" maxLength={200} value={motivo}
                         onChange={(e) => setMotivo(e.target.value)} placeholder="descartado, furtado, vendido…" />
                </Campo>
              </div>
            )}
          </div>
        ) : (
          <Aviso tipo="ok">Todos os esperados foram lidos.</Aviso>
        )}
      </div>
    </Modal>
  );
}
