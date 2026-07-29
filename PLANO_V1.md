# PLANO_V1 — Central

## Contexto

A V1 implementa as entregas 1 a 4 da seção 17 do `CENTRAL.md`: contrato,
descoberta e produto de exemplo por linha de comando; janela com biblioteca,
viewport e inspetor gerado; geração assíncrona com worker, cancelamento,
debounce, cache e tesselagem em dois níveis; portão de qualidade, exportação
3MF e abertura no Bambu Studio nos níveis básico e intermediário.

Fora da V1, e ausentes deste plano inclusive como esqueleto vazio: Lote, banco
SQLite, presets, fatiamento headless, precificação, miniaturas da biblioteca,
plano de corte e cubo de orientação (seção 17, entregas 5 a 7).

Ao final da V1 existem também `CONTRATO.md`, `produtos/_template/` e
`scripts/novo_produto.py` — os três artefatos que fazem um produto novo custar
vinte minutos.

## Situação

| Entrega | Commits | Concluídos |
| --- | --- | --- |
| 1 — contrato, descoberta, produto, CLI | 10 | 10 |
| 2 — janela, biblioteca, viewport, inspetor | 5 | 5 |
| 3 — assíncrono, cache, hot reload | 5 | 5 |
| 4 — qualidade, exportação, Bambu Studio | 5 | 0 |
| Fechamento — os três artefatos | 2 | 0 |
| **Total** | **27** | **20** |

## Protocolo de execução

Um commit por vez: implementar todas as tarefas, rodar `uv run pytest` e
`uv run ruff check .`, verificar o critério de aceite, commitar com a mensagem
planejada, dar push, reportar o que ficou pronto e o que foi verificado, e só
então passar ao próximo. Sem juntar commits, sem adiantar trabalho, sem deixar
para commitar no final.

Se um commit revelar que o plano está errado dali em diante, a execução para,
a mudança é explicada e este arquivo é revisado antes de continuar — mesma
regra que vale para o `CENTRAL.md`.

## Ambiente e convenções

`uv` com `pyproject.toml`, Python 3.12. Dependências pesadas fixadas em `==`
porque carregam binários nativos; leves em `~=`. `uv.lock` versionado.

```
build123d==0.11.1      vtk==9.6.2           PySide6==6.11.1
trimesh==4.12.2        numpy==2.5.1         lib3mf==2.5.0
cadquery-ocp-novtk==7.9.3.1.1
dev: pytest, pytest-qt, ruff
```

`watchdog` entra no commit E3.C6 e `pydantic` no E4.C3, quando passam a ter uso
real. Nenhuma dependência é declarada antes disso.

A seção 18 do `CENTRAL.md` vale sem exceção, e o `ruff` está configurado para
fazê-la cumprir: `PTH` (pathlib em vez de `os.path`), `T20` (logging em vez de
`print`), `D` com convenção Google, `ANN` (anotação de tipo completa) e `E722`
(nenhum `except` nu). Identificadores e docstrings do domínio em português.

---

## Entrega 1 — contrato, descoberta, produto de exemplo e CLI

Sem interface nenhuma. Ao final, `uv run central-cli gerar placa_nome --nome
Helena` produz um 3MF.

### ✅ E1.C1 — `chore: inicializa projeto com ambiente reprodutível`

- **Tarefas:** `pyproject.toml` com metadados, dependências fixadas e
  configuração de ruff e pytest; `uv.lock`; `.gitignore` cobrindo cache e saída
  da Central; `README.md`; `central/__init__.py` com `__version__`;
  `central/log.py` com a configuração central de logging; `tests/conftest.py`.
- **Arquivos:** `pyproject.toml`, `uv.lock`, `.gitignore`, `.gitattributes`,
  `README.md`, `central/__init__.py`, `central/log.py`, `tests/conftest.py`,
  `tests/test_ambiente.py`
- **Aceite:** `uv sync` reproduz o ambiente e as dependências pesadas importam;
  `uv run pytest` verde; `uv run ruff check .` limpo; teste afirma que as
  versões instaladas batem com as fixadas.
- **Depende de:** —
- **Verificado:** 11 testes passando, ruff limpo, Python 3.12.13, as sete
  dependências fixadas conferem com o instalado.

### ✅ E1.C2 — `docs: registra verificações da seção 19 e emenda o CENTRAL.md`

