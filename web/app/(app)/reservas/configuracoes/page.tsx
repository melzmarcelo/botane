"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import ExplicaTela from "@/components/explica-tela";

/**
 * A primeira tela do módulo de Reservas: quando a casa abre, até quando aceita
 * marcar, e quanto tempo cada refeição segura a mesa.
 *
 * 🔑 **Pedido do dono (14/09/2026):** *"isto tudo vai ser habilitado via
 * parâmetro na loja… e a primeira tela que é as configurações"*. O estudo do
 * módulo está em `docs/reservas-esboco.md`; o protótipo navegável, em
 * `apresentacao/reservas-prototipo.html`.
 *
 * 🔑 **São TRÊS horas por dia, não uma.** `abre` e `fecha` são a loja;
 * `última reserva` é até quando a agenda aceita marcar. O site que a casa usa
 * hoje anuncia "Ter-Sex 09h30–17h00", e 17h ali é a última reserva — a casa
 * continua aberta depois disso. A diferença entre as duas é exatamente a
 * permanência de quem senta por último.
 *
 * 🔑 **E a permanência não descreve a casa: ela DECIDE disponibilidade.** É o
 * que diz quando a mesa das 12h volta a aparecer como livre. Curta demais vende
 * mesa ocupada; longa demais recusa mesa vazia. Nenhum dos dois erros aparece
 * nesta tela — os dois aparecem no salão.
 *
 * ⚠️ **`dia_semana` é ISO: 1 = segunda … 7 = domingo**, como o resto do sistema
 * (`parametros.fechamento_dia_semana`). O servidor manda a semana pronta, com
 * nome e ordem — a tela não converte nada, e é por isso que não há aqui um
 * segundo jeito de contar os dias.
 */

type Horario = {
  dia_semana: number;
  nome: string;
  aberto: boolean;
  abre: string;
  fecha: string;
  ultima_reserva: string;
};

type Faixa = { id?: number; nome: string; de: string; ate: string; minutos: number };

type Config = {
  aceita_online: boolean;
  confirmacao: "AUTOMATICA" | "MANUAL";
  teto_online: number;
  tolerancia_min: number;
  folga_min: number;
  passo_min: number;
  antecedencia_min_horas: number;
  antecedencia_max_dias: number;
  cadastro_completo: boolean;
  /** A loja participa da fidelidade (migração 091). */
  fidelidade_ligada: boolean;
  /** 🔑 As mensagens que o site do cliente abre no WhatsApp (migração 081).
   *  Nulas = usa o padrão da casa. */
  whatsapp_texto: string | null;
  whatsapp_texto_reserva: string | null;
  horarios: Horario[];
  permanencias: Faixa[];
  dias_abertos: number;
  ligado: boolean;
};

const NUMEROS: { campo: keyof Config; nome: string; dica: string }[] = [
  {
    campo: "teto_online",
    nome: "Maior grupo pelo site",
    dica: "acima disso, o cliente fala com a casa",
  },
  {
    campo: "tolerancia_min",
    nome: "Tolerância de atraso (min)",
    dica: "depois disso a mesa volta a ficar livre",
  },
  {
    campo: "folga_min",
    nome: "Folga entre reservas (min)",
    dica: "tempo de limpar e arrumar a mesa",
  },
  {
    campo: "passo_min",
    nome: "Horários de quanto em quanto (min)",
    dica: "o intervalo oferecido ao cliente",
  },
  {
    campo: "antecedencia_min_horas",
    nome: "Antecedência mínima (horas)",
    dica: "abaixo disso, só falando com a casa",
  },
  {
    campo: "antecedencia_max_dias",
    nome: "Antecedência máxima (dias)",
    dica: "até onde a agenda se abre",
  },
];

