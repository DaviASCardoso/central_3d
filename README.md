# Central

Aplicativo desktop de geração paramétrica de produtos para impressão 3D.

Cada produto vendável existe no repositório como um módulo Python que declara
seus parâmetros e sabe transformar valores em geometria sólida. A Central
descobre esses módulos, monta a interface de edição a partir da declaração,
renderiza numa viewport 3D, valida se a peça é imprimível, exporta em 3MF com
a orientação correta e entrega o arquivo ao Bambu Studio.

- **[CENTRAL.md](CENTRAL.md)** — especificação técnica e fonte de verdade da arquitetura.
- **[PLANO_V1.md](PLANO_V1.md)** — plano de execução da V1, commit a commit.
- **[docs/NOTAS_VERIFICACAO.md](docs/NOTAS_VERIFICACAO.md)** — verificações feitas contra as versões instaladas.

## Ambiente

O ambiente é gerenciado com [uv](https://docs.astral.sh/uv/) e o Python é fixado
em 3.12. As dependências pesadas — OCCT, VTK e Qt — ficam com versão exata para
que o ambiente seja reprodutível.

```console
uv sync
uv run pytest
uv run ruff check .
```

## Estado

V1 em construção. O acompanhamento por commit está em `PLANO_V1.md`.