- **Tarefas:** `docs/NOTAS_VERIFICACAO.md` com a evidência bruta dos três
  pontos da seção 19 e o método de captura da saída do Bambu Studio; emendas ao
  `CENTRAL.md` nas seções 2, 6, 8, 9 e 19; este arquivo.
- **Arquivos:** `docs/NOTAS_VERIFICACAO.md`, `CENTRAL.md`, `PLANO_V1.md`
- **Aceite:** as emendas estão no `CENTRAL.md` marcadas como verificadas em
  2026-07-28; as notas contêm a linha `BambuStudio-02.07.01.62` e a seção
  `OPTIONS:` íntegra.
- **Depende de:** E1.C1

### ✅ E1.C3 — `feat(contrato): define Param, Corpo, Resultado e Produto`

- **Tarefas:** `TipoParam`, `Param`, `Corpo`, `Resultado` e `Produto` conforme a
  seção 4, com as docstrings do documento.
- **Arquivos:** `central/contrato/__init__.py`, `central/contrato/tipos.py`,
  `tests/test_contrato.py`
- **Aceite:** teste importa o contrato num subprocesso limpo e afirma que
  `PySide6`, `vtkmodules` e `build123d` não entraram em `sys.modules`; `Param` e
  `Produto` são `frozen` e rejeitam atribuição; `Resultado` não compartilha
  defaults mutáveis entre instâncias.
- **Depende de:** E1.C1

### ✅ E1.C4 — `feat(nucleo): descoberta de produtos tolerante a falhas`

- **Tarefas:** `registro.py` varrendo `produtos/` com `pkgutil.iter_modules`,
  importando cada pacote sob `try/except Exception` com traceback preservado e
  indexando os manifestos por `id`; `ProdutoComFalha` com id, caminho e
  traceback; `erros.py` com a hierarquia de exceções.
- **Arquivos:** `central/nucleo/__init__.py`, `central/nucleo/registro.py`,
  `central/nucleo/erros.py`, `produtos/__init__.py`, `tests/test_registro.py`,
  fixtures de produtos válidos e quebrados
- **Aceite:** com 2 produtos válidos e 1 que levanta no import, a descoberta
  devolve 2 manifestos e 1 falha com traceback não vazio, sem levantar; pacote
  sem `MANIFESTO` também vira falha nomeada.
- **Depende de:** E1.C3

### ✅ E1.C5 — `feat(nucleo): validação de parâmetros em duas etapas`

- **Tarefas:** etapa 1 por `Param` (coerção de tipo, mínimo, máximo, `max_len`,
  `padrao_regex` com casamento total, pertinência a `opcoes`); etapa 2 pelo
  `validar` do manifesto; erros indexados por chave; preenchimento dos ausentes
  com o padrão.
- **Arquivos:** `central/nucleo/validacao.py`, `tests/test_validacao.py`
- **Aceite:** testes parametrizados cobrindo limite inferior, superior, fora de
  faixa, tipo errado, regex parcial recusada, opção inválida e `max_len` para
  cada `TipoParam`; erro do `validar` aparece com a chave certa; mensagens em
  português.
- **Depende de:** E1.C3

### ✅ E1.C6 — `feat(nucleo): helpers de geometria com texto_solido memoizado`

- **Tarefas:** `texto_solido(texto, fonte, tamanho, espessura)` com `lru_cache`
  na tupla exata, validando o nome da fonte contra as disponíveis para impedir a
  substituição silenciosa do OCCT; `assentar_na_mesa`; `dimensoes`.
- **Arquivos:** `central/nucleo/helpers.py`, `tests/test_helpers.py`
- **Aceite:** segunda chamada idêntica marca `hits == 1` em `cache_info()`;
  fonte inexistente levanta erro nomeado em vez de cair no Arial;
  `assentar_na_mesa` deixa o mínimo Z em zero e o centro XY na origem dentro de
  1e-6.
- **Depende de:** E1.C3

### ✅ E1.C7 — `feat(nucleo): pipeline síncrono de geração e tesselagem absoluta`

- **Tarefas:** `gerar_sincrono()` no pipeline da seção 6 — validar, gerar,
  normalizar, orientar, tesselar; normalização aceitando sólido solto, lista de
  sólidos ou `Resultado`, nomeando `corpo_1`, `corpo_2` e assim por diante;
  `tesselagem.py` com `isRelative=False`, soldagem de vértices e conversão para
  `trimesh.Trimesh`.
