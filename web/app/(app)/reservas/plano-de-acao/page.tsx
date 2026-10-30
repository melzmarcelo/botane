"use client";

import { useCallback, useEffect, useState } from "react";

import ExplicaTela from "@/components/explica-tela";
import { Aviso, Carregando } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import {
  verPlanoDeAcao,
  type CriteriosDoPlano,
  type ListaDoPlano,
  type PlanoDeAcao,
} from "@/lib/reservas";

import ListaDoPlanoDeAcao from "./lista";

/**
 * O Plano de ação das reservas — quem vale a pena chamar de volta.
 *
 * 🔑 **Pedido do dono (30/10/2026):** *"comece pelo plano de ação de reservas"*, a tela do
 * LeadsFood que a casa usa. Três listas (VIPs em risco, organizadores de grupo sumidos,
 * adormecidos), cada pessoa numa só. A regra mora em `services/reservas_plano.py`.
 * ⚠️ Os critérios valem só para esta visita da tela: são uma lente, não configuração.
 */

const LISTAS: { v: ListaDoPlano; titulo: string; curto: string }[] = [
  { v: "vips", titulo: "VIPs em risco", curto: "VIPs para reativar" },
  { v: "organizadores", titulo: "Organizadores de grupo sumidos", curto: "organizadores de grupo" },
  { v: "adormecidos", titulo: "Adormecidos", curto: "adormecidos para convidar" },
];

const MODELOS: Record<ListaDoPlano, string> = {
  vips:
    "Olá, {nome}! Aqui é do {loja}. Faz um tempinho que você não vem e sentimos sua falta. " +
    "Que tal reservar uma mesa esta semana? Vai ser um prazer receber você de novo.",
  organizadores:
    "Olá, {nome}! Aqui é do {loja}. Foi ótimo receber sua turma aqui. Tem algum encontro " +
    "vindo por aí? É só responder esta mensagem que a gente separa a mesa para o grupo.",
  adormecidos:
    "Olá, {nome}! Aqui é do {loja}. Obrigado pela sua visita. Queremos receber você de novo: " +
    "quando quiser, é só responder por aqui que reservamos sua mesa.",
};

const CAMPOS: { k: keyof CriteriosDoPlano; r: string }[] = [
  { k: "vip_reservas", r: "VIP: reservas, pelo menos" },
  { k: "vip_dias", r: "VIP: sem vir há (dias)" },
  { k: "grupo_pessoas", r: "Grupo grande: pessoas, a partir de" },
  { k: "grupo_reservas", r: "Organizador: grupos, pelo menos" },
  { k: "grupo_dias", r: "Organizador: sem vir há (dias)" },
  { k: "adormecido_max", r: "Adormecido: reservas, até" },
  { k: "adormecido_dias", r: "Adormecido: sem vir há (dias)" },
];

function descricao(lista: ListaDoPlano, c: CriteriosDoPlano) {
  if (lista === "vips")
    return `Fizeram ${c.vip_reservas} ou mais reservas e não voltam há ${c.vip_dias} dias ou mais. Vínculo forte, recuperável.`;
  if (lista === "organizadores")
    return `Reservaram ${c.grupo_reservas} ou mais grupos de ${c.grupo_pessoas}+ pessoas e não voltam há ${c.grupo_dias} dias ou mais. Uma resposta traz a mesa inteira.`;
  return `Vieram até ${c.adormecido_max} vezes e sumiram há ${c.adormecido_dias} dias ou mais. Um convite pode reabrir a porta.`;
}

export default function PlanoDeAcaoPage() {
  const [lista, setLista] = useEstadoNaUrl<string>("lista", "vips");
  const atual = (LISTAS.find((l) => l.v === lista)?.v ?? "vips") as ListaDoPlano;
  const [plano, setPlano] = useState<PlanoDeAcao | null>(null);
  const [rascunho, setRascunho] = useState<Partial<Record<keyof CriteriosDoPlano, string>>>({});
  const [erro, setErro] = useState("");
  const [modelos, setModelos] = useState(MODELOS);

  const carregar = useCallback(async (criterios: Partial<CriteriosDoPlano> = {}) => {
    try {
      const p = await verPlanoDeAcao(criterios);
      setPlano(p);
      setRascunho(Object.fromEntries(
        Object.entries(p.criterios).map(([k, v]) => [k, String(v)]),
      ));
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o plano de ação");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const aplicar = () => {
    const c: Partial<CriteriosDoPlano> = {};
    for (const { k } of CAMPOS) {
      const n = Number(rascunho[k]);
      if (Number.isInteger(n) && n > 0) c[k] = n;
    }
    void carregar(c);
  };

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes · Reservas</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Plano de ação</h1>
        <ExplicaTela>
          Quem vale a pena chamar de volta, pelas reservas desta loja: os VIPs que pararam de
          vir, quem organizava grupos grandes e quem veio poucas vezes e sumiu. Cada cliente
          aparece numa lista só, e quem já tem reserva marcada fica de fora. O botão abre o
          WhatsApp com o convite pronto para você revisar e enviar.
        </ExplicaTela>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!plano ? (
        !erro && <Carregando />
      ) : (
        <>
          <section className="cartao px-5 py-4">
            <p className="rotulo">Clientes para recuperar agora</p>
            <b className="mono mt-1 block text-[32px] leading-none">{plano.resumo.total}</b>
            <div className="mt-4 grid grid-cols-3 gap-2 sm:gap-3 [&>*]:min-w-0">
              {LISTAS.map((l) => (
                <button
                  key={l.v}
                  type="button"
                  aria-pressed={atual === l.v}
                  onClick={() => setLista(l.v)}
                  className={`cartao px-3 py-3 text-left hover:border-[var(--color-erva)] ${
                    atual === l.v ? "ring-1 ring-[var(--color-erva)]" : ""}`}
                >
                  <b className="mono block text-[24px] leading-none">{plano.resumo[l.v]}</b>
                  <span className="mt-1 block text-[12px] leading-tight text-suave">{l.curto}</span>
                </button>
              ))}
            </div>
          </section>

          <details className="cartao px-5 py-4">
            <summary className="cursor-pointer font-medium">Critérios</summary>
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 [&>*]:min-w-0">
              {CAMPOS.map(({ k, r }) => (
                <label key={k} className="block">
                  <span className="rotulo-campo">{r}</span>
                  <input
                    className="campo mt-1.5"
                    inputMode="numeric"
                    value={rascunho[k] ?? ""}
                    onChange={(e) =>
                      setRascunho({ ...rascunho, [k]: e.target.value.replace(/\D/g, "") })}
                  />
                </label>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" className="btn btn-primario" onClick={aplicar}>
                Aplicar
              </button>
              <button type="button" className="btn btn-secundario" onClick={() => void carregar()}>
                Voltar ao padrão
              </button>
            </div>
          </details>

          <ListaDoPlanoDeAcao
            key={atual}
            lista={atual}
            titulo={LISTAS.find((l) => l.v === atual)!.titulo}
            descricao={descricao(atual, plano.criterios)}
            pessoas={plano[atual]}
            loja={plano.loja ?? "nossa casa"}
            modelo={modelos[atual]}
            setModelo={(v) => setModelos({ ...modelos, [atual]: v })}
          />
        </>
      )}
    </div>
  );
}
