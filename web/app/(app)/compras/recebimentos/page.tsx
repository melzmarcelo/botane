"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro from "@/components/busca-cadastro";
import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Modal, SeletorDeArquivo, Vazio } from "@/components/ui";
import { fonteFornecedores } from "@/lib/busca-cadastro";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { reduzirFoto } from "@/lib/imagem";
import {
  excluirRecebimento,
  fotoDoRecebimento,
  listarRecebimentos,
  Recebimento,
  registrarRecebimento,
  resumoRecebimentos,
  SITUACOES,
  SituacaoRecebimento,
} from "@/lib/recebimentos";
import { useSessao } from "@/lib/sessao";

/**
 * Recebimento de notas (migração 162, pedido do dono de 24/11/2026).
 *
 * 🔑 **Só registro**: quem recebe a mercadoria diz "recebi a nota X do fornecedor Y, de tal
 * data", com foto se quiser. A lista mostra se a nota já chegou ao sistema — é o que cobra a
 * nota que se perdeu entre a porta e quem lança.
 * ⚠️ A foto é reduzida no navegador antes de ir (a do celular passa dos 2 MB).
 */

const hojeIso = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const dataBr = (s: string) => s.split("-").reverse().join("/");
const COR: Record<SituacaoRecebimento, string> = {
  FALTA: "bg-alerta-claro text-alerta",
  NO_SISTEMA: "bg-superficie2 text-suave",
  LANCADA: "bg-erva-claro text-erva",
};

function Formulario({ aoRegistrar }: { aoRegistrar: () => void }) {
  const aviso = useAviso();
  const fonte = useMemo(() => fonteFornecedores(), []);
  const [numero, setNumero] = useState("");
  const [fornecedor, setFornecedor] = useState<{ id: number; rotulo: string } | null>(null);
  const [foraDoCadastro, setForaDoCadastro] = useState(false);
  const [texto, setTexto] = useState("");
  const [data, setData] = useState(hojeIso());
  const [obs, setObs] = useState("");
  const [foto, setFoto] = useState<File | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [repetida, setRepetida] = useState("");
  const [rodada, setRodada] = useState(0);
  const campoNumero = useRef<HTMLInputElement>(null);

  function limpar() {
    setNumero(""); setFornecedor(null); setTexto(""); setObs(""); setFoto(null); setErro("");
    setData(hojeIso()); setRepetida(""); setRodada((n) => n + 1);
    campoNumero.current?.focus();
  }

  async function enviar(e?: FormEvent, mesmoAssim = false) {
    e?.preventDefault();
    if (!numero.trim()) return setErro("Informe o número da nota.");
    if (foraDoCadastro ? !texto.trim() : !fornecedor) return setErro("Diga de que fornecedor é a nota.");
    if (!data) return setErro("Informe a data da nota.");
    setOcupado(true);
    setErro("");
    try {
      const fd = new FormData();
      fd.append("numero_nota", numero.trim());
      fd.append("data_nota", data);
      if (foraDoCadastro) fd.append("fornecedor_texto", texto.trim());
      else fd.append("id_fornecedor", String(fornecedor!.id));
      if (obs.trim()) fd.append("observacao", obs.trim());
      if (mesmoAssim) fd.append("mesmo_assim", "true");
      if (foto) fd.append("foto", await reduzirFoto(foto));
      const r = await registrarRecebimento(fd);
      aviso.sucesso(r.message);
      limpar();
      aoRegistrar();
    } catch (x) {
      const msg = x instanceof Error ? x.message : "Não foi possível registrar";
      if (/já foi registrada/.test(msg) && !mesmoAssim) setRepetida(msg);
      else setErro(msg);
    } finally {
      setOcupado(false);
    }
  }

  return (
    <form id="recebimento-form" onSubmit={(e) => void enviar(e)} className="flex flex-col gap-4">
      <h2 className="text-[17px] font-bold tracking-tight">Recebi uma nota</h2>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <div className="grid gap-4 md:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_minmax(0,11rem)]">
        <Campo rotulo="Número da nota">
          <input ref={campoNumero} className="campo" id="recebimento-numero" maxLength={30}
                 inputMode="numeric" placeholder="Ex.: 12345" value={numero}
                 onChange={(e) => setNumero(e.target.value)} />
        </Campo>
        <div>
          <Campo rotulo="Fornecedor">
            {foraDoCadastro ? (
              <input className="campo" id="recebimento-fornecedor-texto" maxLength={120}
                     placeholder="Nome do fornecedor" value={texto}
                     onChange={(e) => setTexto(e.target.value)} />
            ) : (
              <BuscaCadastro key={rodada} id="recebimento-fornecedor" fonte={fonte} selecionado={fornecedor}
                             aoEscolher={(f) => setFornecedor(f ? { id: f.id, rotulo: f.nome } : null)} />
            )}
          </Campo>
          <button type="button" id="recebimento-alternar"
                  className="mt-1 text-[13px] font-semibold text-erva underline underline-offset-2"
                  onClick={() => { setForaDoCadastro((v) => !v); setFornecedor(null); setTexto(""); }}>
            {foraDoCadastro ? "buscar no cadastro" : "não está no cadastro"}
          </button>
        </div>
        <Campo rotulo="Data da nota">
          <input type="date" className="campo" id="recebimento-data" value={data} max={hojeIso()}
                 onChange={(e) => setData(e.target.value)} />
        </Campo>
      </div>
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Campo rotulo="Foto da nota" opcional>
          <SeletorDeArquivo id="recebimento-foto" accept="image/*" arquivo={foto}
                            onEscolher={setFoto} rotulo="Tirar ou escolher foto" />
        </Campo>
        <Campo rotulo="Observação" opcional>
          <input className="campo" id="recebimento-observacao" maxLength={300}
                 placeholder="Ex.: veio faltando uma caixa" value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>
      </div>
      <div className="flex justify-end">
        <button type="submit" className="btn btn-primario" id="recebimento-registrar" disabled={ocupado}>
          {ocupado ? "Registrando…" : "Registrar recebimento"}
        </button>
      </div>
      {repetida && (
        <Confirmacao titulo="Esta nota já foi registrada" rotuloConfirmar="Registrar mesmo assim"
                     rotuloCancelar="Não registrar" ocupado={ocupado}
                     aoConfirmar={() => { setRepetida(""); void enviar(undefined, true); }}
                     aoCancelar={() => setRepetida("")}>
          {repetida} Se for outra entrega com o mesmo número, registre mesmo assim.
        </Confirmacao>
      )}
    </form>
  );
}

