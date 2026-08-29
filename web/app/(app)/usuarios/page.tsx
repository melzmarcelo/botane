"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { Vinculo } from "./formulario";

/**
 * A lista de quem tem acesso — só a lista.
 *
 * ⚠️ **O cadastro saiu da coluna da direita.** A lista de papéis cresce com o
 * sistema e cada um tem descrição de duas linhas; espremida em 380 px, ela
 * empurrava o botão de salvar para fora da tela, e quem cadastrava marcava as
 * caixinhas sem ver o que marcava. Mesmo corte de Compras, Vendas e
 * Fornecedores.
 */

type Usuario = {
  id: number;
  nome: string;
  email: string;
  telefone: string | null;
  ativo: boolean;
  ultimo_acesso: string | null;
  bloqueado: boolean;
  papeis: Vinculo[];
};

export default function PaginaUsuarios() {
  const aviso = useAviso();
  const { eu } = useSessao();
  const [usuarios, setUsuarios] = useState<Usuario[] | null>(null);
  const [erro, setErro] = useState("");
  const [link, setLink] = useState<{ nome: string; url: string } | null>(null);
  const pag = usePaginacao("usuarios");

  const carregar = useCallback(async () => {
    try {
      const q = new URLSearchParams(pag.parametros);
      q.set("incluir_inativos", "true");
      const u = await api.listar<Usuario>(`/usuarios?${q}`);
      setUsuarios(u.itens);
      pag.setTotal(u.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.offset, pag.porPagina]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function alternarAtivo(u: Usuario) {
    setErro("");
    try {
      if (u.ativo) await api.delete(`/usuarios/${u.id}`);
      else await api.put(`/usuarios/${u.id}`, { ativo: true });
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao mudar a situação");
    }
  }

  async function desbloquear(u: Usuario) {
    await api.post(`/usuarios/${u.id}/desbloquear`);
    await carregar();
  }

  /**
   * Manda o link de recuperação — e mostra o link.
   *
   * Enquanto não houver SMTP configurado, é assim que o dono resolve o
   * esquecimento da equipe: copia o link e passa pela pessoa. Continua sendo
   * melhor que escolher uma senha pela outra pessoa e mandá-la por mensagem,
   * porque o link vale meia hora e quem escolhe a senha é o dono dela.
   */
  async function linkDeSenha(u: Usuario) {
    setErro("");
    setLink(null);
    try {
      const r = await api.post<{ link: string; modo: string; message: string }>(
        `/usuarios/${u.id}/recuperar-senha`,
      );
      aviso.sucesso(r.message);
      if (r.modo !== "real") setLink({ nome: u.nome, url: r.link });
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar o link");
    }
  }

  if (erro && !usuarios) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!usuarios) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Administração</p>
          <h1 className="mt-1 text-[30px] font-bold tracking-tight">Usuários</h1>
          <p className="mt-1 max-w-[62ch] text-suave">
            Cada pessoa da casa com o seu login. O papel decide o que ela vê — e quem confere é
            o servidor, não a tela.
          </p>
        </div>
        <Link href="/usuarios/novo" className="btn btn-primario">
          Novo usuário
        </Link>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {link && (
        <Cartao
          titulo={`Link para ${link.nome}`}
          descricao="Vale por 30 minutos e só pode ser usado uma vez."
          acao={
            <div className="flex items-center gap-2">
              <button
                className="btn btn-secundario"
                onClick={() => void navigator.clipboard.writeText(link.url)}
              >
                Copiar
              </button>
              <button className="link-acao link-acao-erro" onClick={() => setLink(null)}>
                fechar
              </button>
            </div>
          }
        >
          <p className="mono break-all text-[13px]">{link.url}</p>
        </Cartao>
      )}

      <Cartao titulo="Quem tem acesso">
        {!usuarios.length ? (
          <Vazio>Nenhum usuário ainda.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Pessoa</th>
                  <th>Papéis</th>
                  <th>Último acesso</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {usuarios.map((u) => (
                  <tr key={u.id} className={u.ativo ? "" : "opacity-55"}>
                    <td>
                      <Link href={`/usuarios/${u.id}`} className="text-left">
                        <span className="link-registro">{u.nome}</span>
                        <span className="block text-[13px] text-suave">{u.email}</span>
                      </Link>
                      {u.bloqueado && (
                        <button
                          className="link-acao link-acao-erro mt-1 flex w-fit"
                          onClick={() => void desbloquear(u)}
                        >
                          bloqueado · desbloquear
                        </button>
                      )}
                      {u.ativo && (
                        <button
                          className="link-acao mt-1 flex w-fit"
                          onClick={() => void linkDeSenha(u)}
                        >
                          esqueceu a senha?
                        </button>
                      )}
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {u.papeis.length ? (
                          u.papeis.map((v) => (
                            <Etiqueta key={v.id_papel} cor="erva">
                              {v.papel}
                            </Etiqueta>
                          ))
                        ) : (
                          <Etiqueta cor="alerta">sem papel</Etiqueta>
                        )}
                      </div>
                    </td>
                    <td className="mono text-[13px] text-suave">
                      {u.ultimo_acesso
                        ? new Date(u.ultimo_acesso).toLocaleString("pt-BR")
                        : "nunca"}
                    </td>
                    <td className="text-right">
                      {u.id !== eu?.id && (
                        <button
                          className="link-acao"
                          onClick={() => void alternarAtivo(u)}
                        >
                          {u.ativo ? "desativar" : "reativar"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Paginacao p={pag} rotulo="usuário(s)" />
      </Cartao>
    </div>
  );
}
