"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import FormularioUsuario, { VAZIO } from "../formulario";

/**
 * Cadastrar usuário — página própria.
 *
 * A lista de papéis cresce com o sistema e cada um tem descrição de duas linhas;
 * espremida na coluna de 380 px da lista, ela empurrava o botão de salvar para
 * fora da tela, e quem cadastrava marcava as caixinhas sem ver o que marcava.
 */
export default function PaginaNovoUsuario() {
  const router = useRouter();
  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/usuarios" className="link-voltar">
          usuários
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">Novo usuário</h1>
        <p className="mt-2 max-w-[70ch] text-suave">
          Cada pessoa da casa com o seu login. A senha que você põe aqui é provisória —{" "}
          <b>a pessoa troca no primeiro acesso</b>, e a definitiva ninguém mais vê.
        </p>
      </header>

      <FormularioUsuario inicial={VAZIO} aoGravar={() => router.push("/usuarios")} />
    </div>
  );
}
