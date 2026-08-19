"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { Aviso, Cartao } from "@/components/ui";

type Empresa = {
  nome_fantasia: string | null;
  razao_social: string | null;
  cnpj: string | null;
  cidade: string | null;
  uf: string | null;
  contador_nome: string | null;
  logo_url: string | null;
};
type Usuario = { id: number; nome: string; ativo: boolean; papeis: { papel: string }[] };

/** O que o sistema vai passar a fazer, em português de restaurante. */
const CAMINHO = [
  { nome: "Acesso da equipe", detalhe: "Cada pessoa com o seu login e só o que precisa ver", pronto: true },
  { nome: "Produtos e fornecedores", detalhe: "O que se compra, em que unidade e de quem", pronto: true },
  { nome: "Fichas técnicas", detalhe: "A receita de cada prato e quanto ela custa por porção", pronto: false },
  { nome: "Estoque e perdas", detalhe: "Entradas, saídas, contagem e o que se perdeu — com nome", pronto: false },
  { nome: "Notas do Omie", detalhe: "A nota de compra entra sozinha e vira custo", pronto: false },
  { nome: "Painel de CMV", detalhe: "Quanto custou o que você vendeu, e onde está a diferença", pronto: false },
];

function Passo({
  feito,
  titulo,
  detalhe,
  href,
  acao,
}: {
  feito: boolean;
  titulo: string;
  detalhe: string;
  href?: string;
  acao?: string;
}) {
  return (
    <li className="flex items-start gap-3 bg-superficie p-4">
      <span
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold ${
          feito ? "border-erva bg-erva text-white" : "border-linha2 text-suave"
        }`}
        aria-hidden
      >
        {feito ? "✓" : ""}
      </span>
      <div className="min-w-0">
        <p className="text-[15px] font-semibold">{titulo}</p>
        <p className="mt-0.5 text-[13.5px] leading-snug text-suave">{detalhe}</p>
        {href && !feito && (
          <Link href={href} className="rotulo mt-1.5 inline-block text-erva hover:underline">
            {acao ?? "preencher"}
          </Link>
        )}
      </div>
    </li>
  );
}

export default function Inicio() {
  const { eu, pode } = useSessao();
  const [empresa, setEmpresa] = useState<Empresa | null>(null);
  const [equipe, setEquipe] = useState<Usuario[] | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api.get<Empresa>("/empresa").then(setEmpresa).catch((e) => setErro(e.message));
    if (pode("admin.usuarios")) {
      api.get<Usuario[]>("/usuarios").then(setEquipe).catch(() => {});
    }
  }, [pode]);

  const hoje = new Date().toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });
  const nome = eu?.nome.split(" ")[0] ?? "";
  // Enquanto a empresa não chega, some com a linha inteira em vez de mostrar
  // um nome genérico que pisca e troca.
  const casa = empresa ? empresa.nome_fantasia || empresa.razao_social || "sua casa" : null;

  const temIdentificacao = !!empresa?.cnpj;
  const temEndereco = !!empresa?.cidade;
  const temContador = !!empresa?.contador_nome;
  const temEquipe = (equipe?.filter((u) => u.ativo).length ?? 0) > 1;
  const faltando = [temIdentificacao, temEndereco, temContador, temEquipe].filter((x) => !x).length;
  const admin = pode("admin.empresa") || pode("admin.usuarios");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">{hoje}</p>
        <h1 className="mt-1 text-[26px] font-bold leading-tight tracking-tight sm:text-[32px]">
          Bom trabalho, {nome}
        </h1>
        <p className="mt-1 min-h-[24px] text-[15px] text-suave sm:text-[16px]">
          {casa && `${casa} · `}
          {casa === null ? "" : `você entrou como ${eu?.papeis.join(", ").toLowerCase() || "usuário"}`}
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {admin && (
        <Cartao
          titulo={faltando ? "Falta pouco para deixar tudo pronto" : "Sua casa está configurada"}
          descricao={
            faltando
              ? `${faltando} ${faltando === 1 ? "item pendente" : "itens pendentes"} — leva poucos minutos.`
              : "Os dados básicos estão no lugar. O próximo passo é cadastrar o que você compra."
          }
        >
          <ol className="grid gap-px overflow-hidden rounded border border-linha bg-linha sm:grid-cols-2">
            <Passo
              feito={temIdentificacao}
              titulo="Dados da empresa"
              detalhe="CNPJ, inscrição e regime — usados nos relatórios e nas notas."
              href="/empresa"
            />
            <Passo
              feito={temEndereco}
              titulo="Endereço e contato"
              detalhe="Onde a casa fica e por onde falam com você."
              href="/empresa"
            />
            <Passo
              feito={temContador}
              titulo="Contabilidade"
              detalhe="O escritório que vai receber os números do mês."
              href="/empresa"
            />
            <Passo
              feito={temEquipe}
              titulo="Equipe com acesso"
              detalhe={
                equipe
                  ? `${equipe.filter((u) => u.ativo).length} pessoa(s) com login hoje.`
                  : "Cozinha, salão e quem confere as entregas."
              }
              href="/usuarios"
              acao="dar acesso a alguém"
            />
          </ol>
        </Cartao>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Cartao
          titulo="O caminho até o CMV"
          descricao="Cada peça depende da anterior — é por isso que a ordem é essa."
        >
          <ol className="flex flex-col">
            {CAMINHO.map((c, i) => (
              <li
                key={c.nome}
                className={`flex items-start gap-3 py-3 ${
                  i < CAMINHO.length - 1 ? "border-b border-linha" : ""
                }`}
              >
                <span
                  className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                    c.pronto ? "bg-erva" : "border border-linha2 bg-papel"
                  }`}
                  aria-hidden
                />
                <div className="min-w-0">
                  <p className={`text-[15px] ${c.pronto ? "font-semibold" : ""}`}>
                    {c.nome}
                    {c.pronto && <span className="rotulo ml-2 text-erva">disponível</span>}
                  </p>
                  <p className="mt-0.5 text-[13.5px] leading-snug text-suave">{c.detalhe}</p>
                </div>
              </li>
            ))}
          </ol>
        </Cartao>

        <Cartao titulo="Atalhos">
          <ul className="flex flex-col gap-2">
            {[
              { href: "/produtos", nome: "Produtos e insumos", chave: "cadastros.produtos" },
              { href: "/fornecedores", nome: "Fornecedores", chave: "cadastros.fornecedores" },
              { href: "/empresa", nome: "Dados da empresa", chave: "admin.empresa" },
              { href: "/usuarios", nome: "Quem tem acesso", chave: "admin.usuarios" },
              { href: "/lojas", nome: "Ajustes da operação", chave: "admin.unidades" },
              { href: "/auditoria", nome: "O que mudou no sistema", chave: "admin.auditoria" },
              { href: "/trocar-senha", nome: "Trocar minha senha" },
            ]
              .filter((a) => !a.chave || pode(a.chave))
              .map((a) => (
                <li key={a.href}>
                  <Link
                    href={a.href}
                    className="flex items-center justify-between rounded border border-linha px-3 py-2.5 text-[14.5px] hover:border-erva hover:text-erva"
                  >
                    {a.nome}
                    <span aria-hidden>›</span>
                  </Link>
                </li>
              ))}
          </ul>
        </Cartao>
      </div>
    </div>
  );
}
