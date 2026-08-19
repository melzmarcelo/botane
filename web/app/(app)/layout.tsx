"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ProvedorSessao, useSessao } from "@/lib/sessao";
import { api, urlArquivo } from "@/lib/api";
import { EVENTO_EMPRESA } from "@/lib/eventos";

/** O menu é montado pelas permissões de quem entrou. */
const MENU: { grupo: string; itens: { href: string; nome: string; chave?: string }[] }[] = [
  {
    grupo: "Operação",
    itens: [{ href: "/", nome: "Início" }],
  },
  {
    grupo: "Cadastros",
    itens: [
      { href: "/produtos", nome: "Produtos", chave: "cadastros.produtos" },
      { href: "/fichas", nome: "Fichas técnicas", chave: "fichas.visualizar" },
      { href: "/fornecedores", nome: "Fornecedores", chave: "cadastros.fornecedores" },
      { href: "/cadastros", nome: "Tabelas de apoio", chave: "cadastros.setores" },
    ],
  },
  {
    grupo: "Estoque",
    itens: [
      { href: "/estoque", nome: "Saldos e movimentos", chave: "estoque.saldos" },
      { href: "/producao", nome: "Produção", chave: "estoque.saidas" },
      { href: "/inventario", nome: "Inventário", chave: "estoque.inventario" },
    ],
  },
  {
    grupo: "Compras",
    itens: [{ href: "/compras", nome: "Notas de entrada", chave: "compras.notas" }],
  },
  {
    grupo: "CMV",
    itens: [
      { href: "/cmv", nome: "Painel de CMV", chave: "cmv.painel" },
      { href: "/vendas", nome: "Vendas", chave: "cmv.painel" },
    ],
  },
  {
    grupo: "Administração",
    itens: [
      { href: "/empresa", nome: "Empresa", chave: "admin.empresa" },
      { href: "/lojas", nome: "Lojas e parâmetros", chave: "admin.unidades" },
      { href: "/usuarios", nome: "Usuários", chave: "admin.usuarios" },
      { href: "/papeis", nome: "Papéis e permissões", chave: "admin.papeis" },
      { href: "/integracoes", nome: "Integrações", chave: "admin.integracoes" },
      { href: "/auditoria", nome: "Auditoria", chave: "admin.auditoria" },
    ],
  },
];

function Marca({ logo, nome }: { logo: string | null; nome: string }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={logo} alt="" className="h-7 w-7 shrink-0 rounded object-contain" />
      ) : null}
      <span className="truncate text-[20px] font-extrabold tracking-[-0.03em]">{nome}</span>
    </span>
  );
}