- **Arquivos:** `central/nucleo/geracao.py`, `central/nucleo/tesselagem.py`,
  `tests/test_geracao.py`, `tests/test_tesselagem.py`
- **Aceite:** as três formas de retorno viram `Resultado` equivalente; a peça
  sai assentada e centrada; a malha do cilindro de raio 20 a 0,015 mm e 0,2 rad
  é estanque e tem volume dentro de 0,1 % do analítico.
- **Depende de:** E1.C5, E1.C6

### ✅ E1.C8 — `feat(produtos): placa com nome em relevo como produto de referência`

- **Tarefas:** produto de referência da seção 17 — cubo com texto em relevo —
  usando `texto_solido`, com os limites da seção 8 codificados nos `Param`
  (traço mínimo de 0,8 mm, relevo mínimo de 0,6 mm) e `validar` recusando
  combinações fisicamente ruins; cabeçalho com as três exigências sobre `gerar`;
  teste genérico de produtos da seção 15.
- **Arquivos:** `produtos/placa_nome/__init__.py`,
  `produtos/placa_nome/geometria.py`, `tests/test_produtos.py`
- **Aceite:** a fixture parametrizada descobre todos os produtos, gera cada um
  com os padrões e afirma estanqueidade, volume positivo e cabimento em
  256×256×256; `validar` rejeita nome vazio e relevo abaixo de 0,6 mm.
- **Depende de:** E1.C7, E1.C4

### ✅ E1.C9 — `feat(nucleo): exportação 3MF multi-objeto e STL`

- **Tarefas:** escrita de 3MF com `lib3mf` direto a partir da malha de
  exportação — um `MeshObject` por `Corpo`, nome, cor via `basematerials`,
  unidade em milímetros e um build item por corpo; STL pela mesma malha.
- **Arquivos:** `central/nucleo/exportacao.py`, `tests/test_exportacao.py`
- **Aceite:** um `Resultado` de 2 corpos produz um 3MF cujo `3D/3dmodel.model`
  tem exatamente 2 `<object>` nomeados, 2 `<base displaycolor=...>`,
  `unit="millimeter"` e 2 `<item>`; a contagem de triângulos no XML é idêntica à
  da malha validada; o STL relido tem volume dentro de 0,5 % do sólido.
- **Depende de:** E1.C7

### ✅ E1.C10 — `feat(cli): geração e exportação por linha de comando`

- **Tarefas:** `listar` mostrando produtos descobertos e falhos; `gerar <id>`
  com os parâmetros como opções, `--saida` e `--formato`; erros de validação
  impressos por campo; entry point `central-cli`.
- **Arquivos:** `central/cli.py`, `pyproject.toml`, `tests/test_cli.py`
- **Aceite:** `listar` mostra `placa_nome`; `gerar placa_nome --nome Helena
  --saida saidas/` cria o arquivo e sai com código 0; parâmetro fora de faixa
  sai com código 2 apontando o campo; nenhuma importação de Qt ou VTK no caminho
  da CLI.
- **Depende de:** E1.C9, E1.C8

---

## Entrega 2 — janela, biblioteca, viewport e inspetor

Geração síncrona, com o travamento momentâneo aceito. As abas são Biblioteca e
Editor apenas: Lote e Catálogo não existem na V1 e não entram como aba vazia.

### ✅ E2.C1 — `feat(ui): janela principal com abas e tema escuro`

- **Arquivos:** `central/app.py`, `central/ui/janela.py`, `central/ui/tema.py`,
  `pyproject.toml`, `tests/test_ui_janela.py`
- **Aceite:** teste `pytest-qt` abre a janela sem exceção e afirma as duas abas;
  `uv run central` abre a janela de verdade.
- **Depende de:** E1.C10

### ✅ E2.C2 — `feat(ui): viewport VTK com mesa e volume de construção`

- **Tarefas:** wrapper único do VTK com o binding fixado antes do import; mesa
  de 256×256 com grade a cada 10 mm e perímetro reforçado; arestas verticais até
  256 mm; três luzes direcionais; material fosco com leve especularidade;
  arestas de silhueta; interação de CAD; troca de malha por swap de
  `vtkPolyData` no mesmo ator.
- **Arquivos:** `central/ui/viewport.py`, `tests/test_ui_viewport.py`
- **Aceite:** teste afirma os atores da mesa e do volume; trocar a malha mantém
  o mesmo ator e não altera a posição da câmera; a primeira carga enquadra.
- **Depende de:** E2.C1

