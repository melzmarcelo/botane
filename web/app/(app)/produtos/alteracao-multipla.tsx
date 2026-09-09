"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Etiqueta, Modal } from "@/components/ui";
import { Categoria, Setor, TIPOS_PRODUTO } from "@/lib/cadastros";

/**
 * Mudar tipo, categoria, setor ou a ativação em VÁRIOS produtos de uma vez.
 *
 * 🔑 **O pedido do dono (09/09/2026).** O catálogo tem 3.183 produtos e 2.229
 * vieram do Omie sem categoria nem setor. Arrumar um a um são quatro passos por
 * produto — abrir, escolher, salvar, voltar — e ninguém faz duas mil vezes: o
 * trabalho não é feito, e o CMV por grupo responde "sem categoria" no maior
 * pedaço da lista.
 *
 * ⚠️ **A PRÉVIA vem antes, sempre.** É a mesma regra da fusão e da colheita de
 * EAN, e aqui vale mais: quem marcou 300 linhas não confere uma a uma depois. A
 * prévia diz quantos mudam de verdade, quantos já estavam assim e quais o
 * servidor recusa — e só então aparece o botão que grava.
 */

type Linha = {
  id: number;
  codigo: string;
  nome: string;
  tipo: string;
  categoria: string | null;
  setor: string | null;
  ativo: boolean;
  motivo?: string;
};

type Resposta = {
  mudam: Linha[];
  iguais: Linha[];
  recusados: Linha[];
  aplicado: boolean;
  message: string;
};