function Casca({ children }: { children: React.ReactNode }) {
  const { eu, carregando, pode, sair } = useSessao();
  const caminho = usePathname();
  const [aberto, setAberto] = useState(false);
  const [marca, setMarca] = useState<{ nome: string; logo: string | null }>({
    nome: "Botané Deli e Café",
    logo: null,
  });

  // Fecha a gaveta ao navegar — no celular ela cobre a tela inteira.
  useEffect(() => setAberto(false), [caminho]);

  useEffect(() => {
    const fechar = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    window.addEventListener("keydown", fechar);
    return () => window.removeEventListener("keydown", fechar);
  }, []);

  useEffect(() => {
    if (!eu) return;
    const buscarMarca = () =>
      api
        .get<{ nome_fantasia: string | null; razao_social: string | null; logo_url: string | null }>(
          "/empresa",
        )
        .then((e) =>
          setMarca({
            nome: e.nome_fantasia || e.razao_social || "Botané Deli e Café",
            logo: urlArquivo(e.logo_url),
          }),
        )
        .catch(() => {});

    void buscarMarca();
    // A tela de empresa avisa quando o nome ou a logo mudam — sem isso o topo
    // só atualizaria no próximo carregamento da página.
    const ouvir = () => void buscarMarca();
    window.addEventListener(EVENTO_EMPRESA, ouvir);
    return () => window.removeEventListener(EVENTO_EMPRESA, ouvir);
  }, [eu]);

  if (carregando) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="rotulo">carregando…</p>
      </main>
    );
  }
  if (!eu) return null;

  const loja = eu.unidades[0];

  const navegacao = (
    <nav className="px-3 pb-5">
      {MENU.map((g) => {
        const itens = g.itens.filter((i) => !i.chave || pode(i.chave));
        if (!itens.length) return null;
        return (
          <div key={g.grupo} className="mb-4 shrink-0">
            <p className="rotulo px-2 pb-1.5">{g.grupo}</p>
            <ul className="flex flex-col gap-0.5">
              {itens.map((i) => {
                const ativo = caminho === i.href;
                return (
                  <li key={i.href}>
                    <Link
                      href={i.href}
                      className={`block rounded px-2 py-2.5 text-[15px] lg:py-1.5 lg:text-[14.5px] ${
                        ativo
                          ? "bg-erva-claro font-semibold text-erva"
                          : "text-tinta hover:bg-superficie2"
                      }`}
                    >
                      {i.nome}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );

  const rodapeUsuario = (
    <div className="border-t border-linha px-5 py-4">
      <p className="truncate text-[14px] font-semibold">{eu.nome}</p>
      <p className="truncate text-[12.5px] text-suave">{eu.papeis.join(", ") || "sem papel"}</p>
      <div className="mt-2 flex gap-4">
        <Link href="/trocar-senha" className="rotulo hover:text-erva">
          trocar senha
        </Link>
        <button className="rotulo hover:text-erva" onClick={() => void sair()}>
          sair
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      {/* ---------- celular: barra fixa + gaveta ---------- */}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-linha bg-papel px-4 py-3 lg:hidden">
        <button
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-linha2 bg-superficie"
          onClick={() => setAberto(true)}
          aria-label="Abrir menu"
          aria-expanded={aberto}
        >
          <span className="flex flex-col gap-[3px]">
            <span className="block h-[2px] w-4 bg-tinta" />
            <span className="block h-[2px] w-4 bg-tinta" />
            <span className="block h-[2px] w-4 bg-tinta" />
          </span>
        </button>
        <Marca logo={marca.logo} nome={marca.nome} />
      </header>

      {aberto && (
        <div
          className="fixed inset-0 z-40 bg-tinta/35 lg:hidden"
          onClick={() => setAberto(false)}
          aria-hidden
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-[268px] flex-col overflow-y-auto border-r border-linha bg-superficie transition-transform duration-200 lg:sticky lg:top-0 lg:z-auto lg:h-screen lg:w-auto lg:translate-x-0 ${
          aberto ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex shrink-0 items-center justify-between gap-2 px-5 pb-4 pt-5">
          <Marca logo={marca.logo} nome={marca.nome} />
          <button
            className="rotulo lg:hidden"
            onClick={() => setAberto(false)}
            aria-label="Fechar menu"
          >
            fechar
          </button>
        </div>

        {/* Com uma loja só o seletor não aparece — mas o dado já é por loja. */}
        {loja && eu.unidades.length === 1 && (
          <p className="rotulo shrink-0 truncate px-5 pb-3">{loja.apelido ?? loja.nome}</p>
        )}
        {eu.unidades.length > 1 && (
          <div className="px-5 pb-3">
            <select className="campo mono py-1.5 text-[12px]">
              {eu.unidades.map((u) => (
                <option key={u.id}>{u.apelido ?? u.nome}</option>
              ))}
            </select>
          </div>
        )}

        {/* min-h-0 + overflow no meio: sem isso o flex comprime os grupos do menu
            quando ele cresce, e os rótulos se sobrepõem. */}
        <div className="min-h-0 flex-1 overflow-y-auto">{navegacao}</div>
        <div className="shrink-0">{rodapeUsuario}</div>
      </aside>

      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-9">
        <div className="mx-auto max-w-[1180px]">{children}</div>
      </main>
    </div>
  );
}

export default function LayoutApp({ children }: { children: React.ReactNode }) {
  return (
    <ProvedorSessao>
      <Casca>{children}</Casca>
    </ProvedorSessao>
  );
}