### ✅ E2.C3 — `feat(ui): biblioteca em grade de cards`

- **Tarefas:** grade com nome, categoria, versão e descrição; filtro por
  categoria e busca em nome, descrição e tags; card vermelho para produto com
  falha, com traceback em diálogo copiável. Sem miniaturas, que são da entrega 7.
- **Arquivos:** `central/ui/biblioteca.py`, `tests/test_ui_biblioteca.py`
- **Aceite:** com 1 produto válido e 1 falho, a grade mostra 2 cards e um deles
  é o vermelho com traceback acessível; busca por tag filtra; clique emite o
  sinal com o id.
- **Depende de:** E2.C1

### ✅ E2.C4 — `feat(ui): inspetor gerado a partir da declaração de Param`

- **Tarefas:** mapeamento fixo de tipo para widget conforme a seção 11; unidade
  como sufixo dentro do campo; grupos na ordem declarada; avançados em seção
  colapsada ao final; `visivel_se` reavaliado a cada mudança, com o valor
  preservado quando escondido; erro de validação grifado no campo culpado.
  Nenhuma regra de negócio: o inspetor só emite o dicionário.
- **Arquivos:** `central/ui/inspetor.py`, `tests/test_ui_inspetor.py`
- **Aceite:** dado um produto com um `Param` de cada tipo, o inspetor cria a
  classe de widget esperada para cada um; slider e spinbox permanecem em
  sincronia; `visivel_se` esconde o campo e o valor continua no dicionário
  emitido; o grifo aparece na chave recusada.
- **Depende de:** E2.C1, E1.C5

### ✅ E2.C5 — `feat(ui): editor de três painéis com geração síncrona`

- **Tarefas:** árvore de corpos recolhível com visibilidade por corpo; viewport
  ao centro; inspetor à direita; barra de status com estado, avisos do produto e
  dimensões finais; barra de ferramentas com restaurar padrões.
- **Arquivos:** `central/ui/editor.py`, `central/ui/janela.py`,
  `tests/test_ui_editor.py`
- **Aceite:** abrir o produto pela biblioteca gera e exibe; mudar um valor
  regenera sem mover a câmera; desmarcar um corpo o esconde; a barra mostra as
  dimensões corretas e os avisos; restaurar padrões volta todos os campos.
- **Depende de:** E2.C2, E2.C3, E2.C4

---

## Entrega 3 — assíncrono, cache, tesselagem em dois níveis e hot reload

### ✅ E3.C1 — `feat(nucleo): tesselagem em dois níveis` — entregue no E1.C7

- **Aceite:** para a mesma peça o nível de preview produz ao menos 2× menos
  triângulos que o de exportação, e ambos saem estanques; o nível faz parte da
  chave de cache.
- **Depende de:** E2.C5

### ✅ E3.C2 — `feat(nucleo): cache de geometria com chave canônica`

- **Tarefas:** chave SHA-256 sobre id, versão e valores com `afeta_geometria`
  verdadeiro, serializados canonicamente; cache LRU em memória indexado também
  pelo nível de tesselagem.
- **Aceite:** a mesma entrada dá a mesma chave em processos distintos; mudar a
  versão invalida; mudar parâmetro que não afeta geometria não invalida; a ordem
  das chaves no dicionário não altera o hash.
- **Depende de:** E3.C1

### ✅ E3.C3 — `feat(nucleo): cache de disco content-addressed com teto LRU`

- **Tarefas:** persistência no diretório de dados do usuário, malha em binário
  compacto, teto configurável com padrão de dois gigabytes e limpeza por
  menos-recentemente-usado.
- **Aceite:** gerar duas vezes lê a segunda do disco e a malha recuperada é
  idêntica; estourar o teto remove o arquivo menos recente e preserva o mais
  recente.
- **Depende de:** E3.C2

### ✅ E3.C4 — `feat(nucleo): worker em QThread com cancelamento cooperativo`

- **Aceite:** dois pedidos em sequência fazem o primeiro terminar cancelado e só
  o segundo emitir pronto; produto que levanta emite erro com traceback legível
  e o worker segue vivo para o pedido seguinte.
- **Depende de:** E3.C3

### ✅ E3.C5 — `feat(ui): editor assíncrono com debounce e estado de geração legível`

- **Aceite:** arrastar o slider por dois segundos dispara uma geração, 250 ms
  após o último movimento; a interface responde durante a geração; a peça
  anterior nunca some; erro mostra o painel e o inspetor continua editável.
