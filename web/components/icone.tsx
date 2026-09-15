import { ICONES, type NomeIcone } from "@/lib/icones";

/**
 * Um ícone do menu. Herda a cor de quem o contém (`currentColor`) e é
 * `aria-hidden`: o nome da tela está escrito ao lado, e um leitor de tela
 * lendo "ícone de caixa, Produtos" diz a mesma coisa duas vezes.
 */
export default function Icone({
  nome,
  tamanho = 17,
  className = "",
}: {
  nome: NomeIcone;
  tamanho?: number;
  className?: string;
}) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d={ICONES[nome]} />
    </svg>
  );
}
