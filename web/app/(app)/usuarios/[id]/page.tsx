"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Aviso, Carregando, Etiqueta } from "@/components/ui";
import FormularioUsuario, { Vinculo } from "../formulario";

type Usuario = {
  id: number;
  nome: string;
  email: string;
  telefone: string | null;
  ativo: boolean;
  bloqueado: boolean;
  ultimo_acesso: string | null;
  papeis: Vinculo[];
};

/** Corrigir um usuário — a mesma forma da criação, para o olho reconhecer. */
export default function PaginaUsuario() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [u, setU] = useState<Usuario | null>(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    try {
      // ⚠️ Não há `GET /usuarios/{id}`: a lista é a fonte. Equipe de restaurante
      // não passa de algumas dezenas, então trazer todos é honesto aqui — o que
      // não seria em produtos, com 2.800.
      const r = await api.listar<Usuario>("/usuarios?incluir_inativos=true&limite=500");
      const achado = r.itens.find((x) => String(x.id) === String(id));
      if (!achado) {
        setErro("Usuário não encontrado.");
        return;
      }
      setU(achado);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!u) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/usuarios" className="link-voltar">
          usuários
        </Link>
        <h1 className="mt-1 break-words text-[24px] font-bold tracking-tight sm:text-[30px]">
          {u.nome}
        </h1>
        <p className="mt-1 text-suave">{u.email}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {!u.ativo && <Etiqueta cor="alerta">inativo</Etiqueta>}
          {u.bloqueado && <Etiqueta cor="alerta">bloqueado</Etiqueta>}
          <span className="text-[12.5px] text-suave">
            último acesso:{" "}
            {u.ultimo_acesso ? new Date(u.ultimo_acesso).toLocaleString("pt-BR") : "nunca"}
          </span>
        </div>
      </header>

      <FormularioUsuario
        inicial={{
          nome: u.nome,
          email: u.email,
          telefone: u.telefone ?? "",
          senha: "",
          papeis: u.papeis.map((v) => v.id_papel),
        }}
        id={u.id}
        aoGravar={() => router.push("/usuarios")}
      />
    </div>
  );
}
