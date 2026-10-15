"use client";

/**
 * O catálogo NOVO, em dois passos: que tipo, e que nome.
 *
 * 🔑 **Reforma de 15/10/2026.** A janela antiga abria com "Origem: PDF" já
 * escolhido — o caso comum hoje é o cardápio montado — e perguntava situação,
 * período e observação antes de existir qualquer coisa para publicar. Depois de
 * salvar, a pessoa voltava à lista e tinha de achar o catálogo para começar.
 * Agora a primeira pergunta é a que decide o resto do trabalho (o TIPO); depois
 * só o nome; ele nasce RASCUNHO e abre direto no editor. Período, lojas e o
 * resto ficam na aba Publicação, quando houver o que publicar.
 * ⚠️ As origens são as do SERVIDOR (`/catalogos/opcoes`); daqui é só o texto.
 */

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import { useSessao } from "@/lib/sessao";
import * as cat from "@/lib/catalogos";

export default function NovoCatalogo({ origens, aoFechar }: { origens: string[]; aoFechar: () => void }) {
  const aviso = useAviso();
  const router = useRouter();
  const { unidade } = useSessao();
  // 🔑 O montado com produtos vem PRIMEIRO: é o caso de hoje.
  const ordem = [...origens].sort((a, b) =>
    Number(b === cat.ORIGEM_PRODUTOS) - Number(a === cat.ORIGEM_PRODUTOS));
  const [origem, setOrigem] = useState<string | null>(null);
  const [nome, setNome] = useState("");
  const [criando, setCriando] = useState(false);

  async function criar(e: FormEvent) {
    e.preventDefault();
    if (!origem) return;
    setCriando(true);
    try {
      // ⚠️ Nasce RASCUNHO: catálogo que nasce ativo é publicado antes de alguém
      // conferir o que tem dentro. E visível na loja em que se está.
      const r = await cat.criar({ nome: nome.trim(), origem, situacao: "RASCUNHO", lojas: unidade ? [unidade] : [] });
      aviso.sucesso(`Catálogo “${r.nome}” criado.`);
      router.push(`/catalogos/${r.id}`);
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível criar");
      setCriando(false);
    }
  }

  return (
    <Modal
      titulo="Novo catálogo"
      descricao={origem ? "Só o nome por enquanto — ele nasce como rascunho." : "Primeiro: como ele vai ser feito?"}
      aoFechar={aoFechar}
      largura="620px"
      rodape={origem ? (
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-secundario" onClick={() => setOrigem(null)}>← Voltar</button>
          <button type="submit" form="form-novo-catalogo" className="btn btn-primario" aria-busy={criando}
                  disabled={criando || nome.trim().length < 2}>
            {criando ? "Criando…" : "Criar e abrir"}
          </button>
        </div>
      ) : undefined}
    >
      {!origem ? (
        <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="tipo do catálogo">
          {ordem.map((o) => {
            const ap = cat.APRESENTA_ORIGEM[o];
            return (
              <button key={o} type="button" role="radio" aria-checked={false} data-origem={o}
                      onClick={() => setOrigem(o)}
                      className="flex flex-col gap-2 rounded-xl border border-linha bg-superficie p-4 text-left hover:border-erva hover:bg-erva-claro">
                <span className="text-[15.5px] font-bold">{ap?.titulo ?? o}</span>
                {ap && <span className="text-[13.5px] text-suave">{ap.explica}</span>}
              </button>
            );
          })}
        </div>
      ) : (
        <form id="form-novo-catalogo" onSubmit={criar} className="flex flex-col gap-4">
          <p className="text-[13.5px] text-suave">
            Tipo: <b className="text-tinta">{cat.APRESENTA_ORIGEM[origem]?.titulo ?? origem}</b>
          </p>
          <Campo rotulo="Nome no site do cliente" dica="É o que o cliente lê. Dá para mudar depois.">
            <input className="campo" id="catalogo-nome" required minLength={2} maxLength={120} autoFocus
                   placeholder="Cardápio de verão" value={nome} onChange={(e) => setNome(e.target.value)} />
          </Campo>
        </form>
      )}
    </Modal>
  );
}
