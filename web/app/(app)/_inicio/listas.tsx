"use client";

import Link from "next/link";

import { COR, ROTULO, type PedidoResumo } from "@/lib/pedidos";

import { diaCurto, type Producao, type Reservas } from "./tipos";

/**
 * As três listas do dia, lado a lado: pedidos do site, mesas e produção.
 *
 * 🔑 Protótipo aprovado (29/09/2026): antes cada uma era um cartão de largura inteira,
 * empilhado. Agora as contagens viram etiquetas no topo, e as próximas linhas vêm embaixo.
 * ⚠️ Cada lista só aparece quando o módulo e a permissão existem — o servidor manda nulo.
 */
export type PedidosDoInicio = {
  novos: number;
  sem_pdv: number;
  hoje: number;
  abertos: number;
  todos: number;
  linhas: PedidoResumo[];
};

const hojeIso = () => new Date().toLocaleDateString("sv-SE");

function Etq({ tom, children }: { tom?: "alerta" | "erro" | "erva"; children: React.ReactNode }) {
  const cls = tom === "alerta" ? "bg-alerta-claro text-alerta" : tom === "erro" ? "bg-erro-claro text-erro"
    : tom === "erva" ? "bg-erva-claro text-erva" : "bg-superficie2 text-suave";
  return <span className={`rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${cls}`}>{children}</span>;
}

function Lista({ titulo, href, rotuloLink, etiquetas, vazio, children }: {
  titulo: string; href: string; rotuloLink: string; etiquetas: React.ReactNode; vazio: string | null;
  children: React.ReactNode;
}) {
  return (
    <section className="cartao flex min-w-0 flex-col p-4">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-bold">{titulo}</h2>
        <Link href={href} className="link-acao text-[13px]">{rotuloLink} ›</Link>
      </div>
      <div className="mb-2 flex flex-wrap gap-1.5">{etiquetas}</div>
      {vazio ? <p className="text-[14px] text-suave">{vazio}</p> : (
        <ul className="lista-rolante flex flex-col text-[13.5px]">{children}</ul>
      )}
    </section>
  );
}

function Linha({ quando, href, texto, direita, tomQuando }: {
  quando: string; href: string; texto: string; direita: React.ReactNode; tomQuando?: "erro";
}) {
  return (
    <li className="flex items-baseline gap-2.5 border-t border-linha py-2 first:border-t-0">
      <span className={`mono w-[54px] flex-none text-[12.5px] ${tomQuando === "erro" ? "text-erro" : "text-suave"}`}>{quando}</span>
      <Link href={href} className="link-registro min-w-0 flex-1 truncate font-normal">{texto}</Link>
      <span className="flex-none">{direita}</span>
    </li>
  );
}

export function ListaDePedidos({ p }: { p: PedidosDoInicio }) {
  return (
    <Lista titulo="Pedidos do site" href="/pedidos/painel" rotuloLink="painel"
           vazio={p.linhas.length ? null : "Nenhum pedido em aberto."}
           etiquetas={<>
             {p.novos > 0 && <Etq tom="alerta">{p.novos} a confirmar</Etq>}
             {p.sem_pdv > 0 && <Etq tom="erro">{p.sem_pdv} sem lançar no PDV</Etq>}
             <Etq>{p.hoje} para hoje</Etq>
           </>}>
      {p.linhas.map((l) => {
        const d = l.para_quando.slice(0, 10);
        const hora = new Date(l.para_quando).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
        return (
          <Linha key={l.id} href={`/pedidos/${l.id}`} quando={d === hojeIso() ? hora : `${diaCurto(d)}`}
                 texto={`Nº ${l.numero} · ${l.nome}`}
                 direita={l.situacao === "CONFIRMADO" && !l.lancado_pdv_em
                   ? <Etq tom="erro">sem PDV</Etq>
                   : <Etq tom={COR[l.situacao] === "alerta" ? "alerta" : COR[l.situacao] === "erva" ? "erva" : undefined}>
                       {ROTULO[l.situacao]}</Etq>} />
        );
      })}
    </Lista>
  );
}

export function ListaDeMesas({ r }: { r: Reservas }) {
  return (
    <Lista titulo="Mesas" href="/reservas/agenda?visao=dia" rotuloLink="agenda"
           vazio={r.total ? null : "Nada marcado daqui para a frente."}
           etiquetas={<>
             <Etq>{r.hoje} hoje</Etq>
             <Etq>{r.pessoas_hoje} pessoas hoje</Etq>
             {r.pendentes > 0 && <Etq tom="alerta">{r.pendentes} a confirmar</Etq>}
           </>}>
      {r.linhas.map((l) => (
        <Linha key={l.id} href="/reservas/agenda" quando={l.data === hojeIso() ? l.hora : `${diaCurto(l.data)}`}
               texto={l.status === "PENDENTE" ? `${l.nome} · a confirmar` : l.nome}
               direita={<span className="mono text-[12.5px] text-suave">{l.pessoas} p</span>} />
      ))}
    </Lista>
  );
}

export function ListaDeProducao({ p }: { p: Producao }) {
  return (
    <Lista titulo="Para produzir" href="/producao" rotuloLink="agenda"
           vazio={p.total ? null : `Nada planejado para os próximos sete dias${p.todos_setores ? "" : " nos seus setores"}.`}
           etiquetas={<>
             <Etq>{p.hoje} hoje</Etq>
             {p.atrasadas > 0 && <Etq tom="erro">{p.atrasadas} atrasada(s)</Etq>}
             <Etq>{p.total} na semana</Etq>
           </>}>
      {p.linhas.map((l) => (
        <Linha key={l.id} href={`/produtos/${l.id_produto}`} tomQuando={l.atrasada ? "erro" : undefined}
               quando={l.data_prevista === hojeIso() ? "hoje" : diaCurto(l.data_prevista)}
               texto={l.produto}
               direita={<span className="mono text-[12.5px] text-suave">
                 {l.quantidade.toLocaleString("pt-BR")} {l.um_estoque ?? ""}</span>} />
      ))}
    </Lista>
  );
}