export default function ConfiguracoesDeReservas() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [cfg, setCfg] = useState<Config | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setCfg(await api.get<Config>("/reservas/configuracao"));
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a configuração");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  function mudar<K extends keyof Config>(campo: K, valor: Config[K]) {
    setCfg((c) => (c ? { ...c, [campo]: valor } : c));
  }

  function mudarDia(dia: number, campo: keyof Horario, valor: string | boolean) {
    setCfg((c) =>
      c
        ? {
            ...c,
            horarios: c.horarios.map((h) =>
              h.dia_semana === dia ? { ...h, [campo]: valor } : h,
            ),
          }
        : c,
    );
  }

  function mudarFaixa(i: number, campo: keyof Faixa, valor: string | number) {
    setCfg((c) =>
      c
        ? { ...c, permanencias: c.permanencias.map((f, j) => (j === i ? { ...f, [campo]: valor } : f)) }
        : c,
    );
  }

  async function salvar() {
    if (!cfg) return;
    setOcupado(true);
    try {
      const r = await api.put<{ message: string } & Config>("/reservas/configuracao", {
        aceita_online: cfg.aceita_online,
        confirmacao: cfg.confirmacao,
        teto_online: Number(cfg.teto_online),
        tolerancia_min: Number(cfg.tolerancia_min),
        folga_min: Number(cfg.folga_min),
        passo_min: Number(cfg.passo_min),
        antecedencia_min_horas: Number(cfg.antecedencia_min_horas),
        antecedencia_max_dias: Number(cfg.antecedencia_max_dias),
        cadastro_completo: cfg.cadastro_completo,
        fidelidade_ligada: cfg.fidelidade_ligada,
        whatsapp_texto: cfg.whatsapp_texto,
        whatsapp_texto_reserva: cfg.whatsapp_texto_reserva,
        horarios: cfg.horarios,
        permanencias: cfg.permanencias.map((f) => ({
          nome: f.nome,
          de: f.de,
          ate: f.ate,
          minutos: Number(f.minutos),
        })),
      });
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!cfg) return <Carregando />;

  const somenteLeitura = !pode("reservas.configurar");

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo">Configuração do Portal de Clientes</h1>
          <ExplicaTela>
            Vale para esta loja. Outra loja com o portal tem a configuração dela.
          </ExplicaTela>
        </div>
        {!somenteLeitura && (
          <button className="btn btn-primario" onClick={() => void salvar()} aria-busy={ocupado} disabled={ocupado}>
            {ocupado ? "Salvando…" : "Salvar"}
          </button>
        )}
      </div>

      {/* 🔑 **A tela DIZ o que ainda falta**, e quem conta é o servidor
          (`dias_abertos`). A casa nasce fechada em todos os dias de propósito —
          semear "segunda a sábado, 9h às 18h" faria a agenda afirmar um horário
          que ninguém conferiu. Mas nascer fechada sem avisar pareceria pronta. */}
      {cfg.dias_abertos === 0 && (
        <Aviso tipo="info">
          Nenhum dia da semana está aberto ainda, então a agenda não tem horário para oferecer.
          Marque os dias em que a casa atende, abaixo, e salve.
        </Aviso>
      )}

      <Cartao
        titulo="Horário de funcionamento"
        descricao="Abre e fecha são a loja. A última reserva é até quando a agenda aceita marcar — a diferença entre as duas é a permanência de quem senta por último."
      >
        <div className="grid-rolante">
          <table className="tabela">
            <thead>
              <tr>
                <th className="min-w-[110px]">Dia</th>
                <th className="w-[90px]">Atende</th>
                <th className="w-[130px]">Abre</th>
                <th className="w-[130px]">Fecha</th>
                <th className="w-[150px]">Última reserva</th>
              </tr>
            </thead>
            <tbody>
              {cfg.horarios.map((h) => (
                <tr key={h.dia_semana} className={h.aberto ? "" : "text-suave"}>
                  <td className="font-medium">{h.nome}</td>
                  <td>
                    <input
                      type="checkbox"
                      disabled={somenteLeitura}
                      aria-label={`${h.nome} atende`}
                      checked={h.aberto}
                      onChange={(e) => mudarDia(h.dia_semana, "aberto", e.target.checked)}
                    />
                  </td>
                  {(["abre", "fecha", "ultima_reserva"] as const).map((campo, n) => (
                    <td key={campo}>
                      <input
                        className="campo mono"
                        type="time"
                        disabled={somenteLeitura}
                        aria-label={`${h.nome} ${["abre", "fecha", "última reserva"][n]}`}
                        value={h[campo]}
                        onChange={(e) => mudarDia(h.dia_semana, campo, e.target.value)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* ⚠️ As horas ficam gravadas mesmo com o dia fechado: é assim que a
            casa fecha a segunda sem perder o horário dela. */}
        <p className="mt-3 text-[13px] text-suave">
          Dia desmarcado guarda o horário dele — reabrir não obriga a redigitar.
        </p>
      </Cartao>

      <Cartao
        titulo="Tempo de permanência"
        descricao="Quanto tempo a mesa fica ocupada. É este número que decide quando ela volta a aparecer como livre — um valor só para o dia inteiro erra nas duas pontas."
        acao={
          !somenteLeitura && (
            <button
              className="btn btn-secundario"
              onClick={() =>
                mudar("permanencias", [
                  ...cfg.permanencias,
                  { nome: "Nova faixa", de: "18:00", ate: "23:59", minutos: 90 },
                ])
              }
            >
              + faixa
            </button>
          )
        }
      >
        <div className="grid-rolante">
          <table className="tabela">
            <thead>
              <tr>
                <th className="min-w-[150px]">Faixa</th>
                <th className="w-[120px]">Das</th>
                <th className="w-[120px]">Até</th>
                <th className="num w-[130px]">Permanência</th>
                <th className="min-w-[140px]">Quem senta às…</th>
                {!somenteLeitura && <th className="w-[80px]"></th>}
              </tr>
            </thead>
            <tbody>
              {cfg.permanencias.map((f, i) => (
                <tr key={i}>
                  <td>
                    <input
                      className="campo"
                      disabled={somenteLeitura}
                      aria-label={`nome da faixa ${i + 1}`}
                      value={f.nome}
                      onChange={(e) => mudarFaixa(i, "nome", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono"
                      type="time"
                      disabled={somenteLeitura}
                      aria-label={`faixa ${i + 1} começa`}
                      value={f.de}
                      onChange={(e) => mudarFaixa(i, "de", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono"
                      type="time"
                      disabled={somenteLeitura}
                      aria-label={`faixa ${i + 1} termina`}
                      value={f.ate}
                      onChange={(e) => mudarFaixa(i, "ate", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono text-right"
                      type="number"
                      min={5}
                      max={720}
                      step={5}
                      disabled={somenteLeitura}
                      aria-label={`permanência da faixa ${i + 1}`}
                      value={f.minutos}
                      onChange={(e) => mudarFaixa(i, "minutos", e.target.value)}
                    />
                  </td>
                  {/* Diz em português o que o número faz: quem senta no começo
                      da faixa sai por volta de tal hora. */}
                  <td className="mono text-[13px] text-suave">{saidaDe(f)}</td>
                  {!somenteLeitura && (
                    <td className="text-right">
                      <button
                        className="link-acao link-acao-erro"
                        aria-label={`remover faixa ${i + 1}`}
                        onClick={() =>
                          mudar(
                            "permanencias",
                            cfg.permanencias.filter((_f, j) => j !== i),
                          )
                        }
                      >
                        remover
                      </button>
                    </td>
                  )}
                </tr>
              ))}
              {!cfg.permanencias.length && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-suave">
                    Sem faixa nenhuma, o sistema não sabe por quanto tempo a mesa fica ocupada.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[13px] text-suave">
          ⚠️ As faixas não podem se sobrepor: cada horário do dia tem uma permanência só.
        </p>
      </Cartao>

      <Cartao
        titulo="Regras da reserva"
        descricao="O que a agenda pode prometer sozinha."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {NUMEROS.map((n) => (
            <Campo key={String(n.campo)} rotulo={n.nome} dica={n.dica}>
              <input
                className="campo mono text-right"
                type="number"
                min={0}
                disabled={somenteLeitura}
                value={String(cfg[n.campo] ?? "")}
                onChange={(e) => mudar(n.campo, Number(e.target.value) as never)}
              />
            </Campo>
          ))}
        </div>

        <div className="mt-5 flex flex-col gap-4">
          {/* 🔑 **A pergunta que muda o fluxo inteiro do cliente**, e a única
              das cinco do esboço que o site de hoje não deixa ver de fora. */}
          <Campo
            rotulo="Depois de reservar"
            dica="muda o passo final do cliente: “está confirmada” ou “a casa vai confirmar”"
          >
            <select
              className="campo"
              disabled={somenteLeitura}
              value={cfg.confirmacao}
              onChange={(e) => mudar("confirmacao", e.target.value as Config["confirmacao"])}
            >
              <option value="AUTOMATICA">Confirma na hora</option>
              <option value="MANUAL">Fica aguardando a casa</option>
            </select>
          </Campo>

          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1"
              disabled={somenteLeitura}
              checked={cfg.aceita_online}
              onChange={(e) => mudar("aceita_online", e.target.checked)}
            />
            <span className="text-[14px]">
              Aceitar reserva pelo site
              <span className="block text-[13px] text-suave">
                Ligado, o cliente marca sozinho pelo site e a reserva cai na agenda. Desligado,
                o site mostra os horários livres e a mesa se fecha pelo WhatsApp. Precisa de
                salão e mesas cadastrados — sem eles não há horário a oferecer.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1"
              disabled={somenteLeitura}
              checked={cfg.cadastro_completo}
              onChange={(e) => mudar("cadastro_completo", e.target.checked)}
            />
            <span className="text-[14px]">
              Pedir cadastro completo de quem é novo
              {/* 🔑 **A data de nascimento entrou em 24/09/2026** (migração 086,
                  pedido do dono). Tinha saído deste texto em 21/09 porque o site
                  não a perguntava — tela que descreve campo que o site não pede
                  ensina a não confiar na tela. Agora pergunta. */}
              <span className="block text-[13px] text-suave">
                Ligado, o site pede gênero, cidade e data de nascimento além do nome.
                Desligado, só o nome — o telefone é sempre perguntado, porque é por ele que a
                casa reconhece quem volta. Vale para reservar e para abrir catálogo que
                exige cadastro.
              </span>
            </span>
          </label>

          {/* 🔑 **Pedido do dono (24/09/2026):** *"na configuração do Portal do Cliente
              criar a flag se utiliza Fidelidade."* As regras do cartão ficam em
              Fidelidade → Configuração; aqui só se a LOJA participa. */}
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1"
              disabled={somenteLeitura}
              checked={cfg.fidelidade_ligada}
              onChange={(e) => mudar("fidelidade_ligada", e.target.checked)}
            />
            <span className="text-[14px]">
              Utiliza Fidelidade
              <span className="block text-[13px] text-suave">
                Ligado, o site mostra o item Fidelidade (visitas e quanto falta para o prêmio) e
                o QR code da mesa passa a valer nesta loja. As regras do cartão ficam em
                Fidelidade → Configuração.
              </span>
            </span>
          </label>
        </div>
      </Cartao>

      {/* 🔑 **O texto do WhatsApp, escrito pela CASA** (pedido do dono,
          21/09/2026: *"em configurações da reserva, colocar o texto padrão
          configurável para o whatsapp"*). Ele estava escrito dentro do site, e
          texto que o cliente lê escrito em código só muda quando alguém
          publica — a casa que quisesse outro tom teria de pedir uma versão. */}
      <Cartao
        titulo="A mensagem que abre no WhatsApp"
        descricao="É o que o cliente vê já digitado ao tocar no botão do site. Ele ainda pode apagar e escrever o que quiser."
      >
        <div className="flex flex-col gap-4">
          {/* ⚠️ **Dois textos, não um.** Quem toca em "Entre em contato" ainda
              não escolheu nada; quem vem da reserva já tem dia, hora e quantas
              pessoas. A mesma frase nos dois ou perde o que o cliente já disse,
              ou manda "reservar para {pessoas}" sem pessoas nenhuma. */}
          <Campo
            rotulo="Quando tocam em “Entre em Contato”"
            dica="Use {casa} para o nome da casa."
          >
            <input
              className="campo"
              id="zap-texto"
              maxLength={400}
              disabled={somenteLeitura}
              placeholder="Olá! Vim pelo site do {casa}."
              value={cfg.whatsapp_texto ?? ""}
              onChange={(e) => mudar("whatsapp_texto", e.target.value)}
            />
          </Campo>
          <Campo
            rotulo="Quando escolhem um horário"
            dica="Use {pessoas}, {data} e {hora} — o site troca pelo que a pessoa escolheu."
          >
            <input
              className="campo"
              id="zap-texto-reserva"
              maxLength={400}
              disabled={somenteLeitura}
              placeholder="Olá! Queria reservar para {pessoas} pessoas no dia {data} às {hora}."
              value={cfg.whatsapp_texto_reserva ?? ""}
              onChange={(e) => mudar("whatsapp_texto_reserva", e.target.value)}
            />
          </Campo>
          {/* ⚠️ **Em branco não é vazio: é o padrão.** Quem apagar o campo sem
              querer não fica com o cliente abrindo o WhatsApp mudo. */}
          <p className="text-[13px] text-suave">
            Deixando em branco, o site usa a mensagem padrão. O número sai de
            Administração ▸ Empresa ▸ WhatsApp — sem ele, o site mostra o telefone e o
            endereço no lugar do botão.
          </p>
        </div>
      </Cartao>

      <p className="text-[13px] text-suave">
        Salões, mesas e a agenda do dia vêm em seguida.{" "}
        <Etiqueta>em construção</Etiqueta>
      </p>
    </div>
  );
}

/** "Quem senta às 12:00 sai por volta das 13:30" — o número em português. */
function saidaDe(f: Faixa): string {
  const [h, m] = (f.de || "00:00").split(":").map(Number);
  const minutos = Number(f.minutos);
  if (!Number.isFinite(h) || !Number.isFinite(m) || !Number.isFinite(minutos)) return "—";
  const total = h * 60 + m + minutos;
  const hh = String(Math.floor(total / 60) % 24).padStart(2, "0");
  const mm = String(total % 60).padStart(2, "0");
  return `${f.de} → ${hh}:${mm}`;
}
