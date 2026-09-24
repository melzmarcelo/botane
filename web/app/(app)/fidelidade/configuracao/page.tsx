"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Campo, Carregando, Cartao, Confirmacao } from "@/components/ui";
import {
  DIAS,
  obterConfig,
  salvarConfig,
  trocarToken,
  type FidelidadeConfig,
} from "@/lib/fidelidade";

import ImpressaoDosQrCodes from "./impressao";
import LocalizacaoDoCheckin from "./localizacao";

/**
 * Fidelidade → Configuração: as regras do cartão de visitas e a impressão dos QR.
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"no menu podemos ter Fidelidade —
 * Configuração, onde vamos configurar a quantidade, o prêmio, os dias de validade,
 * os dias de consumo. Porque somente conta ponto de segunda a sexta e pode consumir
 * de segunda a sexta. Mas deixar configurado."*
 *
 * ⚠️ **A configuração é da REDE** — o cadastro do cliente é único, e o cartão
 * também. Se a LOJA participa se liga em Portal de Clientes → Configuração.
 */
export default function ConfiguracaoDaFidelidade() {
  const aviso = useAviso();
  const [cfg, setCfg] = useState<FidelidadeConfig | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [trocando, setTrocando] = useState(false);

  useEffect(() => {
    obterConfig()
      .then(setCfg)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar a fidelidade"));
  }, []);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!cfg) return <Carregando />;

  const mudar = <K extends keyof FidelidadeConfig>(k: K, v: FidelidadeConfig[K]) =>
    setCfg({ ...cfg, [k]: v });
  const alternarDia = (campo: "dias_pontua" | "dias_consumo", d: number) =>
    mudar(
      campo,
      cfg[campo].includes(d) ? cfg[campo].filter((x) => x !== d) : [...cfg[campo], d].sort(),
    );

  async function salvar() {
    if (!cfg) return;
    setOcupado(true);
    try {
      const r = await salvarConfig({
        visitas: Number(cfg.visitas),
        premio: cfg.premio,
        validade_dias: Number(cfg.validade_dias),
        dias_pontua: cfg.dias_pontua,
        dias_consumo: cfg.dias_consumo,
        so_no_horario: cfg.so_no_horario,
        site_url: cfg.site_url,
        exige_local: cfg.exige_local,
        raio_m: Number(cfg.raio_m),
      });
      setCfg(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  async function novoQr() {
    setTrocando(false);
    try {
      const r = await trocarToken();
      setCfg(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível trocar o QR code");
    }
  }

  const dias = (campo: "dias_pontua" | "dias_consumo", rotulo: string) => (
    <fieldset>
      <legend className="rotulo-campo">{rotulo}</legend>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {DIAS.map((d) => (
          <button
            key={d.v}
            type="button"
            aria-pressed={cfg[campo].includes(d.v)}
            onClick={() => alternarDia(campo, d.v)}
            className={`btn px-3 py-1.5 text-[13px] ${
              cfg[campo].includes(d.v) ? "btn-primario" : "btn-secundario"
            }`}
          >
            {d.r}
          </button>
        ))}
      </div>
    </fieldset>
  );

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes · Fidelidade</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Configuração</h1>
        <ExplicaTela>
          O cartão de visitas: o cliente lê o QR code da mesa, faz o check-in pelo site e, ao
          completar as visitas, ganha o prêmio. Uma visita por dia. As regras valem para todas
          as lojas.
        </ExplicaTela>
      </header>

      {!cfg.ligada && (
        <Aviso tipo="info">
          Esta loja ainda não participa. Ligue <b>Utiliza Fidelidade</b> em{" "}
          <Link href="/reservas/configuracoes" className="link-acao">
            Portal de Clientes → Configuração
          </Link>{" "}
          para o site mostrar o cartão e o QR code valer aqui.
        </Aviso>
      )}

      <Cartao titulo="O cartão" descricao="Mudar as regras não altera prêmios já ganhos.">
        <div className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-[140px_1fr_160px]">
            <Campo rotulo="Visitas para o prêmio">
              <input className="campo mono" type="number" min={1} max={100}
                     value={cfg.visitas} onChange={(e) => mudar("visitas", Number(e.target.value))} />
            </Campo>
            <Campo rotulo="Prêmio">
              <input className="campo" maxLength={120} value={cfg.premio}
                     onChange={(e) => mudar("premio", e.target.value)} />
            </Campo>
            <Campo rotulo="Validade do prêmio" dica="dias depois de completar">
              <input className="campo mono" type="number" min={1} max={365}
                     value={cfg.validade_dias}
                     onChange={(e) => mudar("validade_dias", Number(e.target.value))} />
            </Campo>
          </div>
          {dias("dias_pontua", "Dias em que a visita conta")}
          {dias("dias_consumo", "Dias em que o prêmio pode ser consumido")}
          <label className="flex items-start gap-3">
            <input type="checkbox" className="mt-1" checked={cfg.so_no_horario}
                   onChange={(e) => mudar("so_no_horario", e.target.checked)} />
            <span className="text-[14px]">
              Check-in só com a casa aberta
              <span className="block text-[13px] text-suave">
                Usa o horário de funcionamento do Portal. Sem isto, quem fotografar o QR code
                poderia fazer check-in de casa.
              </span>
            </span>
          </label>
          <LocalizacaoDoCheckin
            cfg={cfg}
            aoMudar={(exige, raio) => setCfg({ ...cfg, exige_local: exige, raio_m: raio })}
            aoGravarLocal={setCfg}
          />
          <div className="flex justify-end">
            <button className="btn btn-primario" onClick={() => void salvar()}
                    aria-busy={ocupado} disabled={ocupado}>
              {ocupado ? "…" : "Salvar"}
            </button>
          </div>
        </div>
      </Cartao>

      <Cartao
        titulo="O QR code"
        descricao="Todos os QR codes desta loja abrem o mesmo endereço."
        acao={
          <button className="link-acao link-acao-erro" onClick={() => setTrocando(true)}>
            gerar outro
          </button>
        }
      >
        <div className="flex flex-col gap-4">
          <Campo rotulo="Endereço do site" dica="Salve o cartão depois de mudar.">
            <input className="campo mono" value={cfg.site_url}
                   onChange={(e) => mudar("site_url", e.target.value)} />
          </Campo>
          <p className="break-all text-[13px] text-suave">
            O QR code abre: <span className="mono text-tinta">{cfg.link}</span>
          </p>
          <ImpressaoDosQrCodes cfg={cfg} />
        </div>
      </Cartao>

      {trocando && (
        <Confirmacao
          titulo="Gerar outro QR code?"
          perigo
          rotuloConfirmar="Sim, gerar outro"
          aoConfirmar={() => void novoQr()}
          aoCancelar={() => setTrocando(false)}
        >
          <p>
            Os QR codes já impressos <b>deixam de valer na hora</b> — o check-in por eles será
            recusado. Use se um QR code vazou; depois, imprima e troque todos.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