- **Depende de:** E3.C4

### ✅ E3.C6 — `feat(nucleo): recarregamento a quente dos módulos de produto`

- **Aceite:** editar um produto em disco recarrega em menos de um segundo;
  gravação em duas etapas dispara um único reload; erro de sintaxe não derruba
  nada e mantém o manifesto anterior; parâmetro removido volta ao padrão e os
  demais mantêm o valor.
- **Depende de:** E3.C5

---

## Entrega 4 — qualidade, exportação e Bambu Studio

### ⬜ E4.C1 — `feat(nucleo): portão de qualidade da malha de exportação`

- **Aceite:** malha boa é aprovada com relatório listando cada checagem; malha
  com furo é reprovada de forma bloqueante; faces degeneradas são reparadas e
  geram aviso; peça de 300 mm é reprovada por exceder o volume; `requer_suporte`
  gera aviso sem bloquear.
- **Depende de:** E3.C6

### ⬜ E4.C2 — `feat(nucleo): nomenclatura de arquivo e formatos adicionais`

- **Aceite:** `"Helena Ção <>:*?"` vira `helena-cao`; arquivo existente gera
  sufixo numérico sem tocar no original; um corpo por arquivo produz N arquivos;
  o STEP relido tem o mesmo volume.
- **Depende de:** E4.C1

### ⬜ E4.C3 — `feat(servicos): configuração e localização do Bambu Studio`

- **Tarefas:** configuração persistida no diretório de dados do usuário; nível
  básico por `QDesktopServices` e intermediário localizando o executável na
  ordem da seção 10 e passando o 3MF como argumento posicional, sempre com `cwd`
  controlado por causa do `result.json`.
- **Aceite:** a localização encontra o executável nesta máquina; com executável
  configurado, a invocação usa o caminho salvo; sem executável nenhum, cai no
  nível básico sem erro visível; a configuração sobrevive a um ciclo de escrita
  e leitura.
- **Depende de:** E4.C2

### ⬜ E4.C4 — `feat(ui): aba de configurações`

- **Aceite:** alterar o formato padrão e reabrir preserva a escolha; caminho
  inválido do Bambu é sinalizado no próprio campo.
- **Depende de:** E4.C3

### ⬜ E4.C5 — `feat(ui): exportar e abrir no Bambu a partir do editor`

- **Aceite:** ponta a ponta, o 3MF aparece na pasta de saída com o nome do
  template e abre no Bambu Studio; peça de 300 mm fica vermelha e o botão
  desabilitado com a razão visível; falha de estanqueidade bloqueia com a
  mensagem do portão.
- **Depende de:** E4.C4

---

## Fechamento da V1

### ⬜ F.C1 — `docs: extrato canônico do contrato em CONTRATO.md`

- **Aceite:** um produto escrito seguindo apenas o `CONTRATO.md`, sem consultar
  o código, é descoberto e passa no teste genérico de produtos.
- **Depende de:** E4.C5

### ⬜ F.C2 — `feat(scripts): template de produto e gerador novo_produto.py`

- **Aceite:** `uv run python scripts/novo_produto.py suporte_fone --nome
  "Suporte de Fone" --categoria Casa` cria o produto, que aparece na biblioteca
  e passa no teste genérico sem nenhuma edição manual; `_template` não aparece
  na biblioteca.
- **Depende de:** F.C1

---

## Grafo de dependências

```
E1.C1 → E1.C2
  └→ E1.C3 → E1.C4 ┐
              E1.C5 ├→ E1.C7 → E1.C8 ┐
              E1.C6 ┘         └ E1.C9 ┴→ E1.C10
E1.C10 → E2.C1 → {E2.C2, E2.C3, E2.C4} → E2.C5
E2.C5 → E3.C1 → E3.C2 → E3.C3 → E3.C4 → E3.C5 → E3.C6
E3.C6 → E4.C1 → E4.C2 → E4.C3 → E4.C4 → E4.C5
E4.C5 → F.C1 → F.C2
```

---

## Ajustes durante a execução

Registro do que saiu do plano original, e por quê.

- **E1.C1** — acrescentado `.gitattributes` normalizando finais de linha para
  LF. Não estava previsto; evita ruído em todo diff futuro no Windows.