function JanelaFoto({ r, aoFechar }: { r: Recebimento; aoFechar: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState("");
  useEffect(() => {
    let aberta: string | null = null;
    fotoDoRecebimento(r.id)
      .then((u) => { aberta = u; setUrl(u); })
      .catch((e) => setErro(e instanceof Error ? e.message : "Não foi possível abrir a foto"));
    return () => { if (aberta) URL.revokeObjectURL(aberta); };
  }, [r.id]);
  return (
    <Modal titulo={`Nota ${r.numero_nota} — ${r.fornecedor ?? ""}`} aoFechar={aoFechar} largura="760px">
      {erro ? <Aviso tipo="erro">{erro}</Aviso>
        : url ? <img src={url} alt={`foto da nota ${r.numero_nota}`} id="recebimento-foto-grande"
                     className="mx-auto max-h-[75vh] w-auto rounded" />
          : <Carregando />}
    </Modal>
  );
}

export default function PaginaRecebimentos() {
  const { pode, eu, unidade } = useSessao();
  const aviso = useAviso();
  const podeReceber = pode("compras.receber");
  const cuidaDasNotas = pode("compras.notas");
  const [situacao, setSituacao] = useEstadoNaUrl<string>("situacao", "", { atraso: 0 });
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [lista, setLista] = useState<Recebimento[] | null>(null);
  const [faltam, setFaltam] = useState<number | null>(null);
  const [erro, setErro] = useState("");
  const [vendoFoto, setVendoFoto] = useState<Recebimento | null>(null);
  const [apagando, setApagando] = useState<Recebimento | null>(null);
  const pag = usePaginacao("recebimentos", { filtros: [situacao, busca, unidade] });

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    setErro("");
    try {
      const q: Record<string, string> = { ...pag.parametros };
      if (situacao) q.situacao = situacao;
      if (busca.trim()) q.busca = busca.trim();
      const [l, r] = await Promise.all([listarRecebimentos(q), resumoRecebimentos()]);
      setLista(l.itens);
      if (l.total !== null) pag.setTotal(l.total);
      setFaltam(r.faltam);
    } catch (e) {
      setLista([]);
      setErro(e instanceof Error ? e.message : "Falha ao carregar os recebimentos");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, situacao, busca, unidade, pag.offset, pag.porPagina]);

  useEffect(() => { void carregar(); }, [carregar]);

  async function apagar() {
    if (!apagando) return;
    try {
      const r = await excluirRecebimento(apagando.id);
      aviso.sucesso(r.message);
      setApagando(null);
      void carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível apagar");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela caminho="Compras" titulo="Recebimento de notas"
                     explica={<>Recebeu mercadoria com nota? Registre aqui o número, o fornecedor e a
                       data, com foto se quiser. É só registro: não mexe no estoque. A lista mostra se
                       a nota já chegou ao sistema.</>}
                     acoes={<BotaoExportar relatorio="recebimento-notas" />} />

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {podeReceber && <Cartao><Formulario aoRegistrar={() => void carregar()} /></Cartao>}

      <Cartao>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-[13.5px]">
          {(["", "FALTA", "NO_SISTEMA", "LANCADA"] as const).map((s) => (
            <button key={s || "todas"} type="button" data-situacao={s || "todas"}
                    className={`btn btn-pequeno ${situacao === s ? "btn-primario" : "btn-secundario"}`}
                    onClick={() => setSituacao(s)}>
              {s ? SITUACOES[s] : "Todas"}
              {s === "FALTA" && faltam ? ` (${faltam})` : ""}
            </button>
          ))}
          <div className="w-full sm:ml-auto sm:w-60">
            <input className="campo py-1.5" id="recebimento-busca" placeholder="nota ou fornecedor"
                   aria-label="buscar nota ou fornecedor" value={busca} onChange={(e) => setBusca(e.target.value)} />
          </div>
        </div>

        {!lista ? <Carregando /> : !lista.length ? (
          <Vazio>{situacao || busca ? "Nada com esse filtro." : "Nenhuma nota registrada ainda."}</Vazio>
        ) : (
          <ul className="divide-y divide-[var(--borda)]" id="recebimento-lista">
            {lista.map((r) => (
              <li key={r.id} data-recebimento={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                <div className="min-w-[12rem] flex-1">
                  <p className="font-semibold">
                    Nota {r.numero_nota} <span className="font-normal text-suave">· {r.fornecedor ?? "—"}</span>
                  </p>
                  <p className="text-[12.5px] text-suave">
                    de {dataBr(r.data_nota)} · recebida por {r.recebido_por_nome ?? "—"}
                    {r.observacao && <> · {r.observacao}</>}
                  </p>
                </div>
                <span className={`rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold ${COR[r.situacao]}`}
                      data-situacao-recebimento={r.situacao}>
                  {SITUACOES[r.situacao]}
                </span>
                <span className="flex items-center gap-1">
                  {r.id_nota && cuidaDasNotas && (
                    <Link href={`/compras/${r.id_nota}`} className="btn btn-terciario btn-pequeno">ver nota</Link>
                  )}
                  {r.tem_foto && (
                    <button type="button" className="btn btn-secundario btn-pequeno" data-acao="foto"
                            onClick={() => setVendoFoto(r)}>Foto</button>
                  )}
                  {(cuidaDasNotas || r.recebido_por === eu?.id) && (
                    <button type="button" className="btn btn-terciario btn-pequeno" data-acao="apagar"
                            onClick={() => setApagando(r)}>Apagar</button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Paginacao p={pag} rotulo="notas" />
      </Cartao>

      {vendoFoto && <JanelaFoto r={vendoFoto} aoFechar={() => setVendoFoto(null)} />}
      {apagando && (
        <Confirmacao titulo="Apagar este registro?" rotuloConfirmar="Apagar" rotuloCancelar="Manter" perigo
                     aoConfirmar={() => void apagar()} aoCancelar={() => setApagando(null)}>
          O registro da nota {apagando.numero_nota} ({apagando.fornecedor}) sai da lista
          {apagando.tem_foto ? ", com a foto" : ""}. Use só para registro feito por engano.
        </Confirmacao>
      )}
    </div>
  );
}