export default function AlteracaoMultipla({
  ids,
  categorias,
  setores,
  aoFechar,
  aoAplicar,
}: {
  ids: number[];
  categorias: Categoria[];
  setores: Setor[];
  aoFechar: () => void;
  /** Recarrega a lista de trás — os valores mudaram. */
  aoAplicar: () => void;
}) {
  const aviso = useAviso();
  const [tipo, setTipo] = useState("");
  const [idCategoria, setIdCategoria] = useState("");
  const [idSetor, setIdSetor] = useState("");
  // ⚠️ Três estados, não dois: "não mexer" é diferente de "ativar" e de
  // "inativar". Uma caixinha de dois estados obrigaria a escolher um dos dois
  // sempre, e quem só quer trocar a categoria mexeria na ativação sem querer.
  const [ativacao, setAtivacao] = useState<"" | "sim" | "nao">("");
  const [previa, setPrevia] = useState<Resposta | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  const mudancas = {
    tipo: tipo || null,
    id_categoria: idCategoria ? Number(idCategoria) : null,
    id_setor: idSetor ? Number(idSetor) : null,
    ativo: ativacao === "" ? null : ativacao === "sim",
  };
  const escolheuAlgo = Object.values(mudancas).some((v) => v !== null);

  // A prévia se refaz a cada escolha: o número que decide o clique não pode
  // estar velho quando ele acontece.
  useEffect(() => {
    if (!escolheuAlgo) {
      setPrevia(null);
      return;
    }
    let valeu = true;
    setErro("");
    api
      .post<Resposta>("/produtos/alteracao-multipla", { ids, ...mudancas })
      .then((r) => valeu && setPrevia(r))
      .catch((e) => valeu && setErro(e instanceof Error ? e.message : "Falha na prévia"));
    return () => {
      // ⚠️ A resposta de uma prévia antiga não pode sobrescrever a nova: sem
      // isto, mudar de categoria rápido deixaria na tela o número da anterior.
      valeu = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids, tipo, idCategoria, idSetor, ativacao]);

  async function aplicar() {
    setOcupado(true);
    try {
      const r = await api.post<Resposta>("/produtos/alteracao-multipla", {
        ids,
        ...mudancas,
        simular: false,
      });
      aviso.sucesso(r.message);
      aoAplicar();
      aoFechar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível aplicar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      titulo={`Alterar ${ids.length} produto(s)`}
      descricao="Só os campos preenchidos mudam. O resto fica como está."
      aoFechar={aoFechar}
      rodape={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-[13px] text-suave">
            {previa ? previa.message : "Escolha o que mudar."}
          </span>
          <div className="flex gap-2">
            <button type="button" className="btn btn-secundario" onClick={aoFechar}>
              Cancelar
            </button>
            <button
              type="button"
              className="btn btn-primario"
              disabled={ocupado || !previa || !previa.mudam.length}
              onClick={() => void aplicar()}
            >
              {ocupado
                ? "Aplicando…"
                : `Aplicar em ${previa?.mudam.length ?? 0}`}
            </button>
          </div>
        </div>
      }
    >
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="grid gap-4 sm:grid-cols-2">
        <Campo rotulo="Tipo" dica="em branco não mexe">
          <select className="campo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">— não mexer —</option>
            {TIPOS_PRODUTO.map((t) => (
              <option key={t.valor} value={t.valor}>
                {t.nome}
              </option>
            ))}
          </select>
        </Campo>
        <Campo rotulo="Categoria" dica="em branco não mexe">
          <select
            className="campo"
            value={idCategoria}
            onChange={(e) => setIdCategoria(e.target.value)}
          >
            <option value="">— não mexer —</option>
            {categorias.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
        </Campo>
        <Campo rotulo="Setor" dica="em branco não mexe">
          <select className="campo" value={idSetor} onChange={(e) => setIdSetor(e.target.value)}>
            <option value="">— não mexer —</option>
            {setores.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nome}
              </option>
            ))}
          </select>
        </Campo>
        <Campo rotulo="Ativação" dica="em branco não mexe">
          <select
            className="campo"
            value={ativacao}
            onChange={(e) => setAtivacao(e.target.value as "" | "sim" | "nao")}
          >
            <option value="">— não mexer —</option>
            <option value="nao">Inativar</option>
            <option value="sim">Ativar</option>
          </select>
        </Campo>
      </div>

      {previa && (
        <div className="mt-5 flex flex-col gap-4">
          {/* 🔑 **"Já estava assim" fica à vista, e não some.** Quem marca 300
              linhas para pôr numa categoria quer saber quantas realmente
              estavam sem ela — "300 alterados" quando 280 já estavam certos não
              informa nada. */}
          {!!previa.iguais.length && (
            <Aviso tipo="info">
              <b>{previa.iguais.length}</b> já está(ão) assim e não conta(m) como
              alteração.
            </Aviso>
          )}

          {/* ⚠️ **A recusa é NOMEADA, e não impede o resto.** O lote é útil
              justamente por não exigir que tudo esteja perfeito: um prato de
              produção própria não vira INSUMO, e os outros 299 mudam. */}
          {!!previa.recusados.length && (
            <div>
              <p className="mb-2 text-[13px] font-semibold text-erro">
                {previa.recusados.length} não dá para alterar:
              </p>
              <ul className="flex flex-col gap-1">
                {previa.recusados.map((l) => (
                  <li key={l.id} className="text-[13px] text-suave">
                    <b>{l.nome}</b> — {l.motivo}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!!previa.mudam.length && (
            <div>
              <p className="mb-2 text-[13px] text-suave">
                {previa.mudam.length} produto(s) mudam:
              </p>
              <div className="max-h-[34vh] overflow-y-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Produto</th>
                      <th>Tipo</th>
                      <th>Categoria</th>
                      <th>Setor</th>
                      <th>Ativo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previa.mudam.map((l) => (
                      <tr key={l.id}>
                        <td>
                          {l.nome}
                          <span className="block text-[12.5px] text-suave">{l.codigo}</span>
                        </td>
                        <td>{l.tipo}</td>
                        <td>{l.categoria ?? "—"}</td>
                        <td>{l.setor ?? "—"}</td>
                        <td>
                          {l.ativo ? <Etiqueta cor="erva">sim</Etiqueta> : <Etiqueta>não</Etiqueta>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[13px] text-suave">
                Os valores acima são os de <b>agora</b>, antes da alteração.
              </p>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