- **E1.C1** — `result.json` acrescentado ao `.gitignore`. O `bambu-studio.exe`
  grava esse arquivo no diretório de trabalho corrente, inclusive rodando apenas
  com `--help`, e ele apareceu na raiz do repositório durante as verificações da
  seção 19. O commit E4.C3 invoca o executável com `cwd` controlado.
- **E1.C7** — descoberto que o OCCT guarda a triangulação dentro da forma e só
  remalha o que estiver pior que o pedido, o que fazia a malha depender da
  ordem das chamadas. Corrigido com `BRepTools.Clean_s` antes de malhar.
  Também: triângulos degenerados vindos do malhador, como os do polo de uma
  esfera, passaram a ser descartados na própria tesselagem, porque são
  artefato dela e não defeito do produto.
- **E1.C8** — acrescentado `central/nucleo/impressora.py` com o volume de
  construção. Não estava previsto, mas o número aparece na viewport, no portão
  de qualidade e no teste genérico, e não podia virar literal repetido.
- **E1.C8** — `CENTRAL.md` seção 18 esclarecida. A redação dizia que um produto
  só importa de `central.contrato`, o que contradizia a seção 6, que manda o
  produto usar o `texto_solido` do núcleo, e a seção 14, que o põe em
  `central/nucleo/helpers.py`. A exceção agora está escrita e é única.
- **E1.C9** — nenhum desvio; a garantia de que a malha gravada é a validada
  ficou travada pelo teste que conta `<triangle>` dentro do XML.
- **E1.C10** — o `argparse` abrevia opção longa por padrão, e `--nome` do
  produto casava com `--nome-do-arquivo` da CLI, gravando o valor no lugar
  errado em silêncio. Corrigido com `allow_abbrev=False` no analisador e em
  cada subparser, já que a opção não se propaga. Acrescentada também a recusa
  explícita quando um produto declara chave reservada pela CLI.
- **E2.C2** — a cor das arestas do volume de construção foi clareada depois de
  conferência visual: no valor original elas sumiam contra o fundo escuro.
- **E2.C5** — registrado para verificações futuras: `QWidget.grab()` do Qt não
  captura a superfície OpenGL nativa da viewport, e devolve um retângulo preto.
  Conferir a viewport exige `vtkWindowToImageFilter` sobre a janela de
  renderização do VTK.
- **E3.C1** — a tesselagem em dois níveis já havia sido entregue no E1.C7,
  porque o pipeline precisava dela e a exportação precisava do nível fino. Seu
  único critério pendente, o nível fazer parte da chave de cache, pertence ao
  E3.C2 e foi verificado lá. A entrega 3 passou de seis para cinco commits, e o
  total da V1 de 28 para 27.
- **E3.C6** — apareceu uma falha de acesso nativa: uma geração que conclui no
  instante em que a janela fecha tocava uma janela de OpenGL já finalizada.
  Vale para o app, não só para os testes. `Viewport.redesenhar` e os
  manipuladores de sinal do editor passaram a conferir o encerramento antes de
  tocar em qualquer coisa.
- **E3.C6** — um teste que eu havia escrito contradizia a seção 5: eu afirmava
  que erro de sintaxe num produto o transformava em falha na biblioteca, mas a
  seção 5 manda manter a versão anterior ativa, que é o que o código faz. O
  teste foi corrigido para afirmar o comportamento correto.
- **Infraestrutura** — o remoto `origin` passou de SSH para HTTPS, porque a
  chave privada `~/.ssh/id_ed25519` não é legível pelo processo que executa os
  comandos. Decisão do operador.

---

## Verificação de ponta a ponta da V1

1. `uv sync` num clone limpo reproduz o ambiente.
2. `uv run pytest` verde, incluindo o teste genérico que gera todo produto
   descoberto e afirma estanqueidade, volume positivo e cabimento no volume de
   construção.
3. `uv run ruff check .` limpo.
4. `uv run central-cli gerar placa_nome --nome Helena --saida saidas/` produz um
   3MF, e abri-lo no Bambu Studio mostra a peça assentada, centrada e na
   orientação de impressão.
5. `uv run central` abre a janela; a biblioteca lista o produto; abrir no editor
   gera; arrastar um slider mantém a interface fluida e a câmera parada;
   exportar mostra o relatório de qualidade e o arquivo abre no Bambu.
6. Com o aplicativo aberto, editar a geometria do produto num editor externo faz
   a peça atualizar sem reiniciar.
7. `uv run python scripts/novo_produto.py <id>` cria um produto que já aparece
   na biblioteca e passa nos testes.
