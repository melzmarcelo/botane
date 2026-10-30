"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Modal, Vazio } from "@/components/ui";
import { plural } from "@/lib/numeros";
import {
  Categoria,
  Setor,
  TIPOS_PRODUTO,
  TipoDescricao,
  gravarDescricaoDeTipo,
  listarDescricoesDeTipo,
} from "@/lib/cadastros";

type Lista = "tipos" | "categorias" | "setores";

/**
 * Descrições de tipo, categoria e setor (pedido do dono, 25/10/2026).
 *
 * 🔑 **É o texto da dica do cadastro do produto**: passar o mouse no Tipo mostra o uso
 * operacional, na Categoria os exemplos/abrangência e no Setor o uso previsto — as
 * três colunas do documento da casa, que a migração 133 já carregou.
 * ⚠️ **Uma janela para as três listas, e não um campo a mais em cada aba**: o tipo é
 * fixo do sistema e não tem aba aqui; e escrever as explicações é um trabalho que se
 * faz de uma vez, lendo uma ao lado da outra.
 * ⚠️ Só o que MUDOU é gravado — trinta e seis categorias com um PUT cada a cada
 * "Salvar" seriam trinta e seis linhas de auditoria dizendo que nada mudou.
 */
export default function Descricoes({
  categorias,
  setores,
  pode,
  aoFechar,
  aoSalvar,
}: {
  categorias: Categoria[];
  setores: Setor[];
  pode: Record<Lista, boolean>;
  aoFechar: () => void;
  aoSalvar: () => void;
}) {
  const aviso = useAviso();
  const [lista, setLista] = useState<Lista>("tipos");
  const [tipos, setTipos] = useState<TipoDescricao[] | null>(null);
  const [erro, setErro] = useState("");
  // O que foi digitado, por chave "lista:id". Ausente = não mexeu.
  const [editado, setEditado] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    listarDescricoesDeTipo().then(setTipos).catch((e) => {
      setTipos([]);
      setErro(e.message);
    });
  }, []);

  const linhas = useMemo(() => {
    if (lista === "tipos") {
      return TIPOS_PRODUTO.map((t) => ({
        chave: `tipos:${t.valor}`,
        nome: t.nome,
        original: tipos?.find((d) => d.tipo === t.valor)?.descricao ?? "",
      }));
    }
    if (lista === "categorias") {
      return categorias.filter((c) => c.ativo).map((c) => ({
        chave: `categorias:${c.id}`, nome: c.caminho, original: c.descricao ?? "",
      }));
    }
    return setores.filter((s) => s.ativo).map((s) => ({
      chave: `setores:${s.id}`, nome: s.nome, original: s.descricao ?? "",
    }));
  }, [lista, tipos, categorias, setores]);

  const todasAsOriginais = useMemo(() => {
    const m: Record<string, string> = {};
    for (const t of TIPOS_PRODUTO) {
      m[`tipos:${t.valor}`] = tipos?.find((d) => d.tipo === t.valor)?.descricao ?? "";
    }
    for (const c of categorias) m[`categorias:${c.id}`] = c.descricao ?? "";
    for (const s of setores) m[`setores:${s.id}`] = s.descricao ?? "";
    return m;
  }, [tipos, categorias, setores]);

  const mudancas = Object.entries(editado).filter(
    ([chave, texto]) => texto.trim() !== (todasAsOriginais[chave] ?? "").trim());

  async function salvar() {
    setSalvando(true);
    setErro("");
    let feitas = 0;
    try {
      for (const [chave, texto] of mudancas) {
        const [qual, id] = chave.split(":");
        if (qual === "tipos") await gravarDescricaoDeTipo(id, texto);
        else await api.put(`/${qual}/${id}`, { descricao: texto });
        feitas += 1;
      }
      aviso.sucesso(`${plural(feitas, "descrição gravada", "descrições gravadas")}`);
      aoSalvar();
      aoFechar();
    } catch (e) {
      // ⚠️ O que já foi gravado fica: diz quantas foram, para ninguém refazer tudo.
      setErro(`${(e as Error).message}${feitas ? ` — ${feitas} já tinham sido gravadas` : ""}`);
      aoSalvar();
    } finally {
      setSalvando(false);
    }
  }

  const titulos: Record<Lista, { nome: string; coluna: string }> = {
    tipos: { nome: "Tipos", coluna: "Uso operacional" },
    categorias: { nome: "Categorias", coluna: "Exemplos / abrangência" },
    setores: { nome: "Setores", coluna: "Uso previsto" },
  };
  const podeEsta = pode[lista];

  return (
    <Modal
      titulo="Descrições"
      descricao="O texto que aparece ao passar o mouse no Tipo, na Categoria e no Setor do cadastro do produto."
      aoFechar={aoFechar}
      largura="820px"
      rodape={
        <div className="flex flex-wrap items-center justify-end gap-3">
          <span className="mr-auto text-[13px] text-suave">
            {mudancas.length ? `${plural(mudancas.length, "alteração", "alterações")} por gravar` : "nada alterado"}
          </span>
          <button type="button" className="btn btn-secundario" onClick={aoFechar}>
            Fechar
          </button>
          <button
            id="descricoes-salvar"
            type="button"
            className="btn btn-primario"
            disabled={!mudancas.length || salvando}
            onClick={() => void salvar()}
          >
            {salvando ? "Gravando…" : "Salvar"}
          </button>
        </div>
      }
    >
      <nav className="mb-4 flex flex-wrap gap-1 border-b border-linha">
        {(Object.keys(titulos) as Lista[]).map((l) => (
          <button
            key={l}
            type="button"
            data-lista={l}
            onClick={() => setLista(l)}
            className={`-mb-px border-b-2 px-3 py-2 text-[14px] ${
              lista === l
                ? "border-erva font-semibold text-erva"
                : "border-transparent text-suave hover:text-tinta"
            }`}
          >
            {titulos[l].nome}
          </button>
        ))}
      </nav>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!podeEsta && (
        <p className="mb-3 text-[13px] text-suave">Só leitura: sua permissão não altera esta lista.</p>
      )}

      {lista === "tipos" && tipos === null ? (
        <Carregando />
      ) : linhas.length === 0 ? (
        <Vazio>Nada cadastrado nesta lista.</Vazio>
      ) : (
        <div className="flex flex-col gap-3" id="descricoes-lista">
          <p className="rotulo">{titulos[lista].coluna}</p>
          {linhas.map((l) => (
            <label key={l.chave} className="grid gap-1 sm:grid-cols-[220px_1fr] sm:gap-3">
              <span className="pt-2 text-[14px] font-semibold">{l.nome}</span>
              <textarea
                className="campo min-h-[44px] text-[14px]"
                rows={2}
                maxLength={500}
                disabled={!podeEsta}
                data-chave={l.chave}
                value={editado[l.chave] ?? l.original}
                onChange={(e) => setEditado({ ...editado, [l.chave]: e.target.value })}
              />
            </label>
          ))}
        </div>
      )}
    </Modal>
  );
}
