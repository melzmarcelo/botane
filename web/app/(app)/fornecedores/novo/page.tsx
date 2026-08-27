"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import FormularioFornecedor, { VAZIO } from "../formulario";

/**
 * Cadastrar fornecedor — página própria.
 *
 * Espremido na coluna da direita da lista, o formulário tinha treze campos numa
 * coluna de 360 px: quem cadastrava rolava a tela inteira para achar o botão, e
 * a lista, que é o assunto de `/fornecedores`, ficava empurrada para o lado.
 * Mesmo corte de Compras e de Vendas.
 */
export default function PaginaNovoFornecedor() {
  const router = useRouter();
  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/fornecedores" className="link-voltar">
          fornecedores
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Novo fornecedor
        </h1>
        <p className="mt-2 max-w-[70ch] text-suave">
          De quem a casa compra. O <b>CNPJ</b> é o que liga a nota fiscal que vem do Omie ao
          fornecedor certo — sem ele, a conciliação vira trabalho manual.
        </p>
      </header>

      <FormularioFornecedor inicial={VAZIO} aoGravar={() => router.push("/fornecedores")} />
    </div>
  );
}
