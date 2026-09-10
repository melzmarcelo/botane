"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useSessao } from "@/lib/sessao";
import Omie from "./omie";
import PdvLegal from "./pdv-legal";
import EmailSmtp from "./email-smtp";
import Duplicados from "./duplicados";

/**
 * O que o Botané troca com o mundo lá fora, uma integração por aba.
 *
 * 🔑 **Pedido do dono (09/09/2026):** *"na tela de integração, vamos organizar
 * melhor: cria uma aba e coloca as coisas do Omie, outra aba para o PDV Legal,
 * outra para o e-mail e demais"*. Eram dez cartões empilhados num arquivo de 751
 * linhas, e quem vinha configurar o e-mail rolava a tela inteira passando por
 * credencial, notas, catálogo, custo inicial e conferência de estoque.
 *
 * ⚠️ **A aba vive na URL** (`?aba=pdv`), como em Tabelas de apoio: é o que
 * permite o menu apontar direto, o voltar do navegador funcionar e a tela virar
 * um link que se manda para alguém. Sem inventar um segundo jeito de fazer aba.
 *
 * ⚠️ **Aba que a pessoa não pode ver não existe**, e a primeira aberta é a
 * primeira que ela PODE — senão alguém cai numa aba vazia sem entender por quê.
 */

type Aba = "omie" | "pdv" | "email" | "outros";

const ABAS: { id: Aba; nome: string; chaves: string[]; explica: string }[] = [
  {
    id: "omie",
    nome: "Omie",
    chaves: ["integracao.omie", "admin.integracoes"],
    explica:
      "As notas de compra, o catálogo de produtos e os fornecedores. É de onde vem o custo do que entra.",
  },
  {
    id: "pdv",
    nome: "PDV Legal",
    chaves: ["integracao.pdv", "admin.integracoes"],
    explica:
      "As vendas do caixa e o cardápio. É de onde vem a receita — e, com o envio ligado, para onde vão os cadastros daqui.",
  },
  {
    id: "email",
    nome: "E-mail",
    chaves: ["admin.integracoes"],
    explica:
      "O servidor que envia a recuperação de senha e os avisos. Sem ele, o link de recuperação fica guardado em disco.",
  },
  {
    id: "outros",
    nome: "Outros",
    chaves: ["cadastros.produtos"],
    explica:
      "O que nasce das integrações mas não é de nenhuma delas.",
  },
];

export default function PaginaIntegracoes() {
  const { pode } = useSessao();
  const router = useRouter();
  const busca = useSearchParams();

  const minhas = ABAS.filter((a) => a.chaves.some((c) => pode(c)));
  const pedida = busca.get("aba") as Aba | null;
  const primeira = minhas[0]?.id ?? "omie";
  const aba: Aba = minhas.some((a) => a.id === pedida) ? (pedida as Aba) : primeira;
  const atual = minhas.find((a) => a.id === aba) ?? minhas[0];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Administração</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Integrações</h1>
        <p className="mt-1 max-w-[66ch] text-suave">
          O que o Botané troca com o mundo lá fora. Nada aqui é pré-requisito — o sistema opera
          inteiro sem nenhuma delas.
        </p>
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-linha">
        {minhas.map((a) => (
          <button
            key={a.id}
            onClick={() => router.replace(`/integracoes?aba=${a.id}`)}
            className={`-mb-px border-b-2 px-3 py-2 text-[14.5px] ${
              aba === a.id
                ? "border-erva font-semibold text-erva"
                : "border-transparent text-suave hover:text-tinta"
            }`}
          >
            {a.nome}
          </button>
        ))}
      </nav>

      {/* A frase do que a aba faz vem ANTES do conteúdo: "Omie" e "PDV Legal"
          são nomes de fornecedor, não dizem o que cada um traz para cá. */}
      {atual && <p className="-mt-3 max-w-[70ch] text-[14px] text-suave">{atual.explica}</p>}

      {aba === "omie" && <Omie />}
      {aba === "pdv" && <PdvLegal />}
      {aba === "email" && <EmailSmtp />}
      {aba === "outros" && <Duplicados />}
    </div>
  );
}
