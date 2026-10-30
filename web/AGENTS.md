# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

⚠️ Escrito à mão, SEM as marcações `nextjs-agent-rules` (v1.2.0): com `agentRules: false` no
`next.config.mjs`, o Next 16.4 remove o bloco que ele mesmo gerencia — e, sendo o arquivo só o
bloco, apagava o arquivo a cada `next dev`/`next build`. Sem as marcações, ele não mexe aqui.
