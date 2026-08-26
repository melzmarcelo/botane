"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { TIPOS_PRODUTO, nomeTipo } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Confirmacao, Etiqueta, Vazio } from "@/components/ui";

/**
 * Os grupos com que a casa separa o CMV por tipo de produto.
 *
 * Fica em arquivo próprio porque a tela de Tabelas de apoio já é longa, e este
 * bloco tem estado próprio (o formulário de edição abre em linha).
 *
 * ⚠️ **Um tipo só pode estar num grupo.** Quem garante é o banco, mas a tela
 * mostra isso ANTES do clique: o tipo já usado aparece desabilitado, dizendo em
 * qual grupo está. Deixar escolher para depois recusar com 409 é fazer a pessoa
 * descobrir a regra errando.
 */

type Grupo = {
  id: number;
  nome: string;
  tipos: string[];
  ordem: number;
  ativo: boolean;
  considerar_no_cmv: boolean;
};

export default function GruposCmv() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeEditar = pode("cmv.grupos");

  const [grupos, setGrupos] = useState<Grupo[] | null>(null);
  const [erro, setErro] = useState("");
  const [novoNome, setNovoNome] = useState("");
  const [novosTipos, setNovosTipos] = useState<string[]>([]);
  const [novoNoCmv, setNovoNoCmv] = useState(true);
  const [editando, setEditando] = useState<Grupo | null>(null);
  const [excluindo, setExcluindo] = useState<Grupo | null>(null);

  const carregar = useCallback(async () => {
    try {
      setGrupos(await api.get<Grupo[]>("/cmv/grupos"));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function acao(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      aviso.sucesso(ok);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    }
  }

  /** Em que grupo este tipo já está — vazio se estiver livre. */
  const donoDoTipo = (tipo: string, ignorar?: number) =>
    grupos?.find((g) => g.id !== ignorar && g.tipos.includes(tipo))?.nome ?? "";

  const alternar = (lista: string[], tipo: string) =>
    lista.includes(tipo) ? lista.filter((t) => t !== tipo) : [...lista, tipo];

  /**
   * A escolha que muda o NÚMERO, não só a apresentação.
   *
   * ⚠️ Desmarcado, os produtos destes tipos saem do CMV real — do estoque
   * inicial, das compras e do estoque final. É o que separa comida de
   * detergente no food cost, que é o percentual que vira decisão de cardápio.
   * O dinheiro continua aparecendo no painel, à parte: gasto que some da vista
   * é gasto que ninguém controla.
   */
  const NoCmv = ({
    marcado,
    aoTrocar,
    id,
  }: {
    marcado: boolean;
    aoTrocar: (v: boolean) => void;
    id: string;
  }) => (
    <label className="flex items-start gap-2.5" htmlFor={`cmv-${id}`}>
      <input
        id={`cmv-${id}`}
        type="checkbox"
        className="mt-0.5 h-4 w-4 accent-erva"
        disabled={!podeEditar}
        checked={marcado}
        onChange={(e) => aoTrocar(e.target.checked)}
      />
      <span className="text-[14px] leading-snug">
        considerar no CMV real
        <span className="block text-[12.5px] text-suave">
          {marcado
            ? "o custo destes tipos entra na conta do CMV, como qualquer insumo."
            : "o custo destes tipos FICA DE FORA do CMV e do food cost — continua aparecendo no painel, em linha própria."}
        </span>
      </span>
    </label>
  );

  /** As caixas de tipo, com o já usado travado e explicado. */
  const Tipos = ({
    escolhidos,
    aoTrocar,
    ignorar,
  }: {
    escolhidos: string[];
    aoTrocar: (tipos: string[]) => void;
    ignorar?: number;
  }) => (
    <ul className="grid gap-px overflow-hidden rounded border border-linha bg-linha sm:grid-cols-2">
      {TIPOS_PRODUTO.map((t) => {
        const dono = donoDoTipo(t.valor, ignorar);
        return (
          <li key={t.valor} className="flex items-start gap-2.5 bg-superficie p-3">
            <input
              id={`tipo-${ignorar ?? "novo"}-${t.valor}`}
              type="checkbox"
              className="mt-1 h-4 w-4 accent-erva"
              disabled={!podeEditar || !!dono}
              checked={escolhidos.includes(t.valor)}
              onChange={() => aoTrocar(alternar(escolhidos, t.valor))}
            />
            <label
              htmlFor={`tipo-${ignorar ?? "novo"}-${t.valor}`}
              className={dono ? "opacity-55" : "cursor-pointer"}
            >
              <span className="block text-[14px] font-semibold">{t.nome}</span>
              <span className="mt-0.5 block text-[12.5px] leading-snug text-suave">
                {dono ? `já está em ${dono}` : t.ajuda}
              </span>
            </label>
          </li>
        );
      })}
    </ul>
  );

  if (erro && !grupos) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!grupos) return <Carregando />;

  return (
    <div className="flex flex-col gap-5">
      {podeEditar && (
        <form
          className="flex flex-col gap-3 rounded border border-linha bg-fundo p-4"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void acao(async () => {
              await api.post("/cmv/grupos", {
                nome: novoNome,
                tipos: novosTipos,
                ordem: (grupos.at(-1)?.ordem ?? 0) + 10,
                considerar_no_cmv: novoNoCmv,
              });
              setNovoNome("");
              setNovosTipos([]);
              setNovoNoCmv(true);
            }, "Grupo criado.");
          }}
        >
          <p className="rotulo">Novo grupo</p>
          <Campo rotulo="Nome" dica="é como a linha aparece no painel de CMV">
            <input
              className="campo"
              required
              minLength={2}
              maxLength={60}
              placeholder="Material de limpeza e embalagem"
              value={novoNome}
              onChange={(e) => setNovoNome(e.target.value)}
            />
          </Campo>
          <Campo rotulo="Tipos de produto que entram">
            <Tipos escolhidos={novosTipos} aoTrocar={setNovosTipos} />
          </Campo>
          <NoCmv marcado={novoNoCmv} aoTrocar={setNovoNoCmv} id="novo" />
          <div>
            <button className="btn btn-secundario" type="submit">
              Criar grupo
            </button>
          </div>
        </form>
      )}

      {!grupos.length && <Vazio>Nenhum grupo. O CMV sai inteiro, sem separação.</Vazio>}

      <ul className="flex flex-col gap-3 empty:hidden">
        {grupos.map((g) => (
          <li
            key={g.id}
            className={`rounded border border-linha p-4 ${g.ativo ? "" : "opacity-55"}`}
          >
            {editando?.id === g.id ? (
              <form
                className="flex flex-col gap-3"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  const alvo = editando;
                  void acao(async () => {
                    await api.put(`/cmv/grupos/${alvo.id}`, {
                      nome: alvo.nome,
                      tipos: alvo.tipos,
                      ordem: alvo.ordem,
                      ativo: alvo.ativo,
                      considerar_no_cmv: alvo.considerar_no_cmv,
                    });
                    setEditando(null);
                  }, "Grupo atualizado.");
                }}
              >
                <Campo rotulo="Nome">
                  <input
                    className="campo"
                    required
                    minLength={2}
                    maxLength={60}
                    value={editando.nome}
                    onChange={(e) => setEditando({ ...editando, nome: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Tipos de produto que entram">
                  <Tipos
                    escolhidos={editando.tipos}
                    ignorar={editando.id}
                    aoTrocar={(tipos) => setEditando({ ...editando, tipos })}
                  />
                </Campo>
                <NoCmv
                  marcado={editando.considerar_no_cmv}
                  aoTrocar={(v) => setEditando({ ...editando, considerar_no_cmv: v })}
                  id={String(editando.id)}
                />
                <div className="flex gap-2">
                  <button className="btn btn-primario" type="submit">
                    Salvar
                  </button>
                  <button
                    className="btn btn-secundario"
                    type="button"
                    onClick={() => setEditando(null)}
                  >
                    Cancelar
                  </button>
                </div>
              </form>
            ) : (
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 text-[15px] font-semibold">
                    {g.nome}
                    {!g.considerar_no_cmv && <Etiqueta cor="alerta">fora do CMV real</Etiqueta>}
                  </p>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5">
                    {/* Grupo sem tipo não aparece no CMV — dizer isso aqui evita
                        que alguém procure a linha que não existe. */}
                    {!g.tipos.length ? (
                      <li className="text-[13px] text-suave">
                        nenhum tipo escolhido — não aparece no CMV
                      </li>
                    ) : (
                      g.tipos.map((t) => (
                        <li key={t}>
                          <Etiqueta>{nomeTipo(t)}</Etiqueta>
                        </li>
                      ))
                    )}
                  </ul>
                </div>
                {podeEditar && (
                  <span className="flex shrink-0 gap-3">
                    <button className="rotulo hover:text-erva" onClick={() => setEditando(g)}>
                      editar
                    </button>
                    <button className="rotulo hover:text-erro" onClick={() => setExcluindo(g)}>
                      excluir
                    </button>
                  </span>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>

      {excluindo && (
        <Confirmacao
          titulo="Excluir o grupo"
          rotuloConfirmar="Excluir"
          perigo
          aoCancelar={() => setExcluindo(null)}
          aoConfirmar={() => {
            const alvo = excluindo;
            setExcluindo(null);
            void acao(() => api.delete(`/cmv/grupos/${alvo.id}`), "Grupo excluído.");
          }}
        >
          <p>
            Excluir <b>{excluindo.nome}</b>?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            O CMV deixa de mostrar essa linha e os tipos voltam a ficar livres para outro
            grupo. Nada de histórico se perde: o custo continua dentro do CMV real, só deixa de
            aparecer separado.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
