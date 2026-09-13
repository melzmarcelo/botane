"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, FonteBusca, ItemBusca } from "@/lib/busca-cadastro";
import { Aviso, Confirmacao } from "@/components/ui";

/**
 * Copiar esta receita para outro produto.
 *
 * 🔑 **Pedido do dono (12/09/2026):** *"tenho Bolo de Morango e Bolo de Banana, a
 * base da receita é a mesma, então gostaria de duplicar e ajustar, retirando o
 * que não vai e adicionando o que precisa"*. Sem isto a segunda receita era
 * redigitada item por item — e é aí que uma entra com 200 G de farinha e a outra
 * com 250, sem ninguém ter decidido nada.
 *
 * ⚠️ **A janela diz o que vai acontecer ANTES de acontecer.** Duplicar cria uma
 * ficha nova num produto que pode já ter uma; quem confirma precisa saber que a
 * cópia nasce em rascunho e que a ficha atual do destino continua valendo. Sem
 * isso a pessoa descobre o efeito pela lista de fichas, depois.
 *
 * ⚠️ **A busca lista só PRODUZIDOS** (decisão do dono, 12/09/2026). A primeira
 * versão não filtrava, para não repetir o caso em que um recorte fez "o prato que
 * se queria virar invisível" — o tipo `KIT` também aceita ficha, e filtrar o
 * esconde. Medido na base ao decidir: **zero kits** cadastrados e as 46 fichas
 * todas em produzidos, então o que o filtro esconde hoje é nada, e o que ele tira
 * da frente são 600 insumos, revendas e utensílios que nunca serão destino de uma
 * receita. É também o mesmo recorte que a tela de CRIAR a ficha já usa
 * (`fonteProduzidos`), o que faz as duas buscas responderem igual.
 * ⚠️ **No dia em que existir kit com ficha**, o filtro é uma string: tirar o
 * `tipo=PRODUZIDO` devolve o comportamento anterior. E a guarda abaixo continua
 * valendo, porque o servidor aceita os dois tipos.
 *
 * ⚠️ **Produto EXISTENTE.** Cadastrar o produto aqui pediria tipo, unidade,
 * categoria e setor — um cadastro inteiro dentro de uma janela de cópia. Quem
 * duplica já tem o bolo de banana cadastrado; quem não tem, cadastra em Produtos.
 */
export default function DuplicarFicha({
  idFicha,
  produtoAtual,
  fichasDoSistema,
}: {
  idFicha: number;
  produtoAtual: string;
  /** Para avisar que o destino já tem ficha — a lista já está carregada na tela. */
  fichasDoSistema: { id_produto: number; versao: number; status: string }[];
}) {
  const router = useRouter();
  const aviso = useAviso();
  const [aberta, setAberta] = useState(false);
  const [destino, setDestino] = useState<ItemBusca | null>(null);
  const [erro, setErro] = useState("");
  const [copiando, setCopiando] = useState(false);

  const fonte = useMemo<FonteBusca>(
    () => ({
      // ⚠️ O recorte vai como query do SERVIDOR (`extra`), nunca como peneira no
      // navegador: filtrar depois cortaria a página trazida e a busca diria
      // "nenhum resultado" para um prato que existe na página seguinte.
      ...fonteProdutos("tipo=PRODUZIDO"),
      titulo: "Buscar o produto de destino",
      singular: "produto produzido",
    }),
    [],
  );

  const tipoDoDestino = String(destino?.bruto?.tipo ?? "");
  const serve = !destino || ["PRODUZIDO", "KIT"].includes(tipoDoDestino);

  /** O que o destino escolhido já tem, para a janela poder dizer. */
  const jaTem = useMemo(() => {
    if (!destino) return null;
    const suas = fichasDoSistema.filter((f) => f.id_produto === Number(destino.id));
    if (!suas.length) return null;
    return {
      quantas: suas.length,
      maiorVersao: Math.max(...suas.map((f) => f.versao)),
      temHomologada: suas.some((f) => f.status === "HOMOLOGADA"),
    };
  }, [destino, fichasDoSistema]);

  async function duplicar() {
    if (!destino) {
      setErro("Escolha para qual produto a receita vai.");
      return;
    }
    if (!serve) {
      setErro("Ficha técnica é de produto produzido ou kit. Ajuste o tipo do produto primeiro.");
      return;
    }
    setCopiando(true);
    setErro("");
    try {
      const r = await api.post<{ id: number; message: string }>(
        `/fichas/${idFicha}/duplicar`,
        { id_produto: Number(destino.id) },
      );
      aviso.sucesso(r.message);
      // Vai para a CÓPIA: o passo seguinte é sempre ajustar a receita nova.
      router.push(`/fichas/${r.id}`);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível duplicar");
      setCopiando(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="btn btn-secundario"
        onClick={() => {
          setDestino(null);
          setErro("");
          setAberta(true);
        }}
      >
        Duplicar receita
      </button>

      {aberta && (
        <Confirmacao
          titulo="Copiar esta receita para outro produto"
          rotuloConfirmar="Copiar receita"
          ocupado={copiando}
          aoConfirmar={duplicar}
          aoCancelar={() => setAberta(false)}
        >
          <p>
            Vai junto tudo o que está nesta ficha: os ingredientes com as quantidades e os
            fatores, o rendimento, as porções, o modo de preparo, os alérgenos e a foto. Depois
            você ajusta o que difere — é para isso que a cópia nasce em <b>rascunho</b>.
          </p>
          <div className="mt-3">
            <p className="rotulo mb-1.5">Para qual produto</p>
            <BuscaCadastro
              fonte={fonte}
              selecionado={destino ? { id: destino.id, rotulo: rotuloDe(destino) } : null}
              aoEscolher={(item) => {
                setDestino(item);
                setErro("");
              }}
            />
            <p className="mt-1.5 text-[13px] text-suave">
              A lista traz os produtos <b>produzidos</b>, que são os que têm receita. Copiando
              de {produtoAtual}.
            </p>
          </div>
          {destino && !serve && (
            <div className="mt-3">
              <Aviso tipo="erro">
                {rotuloDe(destino)} é do tipo <b>{tipoDoDestino.toLowerCase()}</b>, e ficha
                técnica é de produzido ou kit. Troque o tipo em Produtos, ou escolha outro.
              </Aviso>
            </div>
          )}
          {jaTem && serve && (
            <div className="mt-3">
              <Aviso tipo="info">
                Este produto já tem{" "}
                {jaTem.quantas === 1 ? "uma ficha" : `${jaTem.quantas} fichas`} (a maior é a v
                {jaTem.maiorVersao}). A cópia entra como <b>v{jaTem.maiorVersao + 1}</b> em
                rascunho
                {jaTem.temHomologada
                  ? ", e a homologada continua valendo até você homologar a nova."
                  : "."}
              </Aviso>
            </div>
          )}
          {erro && (
            <div className="mt-3">
              <Aviso tipo="erro">{erro}</Aviso>
            </div>
          )}
        </Confirmacao>
      )}
    </>
  );
}
