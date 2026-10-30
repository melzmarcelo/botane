"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Cartao, SeletorDeArquivo } from "@/components/ui";
import Voltar from "@/components/voltar";
import { inteiro, plural } from "@/lib/numeros";
import { importarLeadsfood, type ArquivoLeadsfood, type ResultadoLeadsfood } from "@/lib/reservas";
import { useSessao } from "@/lib/sessao";

/**
 * Importar do LeadsFood — o sistema de leads que a casa usava antes do Portal.
 *
 * 🔑 **Pedido do dono (30/10/2026):** *"siga para a importação do LeadsFood"*. A regra mora em
 * `services/importacao_leadsfood.py`. ⚠️ **Prévia antes, sempre**: o botão de importar só
 * aparece depois dela e reenvia os MESMOS arquivos. Pode repetir com arquivos mais novos: não
 * duplica, e os selos em aberto valem como foto do dia.
 */

const ARQUIVOS: { k: ArquivoLeadsfood; r: string; como: string }[] = [
  { k: "contatos", r: "Contatos", como: "CRM → Contatos → Exportar (todas as colunas)." },
  { k: "reservas", r: "Reservas",
    como: "Operacional → Reservas: tire o filtro de status e, em Filtrar, escolha “Exibir registros excluídos” — é lá que ficam as reservas que já passaram. Depois Exportar." },
  { k: "selos", r: "Selos em aberto",
    como: "O LeadsFood não exporta check-in: é a lista de Fidelidade → Checkins sem filtro de status e sem os registros excluídos, em CSV (nome, celular, pin, campanha, status, criado_em)." },
  { k: "premios", r: "Prêmios", como: "Fidelidade → Prêmios: tire o filtro de status e Exportar." },
];

const NOMES: Record<ArquivoLeadsfood, string> = {
  contatos: "Contatos", reservas: "Reservas", selos: "Selos", premios: "Prêmios",
};

