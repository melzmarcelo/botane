/**
 * A tela que aparece quando o aparelho perde a rede.
 *
 * A câmara fria e o depósito costumam ser o pior ponto de sinal da casa, e é
 * exatamente onde se conta o inventário. Dizer o que fazer vale mais que um
 * ícone triste: a contagem digitada continua na tela até salvar.
 */
export default function PaginaOffline() {
  return (
    <main className="mx-auto flex min-h-screen max-w-[52ch] flex-col justify-center gap-4 px-6">
      <p className="rotulo">Botané</p>
      <h1 className="text-[26px] font-bold tracking-tight">Sem conexão</h1>
      <p className="text-suave">
        O aparelho está sem internet. O que já estava aberto continua na tela — só não dá para
        buscar nem salvar nada enquanto o sinal não voltar.
      </p>
      <ul className="flex list-disc flex-col gap-1 pl-5 text-suave">
        <li>Na câmara fria e no depósito o sinal costuma cair: dê alguns passos e tente de novo.</li>
        <li>Se estiver contando o inventário, não feche esta janela — o que foi digitado
          continua aqui até você salvar.</li>
      </ul>
      <div>
        <a className="btn btn-primario inline-block no-underline" href="/">
          Tentar de novo
        </a>
      </div>
    </main>
  );
}
