"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Categoria, Local, Setor, TIPOS_PRODUTO } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import FiltroMultiplo from "@/components/filtro-multiplo";

/**
 * Montar uma contagem.
 *
 * Contar a despensa inteira é raro. O que a casa faz é contar a câmara fria, ou
 * só as bebidas, ou só o hortifrúti antes da feira. Por isso são quatro
 * filtros — local, setor, categoria e tipo —, cada um opcional, combinando com
 * E, e **em branco querendo dizer "todos"**.
 *
 * ⚠️ **A prévia é o coração desta tela.** Numa base real, filtro em branco traz
 * o cadastro inteiro; descobrir isso depois de abrir custa cancelar e
 * recomeçar. Quantos itens, de quais locais e uma amostra aparecem ANTES do
 * botão — e a conta é do servidor, o mesmo código que vai montar a contagem.
 */

type Previa = {
  total: number;
  produtos: number;
  locais: { nome: string; itens: number }[];
  amostra: { produto: string; local: string; um: string | null }[];
  ja_em_contagem: { produto: string; local: string; inventario: number }[];
  ja_em_contagem_total: number;
};

/** Um filtro: caixas de seleção, com "todos" sendo nenhuma marcada. */
function Filtro<T extends { toString(): string }>({
  titulo,
  ajuda,
  opcoes,
  escolhidos,
  aoTrocar,
}: {
  titulo: string;
  ajuda: string;
  opcoes: { valor: T; nome: string }[];
  escolhidos: T[];
  aoTrocar: (v: T[]) => void;
}) {
  const alternar = (v: T) =>
    aoTrocar(escolhidos.includes(v) ? escolhidos.filter((x) => x !== v) : [...escolhidos, v]);

  return (
    <div className="flex min-w-0 flex-col">
      <div className="flex items-baseline justify-between gap-2">
        <span className="rotulo">{titulo}</span>
        {/* ⚠️ "Todos" não é uma opção na lista: é a ausência de escolha. Uma
            caixinha "todos" que se desmarca sozinha ao marcar outra é um
            estado a mais para manter em dia, e o primeiro a divergir. */}
        {escolhidos.length > 0 && (
          <button className="link-acao" onClick={() => aoTrocar([])}>
            limpar
          </button>
        )}
      </div>
      <p className="mt-0.5 text-[12.5px] leading-snug text-suave">
        {escolhidos.length ? `${escolhidos.length} escolhido(s)` : ajuda}
      </p>
      {!opcoes.length ? (
        <p className="mt-2 text-[13px] text-suave">nada cadastrado</p>
      ) : (
        <ul className="mt-2 flex max-h-[180px] flex-col gap-px overflow-y-auto rounded border border-linha bg-linha">
          {opcoes.map((o) => (
            <li key={o.valor.toString()} className="bg-superficie">
              <label className="flex cursor-pointer items-center gap-2.5 px-3 py-2 text-[14px]">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-erva"
                  checked={escolhidos.includes(o.valor)}
                  onChange={() => alternar(o.valor)}
                />
                {o.nome}
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PaginaNovaContagem() {
  const aviso = useAviso();
  const router = useRouter();

  const [locais, setLocais] = useState<Local[]>([]);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);

  const [nome, setNome] = useState("");
  const [escLocais, setEscLocais] = useState<number[]>([]);
  const [escSetores, setEscSetores] = useState<number[]>([]);
  const [escCategorias, setEscCategorias] = useState<number[]>([]);
  const [escTipos, setEscTipos] = useState<string[]>([]);
  // ⚠️ Cega marcada por padrão: ver o saldo esperado transforma a contagem em
  // conferência — a pessoa lê 12, olha a prateleira e escreve 12.
  const [cega, setCega] = useState(true);
  // 🔑 **Quem foi escalado para contar ESTA contagem.** Vazio quer dizer
  // "qualquer um com a permissão de contar" — é o comportamento de sempre, e é
  // o que faz esta tela não obrigar ninguém a escolher.
  // ⚠️ Não é permissão, é escala: a permissão diz o que a pessoa sabe fazer,
  // isto diz quem está no turno de hoje.
  const [contadores, setContadores] = useState<number[]>([]);
  const [equipe, setEquipe] = useState<{ id: number; nome: string }[]>([]);

  const [previa, setPrevia] = useState<Previa | null>(null);
  const [carregandoPrevia, setCarregandoPrevia] = useState(false);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<Local[]>("/locais"),
      api.get<Setor[]>("/setores"),
      api.get<Categoria[]>("/categorias"),
      // ⚠️ Falhar aqui não derruba a tela: quem não pode ver a lista de
      // usuários ainda pode abrir contagem — ela só nasce sem escala, que é o
      // padrão de qualquer jeito.
      api.get<{ id: number; nome: string }[]>("/usuarios").catch(() => []),
    ])
      .then(([l, s, c, u]) => {
        setLocais(l.filter((x) => x.ativo !== false));
        setSetores(s.filter((x) => x.ativo !== false));
        setCategorias(c.filter((x) => x.ativo !== false));
        setEquipe(u as { id: number; nome: string }[]);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, []);

  const parametros = useCallback(() => {
    const q = new URLSearchParams();
    escLocais.forEach((v) => q.append("locais", String(v)));
    escSetores.forEach((v) => q.append("setores", String(v)));
    escCategorias.forEach((v) => q.append("categorias", String(v)));
    escTipos.forEach((v) => q.append("tipos", v));
    return q;
  }, [escLocais, escSetores, escCategorias, escTipos]);

  // A prévia acompanha a escolha. Vem do SERVIDOR, do mesmo código que monta a
  // contagem: uma segunda regra de seleção em TypeScript prometeria uma lista e
  // entregaria outra.
  useEffect(() => {
    let vivo = true;
    setCarregandoPrevia(true);
    api
      .get<Previa>(`/inventarios/previa?${parametros()}`)
      .then((p) => vivo && setPrevia(p))
      .catch(() => vivo && setPrevia(null))
      .finally(() => vivo && setCarregandoPrevia(false));
    return () => {
      vivo = false;
    };
  }, [parametros]);

  async function abrir() {
    setOcupado(true);
    setErro("");
    try {
      const inv = await api.post<{ id: number }>("/inventarios", {
        nome: nome.trim() || null,
        cega,
        locais: escLocais,
        setores: escSetores,
        categorias: escCategorias,
        tipos: escTipos,
        contadores,
      });
      // Abrir uma contagem é o começo de CONTAR: leva direto para a tela de
      // contagem, em vez de devolver a pessoa à lista para clicar de novo.
      router.push(`/inventario/${inv.id}`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível abrir");
      setOcupado(false);
    }
  }

  const nenhumFiltro =
    !escLocais.length && !escSetores.length && !escCategorias.length && !escTipos.length;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/inventario" className="link-voltar">
          ← Inventário
        </Link>
        <h1 className="mt-3 text-[26px] font-bold tracking-tight sm:text-[30px]">
          Nova contagem
        </h1>
        <p className="mt-1 max-w-[66ch] text-suave">
          Escolha o que entra na contagem. Cada filtro é opcional — em branco quer dizer todos —
          e eles se somam: setor <b>cozinha</b> com tipo <b>insumo</b> traz os insumos da
          cozinha.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao titulo="O que contar">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Filtro
            titulo="Locais"
            ajuda="todos os locais"
            opcoes={locais.map((l) => ({ valor: l.id, nome: l.nome }))}
            escolhidos={escLocais}
            aoTrocar={setEscLocais}
          />
          <Filtro
            titulo="Setores"
            ajuda="todos os setores"
            opcoes={setores.map((s) => ({ valor: s.id, nome: s.nome }))}
            escolhidos={escSetores}
            aoTrocar={setEscSetores}
          />
          <Filtro
            titulo="Categorias"
            ajuda="todas as categorias"
            opcoes={categorias.map((c) => ({ valor: c.id, nome: c.nome }))}
            escolhidos={escCategorias}
            aoTrocar={setEscCategorias}
          />
          <Filtro
            titulo="Tipos de produto"
            ajuda="todos os tipos"
            opcoes={TIPOS_PRODUTO.map((t) => ({ valor: t.valor, nome: t.nome }))}
            escolhidos={escTipos}
            aoTrocar={setEscTipos}
          />
        </div>
      </Cartao>

      <Cartao titulo="Como chamar, e como contar">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <Campo
            rotulo="Nome da contagem"
            dica="opcional — sem nome, a lista mostra o recorte"
            className="sm:flex-1"
          >
            <input
              className="campo"
              maxLength={80}
              placeholder="Contagem da câmara fria"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
            />
          </Campo>
          <label className="flex items-start gap-2 sm:max-w-[340px] sm:pt-6">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-erva"
              checked={cega}
              onChange={(e) => setCega(e.target.checked)}
            />
            <span className="text-[14px] leading-snug">
              contagem cega
              <span className="block text-[12.5px] text-suave">
                esconde o saldo do sistema até a contagem fechar. Ver o esperado transforma a
                contagem em conferência.
              </span>
            </span>
          </label>
        </div>
      </Cartao>

      {/* 🔑 **Quem conta é escala do dia, não papel.** A permissão diz que a
          pessoa sabe contar; esta lista diz quem foi escalado para ESTA
          contagem. Sem isso, restringir a contagem de hoje exigiria mexer nos
          papéis — e desfazer amanhã. */}
      {equipe.length > 0 && (
        <Cartao
          titulo="Quem vai contar"
          descricao={
            contadores.length
              ? `${contadores.length} pessoa(s) escalada(s) — só elas conseguem digitar nesta contagem.`
              : "Ninguém escolhido: qualquer pessoa com permissão de contar pode preencher."
          }
        >
          <FiltroMultiplo
            titulo="Pessoas"
            ajuda="Deixe vazio para liberar a todos que podem contar."
            opcoes={equipe.map((u) => ({ valor: u.id, nome: u.nome }))}
            escolhidos={contadores}
            aoTrocar={setContadores}
          />
        </Cartao>
      )}

      <Cartao
        titulo="O que vai entrar"
        descricao={
          nenhumFiltro
            ? "Sem filtro nenhum: tudo o que tem saldo, em todos os locais."
            : undefined
        }
      >
        {carregandoPrevia && !previa ? (
          <Carregando />
        ) : !previa ? (
          <Vazio>Não deu para calcular a prévia.</Vazio>
        ) : previa.total === 0 ? (
          <Aviso tipo="info">
            Nenhum produto neste recorte. Só entra o que tem saldo ou já se moveu nos locais
            escolhidos — confira os filtros.
          </Aviso>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
              <p className="mono text-[26px] font-bold">{previa.total}</p>
              <p className="text-suave">
                linha(s) para contar · {previa.produtos} produto(s) ·{" "}
                {previa.locais.length} local(is)
              </p>
            </div>

            {/* ⚠️ O mesmo produto em dois locais são DUAS linhas: prateleiras
                diferentes, contagens diferentes, ajustes diferentes. Dizer isso
                aqui evita a surpresa de ver o café repetido na contagem. */}
            {previa.produtos < previa.total && (
              <p className="text-[13.5px] text-suave">
                Há produto com saldo em mais de um local — cada prateleira é uma linha, contada
                separadamente.
              </p>
            )}

            <ul className="flex flex-wrap gap-1.5">
              {previa.locais.map((l) => (
                <li key={l.nome}>
                  <Etiqueta>
                    {l.nome} · {l.itens}
                  </Etiqueta>
                </li>
              ))}
            </ul>

            <div>
              <p className="rotulo">Começa por</p>
              <p className="mt-1 text-[13.5px] leading-relaxed text-suave">
                {previa.amostra.map((a) => a.produto).join(" · ")}
                {previa.total > previa.amostra.length && " …"}
              </p>
            </div>

            {previa.ja_em_contagem_total > 0 && (
              <Aviso tipo="erro">
                {previa.ja_em_contagem_total} item(ns) já estão numa contagem aberta —{" "}
                {previa.ja_em_contagem
                  .slice(0, 3)
                  .map((c) => `${c.produto} em ${c.local} (#${c.inventario})`)
                  .join("; ")}
                . Feche ou cancele a outra contagem, ou estreite o filtro: o mesmo produto no
                mesmo local em duas contagens faria a segunda desfazer o ajuste da primeira.
              </Aviso>
            )}
          </div>
        )}
      </Cartao>

      <div className="flex flex-wrap gap-2">
        <button
          className="btn btn-primario"
          onClick={abrir}
          disabled={
            ocupado || !previa || previa.total === 0 || previa.ja_em_contagem_total > 0
          }
        >
          {ocupado ? "Abrindo…" : `Abrir contagem${previa?.total ? ` (${previa.total})` : ""}`}
        </button>
        <Link href="/inventario" className="btn btn-secundario">
          Cancelar
        </Link>
      </div>
    </div>
  );
}