export default function ImportarLeadsfood() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const podeImportar = pode("reservas.configurar");
  const [arquivos, setArquivos] = useState<Partial<Record<ArquivoLeadsfood, File>>>({});
  const [resultado, setResultado] = useState<ResultadoLeadsfood | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");
  const algum = Object.values(arquivos).some(Boolean);

  async function enviar(simular: boolean) {
    setOcupado(true);
    setErro("");
    try {
      const r = await importarLeadsfood(arquivos, simular);
      setResultado(r);
      if (!simular) aviso.sucesso("Importação do LeadsFood gravada.");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível ler os arquivos");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/reservas/clientes">clientes</Voltar>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">Importar do LeadsFood</h1>
        <ExplicaTela>
          Traz do LeadsFood os contatos, o histórico de reservas, os selos dos cartões em aberto e
          os prêmios. Pode importar de novo com arquivos mais novos até a troca de sistema: nada
          se duplica, o cliente que já existe aqui só ganha os campos vazios e os selos em aberto
          passam a ser os do arquivo novo.
        </ExplicaTela>
      </header>

      <Cartao titulo="Os arquivos" descricao="Todos em CSV. Mande os quatro juntos ou só os que mudaram.">
        <ul className="divide-y divide-linha">
          {ARQUIVOS.map((a) => (
            <li key={a.k} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:gap-6">
              <div className="min-w-0 sm:w-[46%]">
                <b className="block">{a.r}</b>
                <span className="text-[13px] text-suave">{a.como}</span>
              </div>
              <SeletorDeArquivo id={`leadsfood-${a.k}`} accept=".csv,text/csv" disabled={!podeImportar}
                                rotulo="Escolher o CSV" arquivo={arquivos[a.k] ?? null}
                                onEscolher={(f) => {
                                  setArquivos({ ...arquivos, [a.k]: f ?? undefined });
                                  setResultado(null);
                                }} />
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-3 border-t border-linha px-5 py-4">
          <button type="button" className="btn btn-secundario" id="leadsfood-previa"
                  disabled={!algum || ocupado || !podeImportar} aria-busy={ocupado}
                  onClick={() => void enviar(true)}>
            Ver prévia
          </button>
          {!podeImportar && (
            <span className="text-[13px] text-suave">Importar pede a permissão de configurar as reservas.</span>
          )}
        </div>
      </Cartao>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {resultado && <Resultado r={resultado} ocupado={ocupado} aoImportar={() => void enviar(false)} />}
    </div>
  );
}

function Resultado({ r, ocupado, aoImportar }: {
  r: ResultadoLeadsfood; ocupado: boolean; aoImportar: () => void;
}) {
  const verbo = r.aplicado ? "" : "vão ";
  const blocos: { t: string; linhas: string[] }[] = [
    { t: "Clientes", linhas: [
      plural(r.clientes.novos, "novo", "novos"),
      `${inteiro(r.clientes.completados)} já existiam e ${r.aplicado ? "ganharam" : "ganham"} campos vazios`,
      `${inteiro(r.clientes.iguais)} já existiam e não mudam`,
    ] },
  ];
  if (r.reservas) blocos.push({ t: "Reservas", linhas: [
    plural(r.reservas.novas, "nova", "novas"),
    plural(r.reservas.atualizadas, "com status atualizado", "com status atualizado"),
    plural(r.reservas.iguais, "já importada, igual", "já importadas, iguais"),
  ] });
  if (r.selos) blocos.push({ t: "Selos em aberto", linhas: [
    `${plural(r.selos.selos, "selo", "selos")} em ${plural(r.selos.dias, "visita", "visitas")}`,
    `${plural(r.selos.clientes, "cliente", "clientes")} no arquivo`,
    ...(r.selos.ja_tinham ? [plural(r.selos.ja_tinham, "visita já importada", "visitas já importadas")] : []),
    ...(r.selos.retirados ? [`${plural(r.selos.retirados, "visita", "visitas")} ${verbo}sair (o cartão fechou no LeadsFood)`] : []),
    ...(r.selos.conflitos ? [`${plural(r.selos.conflitos, "dia", "dias")} com visita já marcada aqui: vale a daqui`] : []),
  ] });
  if (r.premios) blocos.push({ t: "Prêmios", linhas: [
    plural(r.premios.novos, "novo", "novos"),
    `${inteiro(r.premios.abertos)} ainda para usar`,
    ...(r.premios.atualizados ? [plural(r.premios.atualizados, "marcado como usado", "marcados como usados")] : []),
  ] });

  return (
    <Cartao titulo={r.aplicado ? "Importado" : "Prévia"}
            descricao={r.aplicado ? "Gravado. Os clientes já aparecem no Portal, no Painel e no Plano de ação."
              : "Nada foi gravado ainda. Confira e importe."}>
      <div className="grid grid-cols-1 gap-3 px-5 py-4 sm:grid-cols-2 lg:grid-cols-4 [&>*]:min-w-0" id="leadsfood-resumo">
        {blocos.map((b) => (
          <div key={b.t} className="rounded-lg border border-linha px-3 py-3">
            <b className="block">{b.t}</b>
            {b.linhas.map((l) => <span key={l} className="block text-[13px] text-suave">{l}</span>)}
          </div>
        ))}
      </div>
      {!r.aplicado && (
        <div className="px-5 pb-4">
          <button type="button" className="btn btn-primario" id="leadsfood-aplicar"
                  disabled={ocupado} aria-busy={ocupado} onClick={aoImportar}>
            Importar
          </button>
        </div>
      )}
      {r.recusados.length > 0 && (
        <div className="border-t border-linha px-5 py-4">
          <Aviso tipo="info">
            {plural(r.recusados.length, "linha", "linhas")} {r.aplicado ? "não entraram" : "não vão entrar"} —
            em geral celular estrangeiro ou com dígito a mais. Cadastre à mão se fizer falta.
          </Aviso>
          <div className="mt-3 grid-rolante">
            <table className="tabela" id="leadsfood-recusados">
              <thead><tr><th>Arquivo</th><th className="num">Linha</th><th>Cliente</th><th>Por quê</th></tr></thead>
              <tbody>
                {r.recusados.map((x) => (
                  <tr key={`${x.arquivo}-${x.linha}`}>
                    <td>{NOMES[x.arquivo]}</td>
                    <td className="num mono">{x.linha}</td>
                    <td>{x.nome || "—"}</td>
                    <td className="text-[13px]">{x.motivo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Cartao>
  );
}
