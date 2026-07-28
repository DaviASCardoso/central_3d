# CENTRAL — Especificação técnica

Documento de referência para a construção da Central, um aplicativo desktop de geração paramétrica de produtos para impressão 3D. Este arquivo é a fonte de verdade da arquitetura: qualquer decisão que o contrarie deve ser discutida antes de ser implementada, e qualquer decisão nova tomada durante a implementação deve ser registrada aqui.

---

## 1. O que a Central é

A Central é um catálogo executável. Cada produto vendável — porta-lápis com nome, chaveiro personalizado, plaquinha, suporte de fone, o que vier — existe no repositório como um módulo Python que declara quais parâmetros aceita e sabe transformar um conjunto de valores em geometria sólida. A Central descobre esses módulos sozinha, monta a interface de edição a partir da declaração de parâmetros, renderiza o resultado em tempo real numa viewport 3D, valida se a peça é imprimível, exporta no formato certo com a orientação certa e entrega o arquivo ao Bambu Studio.

O objetivo econômico por trás disso é encurtar o caminho entre "cliente pediu o nome Helena em roxo" e "arquivo fatiando", e permitir que quarenta pedidos personalizados virem quarenta arquivos numa passada só. O objetivo técnico é que criar um produto novo custe apenas escrever a função de geometria, porque todo o resto — formulário, preview, validação, exportação, nomenclatura, lote, precificação — já está resolvido pela Central e nunca é responsabilidade do produto.

A regra que sustenta o projeto inteiro: **o produto devolve geometria e nada mais**. Ele não escreve arquivos, não conhece o Bambu Studio, não sabe o que é uma janela, não lê configuração, não imprime log. Se um produto precisar fazer qualquer uma dessas coisas, o contrato está incompleto e é o contrato que deve mudar.

---

## 2. Escolha da stack, e por quê

O núcleo geométrico decide a linguagem. Geração paramétrica com texto, chanfros, filetes e operações booleanas confiáveis pede um kernel B-rep, e o único kernel B-rep maduro e livre é o OpenCASCADE. As bibliotecas que expõem o OCCT de forma produtiva — CadQuery e build123d — são Python, ligadas via OCP. As alternativas em outras linguagens não se sustentam num exame honesto: `truck` em Rust ainda é imaturo para filetes e texto, `opencascade.js` em WASM é lento e sofre com fontes, Manifold é excelente em CSG mas não faz B-rep nem texto vetorial, e escrever contra o OCCT em C++ diretamente custaria semanas antes do primeiro produto sair. OpenSCAD resolveria a geometria simples mas usa linguagem própria, o que mataria a premissa de gerar produto novo com Claude Code em Python.

Então Python está fixado pela camada de geometria. A pergunta restante é se a interface acompanha no mesmo processo ou fica do outro lado de uma fronteira de IPC. Tauri com sidecar Python daria uma UI mais bonita, ao custo de empacotar dois runtimes, serializar malhas de centenas de milhares de triângulos por pipe a cada ajuste de slider, e perder o recarregamento a quente dos módulos de produto no processo vivo. Para uma ferramenta desktop mono-usuário com payload de malha pesado e edição contínua de parâmetros, o processo único ganha com folga.

A stack, portanto, é **Python 3.12 com PySide6 para a interface e VTK para a viewport 3D**, com **build123d** sobre OCP como motor de geometria. PySide6 é o binding oficial do Qt e é LGPL, o que evita dor de licença na hora de distribuir. VTK é o único renderizador Python que aguenta milhões de triângulos com picking, planos de corte e orbit sem que se escreva um motor gráfico do zero; usar `vtkmodules` diretamente com o `QVTKRenderWindowInteractor` é preferível a passar por PyVista, porque reduz a cadeia de dependências e o risco de abandono, ao custo de mais código de boilerplate concentrado num único módulo de wrapper. Se a velocidade de desenvolvimento sofrer visivelmente com o VTK cru, PyVista mais `pyvistaqt` é o plano B aceitável, mas a troca deve ser deliberada e anotada aqui.

Complementam a stack `trimesh` para checagem de malha, `lib3mf` via a classe `Mesher` do build123d para escrita de 3MF, `watchdog` para recarregamento a quente, `pydantic` para validação de parâmetros e serialização de presets, `sqlite3` da biblioteca padrão para o catálogo, e `pytest` para os testes. Gerenciamento de ambiente com `uv`.

---

## 3. Arquitetura em camadas

A Central se divide em quatro camadas com dependência estritamente unidirecional, de cima para baixo, sem exceção.

Na base está o **contrato** (`central/contrato/`), que define `Param`, `Produto`, `Corpo` e `Resultado`. Não importa nada do resto do sistema, não conhece Qt, não conhece VTK, e pode ser importado por um script de linha de comando sem carregar interface nenhuma. Os módulos de produto dependem apenas desta camada.

Acima está o **núcleo** (`central/nucleo/`), que faz descoberta de produtos, validação de parâmetros, orquestração da geração, cache, tesselagem, checagem de qualidade da malha e exportação. Conhece o contrato e conhece geometria, mas não conhece interface. Toda a lógica de valor está aqui, e por isso toda ela é testável sem abrir uma janela.

Acima disso ficam os **serviços** (`central/servicos/`), que lidam com o mundo externo: localizar e invocar o Bambu Studio, ler e escrever o banco SQLite, gerenciar configurações, executar lotes em pool de processos, calcular preço.

No topo está a **interface** (`central/ui/`), que só monta widgets, liga sinais e exibe o que o núcleo produz. Nenhuma regra de negócio mora aqui. O teste mental é direto: se uma função da UI fosse apagada, nenhum comportamento de geometria, validação ou exportação poderia se perder junto.

---

## 4. O contrato

O contrato é a peça mais importante do projeto e a que mais deve resistir a mudanças. Ele vive em `central/contrato/tipos.py` e é o que o Claude Code lê antes de escrever qualquer produto novo.

```python
"""Contrato entre a Central e os módulos de produto."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class TipoParam(StrEnum):
    TEXTO = "texto"
    INTEIRO = "inteiro"
    DECIMAL = "decimal"
    BOOLEANO = "booleano"
    ESCOLHA = "escolha"
    COR = "cor"


@dataclass(frozen=True, slots=True)
class Param:
    """Declaração de um parâmetro editável de um produto.

    A Central usa esta declaração para três coisas ao mesmo tempo: construir
    o widget de edição, validar o valor antes de chamar `gerar`, e compor a
    chave de cache. Nenhum produto deve validar seus próprios parâmetros
    quando a validação puder ser expressa aqui.

    Attributes:
        chave: Nome do argumento recebido por `gerar`. snake_case, estável.
        rotulo: Texto exibido na interface.
        tipo: Determina o widget e a coerção de tipo.
        padrao: Valor inicial. Deve ser sempre válido segundo as restrições.
        minimo: Limite inferior inclusivo para tipos numéricos.
        maximo: Limite superior inclusivo para tipos numéricos.
        passo: Incremento do spinbox e do slider.
        max_len: Comprimento máximo para TEXTO.
        padrao_regex: Regex que TEXTO deve satisfazer por inteiro.
        opcoes: Valores permitidos para ESCOLHA.
        unidade: Sufixo exibido no campo, tipicamente "mm" ou "°".
        grupo: Título da seção do inspetor onde o campo aparece.
        ordem: Posição dentro do grupo, crescente.
        ajuda: Tooltip. Explique a consequência física, não repita o rótulo.
        avancado: Se verdadeiro, fica atrás do disclosure "Avançado".
        visivel_se: Recebe o dict de valores atuais e decide a visibilidade.
        afeta_geometria: Se falso, mudar este valor não invalida o cache de
            geometria — usar para cor de exibição e afins.
    """

    chave: str
    rotulo: str
    tipo: TipoParam
    padrao: Any
    minimo: float | None = None
    maximo: float | None = None
    passo: float | None = None
    max_len: int | None = None
    padrao_regex: str | None = None
    opcoes: tuple[str, ...] | None = None
    unidade: str | None = None
    grupo: str = "Geral"
    ordem: int = 0
    ajuda: str | None = None
    avancado: bool = False
    visivel_se: Callable[[dict[str, Any]], bool] | None = None
    afeta_geometria: bool = True
```

Sobre a geometria devolvida, o produto pode entregar um sólido só ou vários corpos nomeados. Vários corpos são o caso de tampa mais base, ou de peça bicolor pensada para troca de filamento, e a Central precisa saber distingui-los para colori-los na viewport e escrevê-los como objetos separados no 3MF.

```python
@dataclass(slots=True)
class Corpo:
    """Um sólido nomeado dentro do resultado de um produto.

    Attributes:
        nome: Identificador curto, usado no nome do arquivo quando exportado
            separadamente e como rótulo na árvore da viewport.
        forma: O sólido em si (build123d Part ou Compound).
        cor: Cor de exibição em hexadecimal. Não afeta a impressão.
        filamento: Índice de filamento sugerido para AMS, ou None.
    """

    nome: str
    forma: Any
    cor: str = "#8AB4F8"
    filamento: int | None = None


@dataclass(slots=True)
class Resultado:
    """O que `gerar` devolve.

    Attributes:
        corpos: Um ou mais sólidos. Nunca vazio.
        avisos: Mensagens dirigidas ao operador, exibidas em amarelo no
            painel de status. Use para dizer coisas como "nome longo demais
            foi comprimido em 8%".
        metadados: Informação livre para o catálogo, como uma descrição
            gerada ou o número de caracteres realmente gravados.
    """

    corpos: list[Corpo]
    avisos: list[str] = field(default_factory=list)
    metadados: dict[str, Any] = field(default_factory=dict)
```

O manifesto amarra tudo e carrega também o que a Central precisa saber sobre a impressão em si.

```python
@dataclass(frozen=True, slots=True)
class Produto:
    """Manifesto de um produto do catálogo.

    Attributes:
        id: Identificador estável em snake_case. Nunca muda depois de
            publicado, porque presets salvos apontam para ele.
        nome: Nome comercial exibido na biblioteca.
        versao: SemVer. Incrementar o minor quando a geometria mudar de
            forma perceptível, o major quando a lista de parâmetros quebrar
            compatibilidade com presets antigos.
        descricao: Um parágrafo curto para o card da biblioteca.
        categoria: Agrupamento na biblioteca, como "Papelaria" ou "Casa".
        tags: Termos de busca livres.
        params: Declaração completa dos parâmetros.
        gerar: A função de geometria.
        validar: Validação cruzada entre parâmetros que não cabe em Param.
            Recebe os valores e devolve uma lista de mensagens de erro;
            lista vazia significa válido.
        orientacao: Transformação aplicada pela Central antes de exportar,
            para que a peça caia na mesa já na posição de impressão. O
            produto deve modelar na posição que for mais conveniente.
        altura_camada_sugerida: Em mm, ou None para o padrão do perfil.
        requer_suporte: Declaração honesta, exibida como aviso na exportação.
        tempo_estimado_min: Chute grosseiro para ordenação na biblioteca,
            substituído pelo valor real quando o fatiamento headless roda.
    """

    id: str
    nome: str
    versao: str
    descricao: str
    categoria: str
    params: tuple[Param, ...]
    gerar: Callable[[dict[str, Any]], Any]
    tags: tuple[str, ...] = ()
    validar: Callable[[dict[str, Any]], list[str]] | None = None
    orientacao: Any | None = None
    altura_camada_sugerida: float | None = None
    requer_suporte: bool = False
    tempo_estimado_min: int | None = None
```

Três exigências pesam sobre a função `gerar` e devem estar escritas no topo de todo módulo de produto. Ela precisa ser **pura**, no sentido de que a mesma entrada produz sempre a mesma saída e nenhum efeito colateral acontece — sem I/O, sem estado global, sem randomização não semeada. Precisa ser **determinística inclusive na ordem das operações**, porque o cache é indexado por hash dos parâmetros e uma geometria que varia entre chamadas idênticas corrompe o cache silenciosamente. E precisa **não confiar nos valores recebidos como já validados em relação à física**, isto é, ela pode assumir que os tipos e as faixas declaradas em `Param` foram respeitados, mas se uma combinação legal de valores gerar parede de 0,3 mm, cabe ao `validar` do manifesto recusar antes, não a `gerar` improvisar.

---

## 5. Descoberta de produtos e recarregamento a quente

Os produtos vivem em `produtos/`, um pacote por produto, cada um com um `__init__.py` que expõe uma variável de módulo chamada `MANIFESTO` do tipo `Produto`. A descoberta varre o diretório com `pkgutil.iter_modules`, importa cada pacote dentro de um `try` que captura `Exception` e registra a falha sem derrubar o resto, e recolhe os manifestos válidos num registro em memória indexado por `id`. Um produto que falha ao importar aparece na biblioteca como um card vermelho com o traceback acessível em um clique, porque o operador precisa ver o erro em vez de ver o produto sumir.

O recarregamento a quente é uma funcionalidade central e não um luxo, porque o fluxo de trabalho previsto é escrever o produto com o Claude Code em outra janela e ver o resultado aparecer sem reiniciar. Um observador `watchdog` monitora `produtos/` recursivamente, e ao detectar escrita num arquivo `.py` espera duzentos milissegundos de silêncio para evitar disparar no meio de uma gravação parcial, então executa `importlib.reload` no pacote afetado, invalida todas as entradas de cache daquele `id` de produto e reemite o sinal de mudança para a UI. Se o produto estiver aberto no editor no momento, os valores atuais dos parâmetros são preservados quando as chaves continuam existindo, e os que sumiram do manifesto voltam ao padrão. Falha de reload nunca derruba o app: o erro vai para o console de desenvolvimento e a versão anterior do módulo continua ativa.

---

## 6. Motor de geração

Toda geração passa pelo mesmo caminho, e nunca acontece na thread da interface.

A UI emite uma intenção de gerar com um dicionário de valores. O núcleo primeiro roda a validação em duas etapas, começando por cada `Param` isoladamente — tipo, faixa, comprimento, regex, pertinência ao conjunto de opções — e depois pelo `validar` do manifesto, que enxerga todos os valores juntos. Erros de validação aparecem grifados no campo culpado e a geração nem chega a ser agendada.

Passada a validação, calcula-se a chave de cache como um hash SHA-256 do `id` do produto, da sua `versao`, e do dicionário de valores serializado de forma canônica considerando apenas os parâmetros com `afeta_geometria` verdadeiro. Se a chave existir no cache de geometria em memória, a malha de preview volta imediatamente e nada mais acontece.

Se não existir, o pedido vai para um worker em `QThread` carregando um token de cancelamento. Cada nova edição de parâmetro cancela o token do pedido anterior antes de agendar o novo, e o worker verifica o token entre as etapas do pipeline para abortar cedo. As edições contínuas de slider são debounceadas em duzentos e cinquenta milissegundos, com atualização imediata apenas dos parâmetros discretos como checkbox e combo. Uma etapa que já começou dentro do OCCT não pode ser interrompida no meio, então o cancelamento é cooperativo entre etapas e não instantâneo — isso é aceitável e não deve ser contornado com terminação forçada de thread.

Dentro do worker, o pipeline é sempre gerar, normalizar, orientar, tesselar, validar malha. A normalização aceita as três formas de retorno possíveis — um sólido solto, uma lista de sólidos, ou um `Resultado` completo — e converte tudo em `Resultado`, atribuindo nomes automáticos como `corpo_1` quando o produto não nomeou. A orientação aplica a transformação declarada no manifesto e, em seguida, translada o conjunto para que a menor cota em Z fique exatamente em zero e o centro do bounding box em XY fique na origem, de modo que a peça sempre caia assentada e centralizada na mesa.

A tesselagem tem dois níveis e essa distinção importa para a fluidez do app. O preview usa `BRepMesh_IncrementalMesh` com desvio linear de 0,08 mm e angular de 0,5 radiano, o que gera malha leve o bastante para atualizar em tempo real. A exportação usa 0,015 mm e 0,2 radiano, roda apenas quando o operador de fato exporta, e é a única tesselagem que entra na checagem de qualidade rigorosa. Malhas de preview e de exportação são cacheadas em chaves separadas.

Uma otimização específica vale ser implementada desde o começo, porque o gargalo aparece rápido: converter texto em contorno vetorial no OCCT é caro, e num produto de nome personalizado é justamente a operação repetida a cada ajuste de altura ou diâmetro. O núcleo deve expor um helper memoizado `texto_solido(texto, fonte, tamanho, espessura)` que os produtos usem em vez de chamar `Text` diretamente, com cache LRU indexado por essa tupla. Mudar o diâmetro do porta-lápis deixa de recomputar as letras.

O cache de disco é content-addressed, guardado em `%LOCALAPPDATA%/Central/cache/` no Windows e no equivalente XDG no Linux, com a chave de hash como nome de arquivo, contendo a malha serializada em formato binário compacto. Um teto configurável de tamanho, com padrão de dois gigabytes, dispara limpeza por menos-recentemente-usado.

---

## 7. Viewport e renderização

A viewport ocupa o centro da janela e é o elemento que faz o app parecer sério ou amador, então merece cuidado. Ela mostra a mesa da impressora como um plano quadriculado de 256 por 256 milímetros com marcação a cada dez milímetros e um contorno mais forte no perímetro, um volume de construção indicado por arestas verticais até 256 milímetros de altura, e a peça assentada nesse espaço com a orientação real de impressão. Peça que ultrapassa o volume é renderizada em vermelho translúcido e o botão de exportar fica desabilitado com a razão explicada.

A iluminação deve ser três luzes direcionais suaves em vez do padrão do VTK, e o material dos corpos deve ser fosco com leve especularidade, porque plástico brilhante demais engana sobre o resultado impresso. Cada corpo recebe a cor declarada. Arestas de silhueta desenhadas por cima ajudam a leitura da forma e valem o custo.

A interação segue a convenção de CAD: botão esquerdo orbita, botão do meio faz pan, roda dá zoom, duplo clique numa face enquadra nela. Um cubo de orientação no canto superior direito permite pular para as vistas ortogonais, e teclas numéricas de um a seis fazem o mesmo. Um plano de corte controlado por slider, alternável por um botão da barra, é o que permite verificar espessura de parede sem exportar nada, e vale a implementação com `vtkClipPolyData`.

Um detalhe que muda a percepção de qualidade: quando uma nova malha chega, a câmera nunca se reposiciona sozinha, exceto no primeiro carregamento do produto. Trocar de parâmetro e ver a câmera pular é irritante e destrói o senso de edição contínua. A troca de malha deve ser um swap de `vtkPolyData` no mesmo ator, sem recriar a cena.

A biblioteca precisa de miniaturas, e elas são geradas por renderização offscreen com os valores padrão do produto, em 512 por 512, com fundo transparente, na primeira vez em que o produto é descoberto, e cacheadas junto do cache de malha, invalidadas quando a versão do produto muda.

---

## 8. Portão de qualidade

Nenhum arquivo é exportado sem passar pela checagem, e o resultado dela é mostrado no painel de status mesmo quando tudo passa, porque a confirmação visível é o que constrói confiança na ferramenta.

A malha de exportação é carregada no `trimesh` e verificada quanto a estanqueidade com `is_watertight`, volume estritamente positivo, ausência de faces degeneradas e duplicadas, e coerência de normais com `is_winding_consistent`. Falha em estanqueidade é bloqueante e impede a exportação, porque malha não-manifold quebra no fatiador e o operador só descobriria dez minutos depois no Bambu Studio. Faces degeneradas em pequena quantidade geram aviso e uma tentativa automática de reparo com `trimesh.repair`, seguida de nova checagem.

Além da malha, a checagem geométrica compara o bounding box orientado com o volume de construção e verifica se a peça toca a mesa. Se o manifesto declara `requer_suporte`, um aviso aparece na exportação lembrando de habilitar suportes, porque essa é exatamente a informação que se esquece.

A checagem de espessura mínima de parede é tentadora e deve ficar fora do escopo inicial. Fazê-la corretamente exige análise de eixo medial ou amostragem por raios, ambas caras e imprecisas, e o retorno não justifica a complexidade. A defesa contra parede fina fica no `validar` do manifesto de cada produto, onde é barata e exata porque o produto conhece a própria geometria.

Como conhecimento a codificar nos produtos e não na Central: com bico de 0,4 mm, traço de texto abaixo de 0,8 mm de largura desaparece ou vira borrão, relevo abaixo de 0,6 mm de altura some no acabamento, e texto gravado para dentro em parede vertical sai visivelmente pior do que texto em relevo. Esses números devem virar limites nos `Param` dos produtos que envolvem texto.

---

## 9. Exportação

O formato padrão é **3MF**, escrito pela classe `Mesher` do build123d sobre o lib3mf, porque ele carrega unidades explicitamente, suporta múltiplos objetos nomeados num mesmo arquivo, e é o formato nativo do ecossistema Bambu. STL continua disponível como alternativa para compatibilidade, e STEP como exportação de engenharia para quem quiser editar a peça em outro CAD. A escolha do formato fica nas configurações com o 3MF como padrão, e a caixa de exportação permite sobrepor pontualmente.

Corpos múltiplos vão como objetos separados dentro do mesmo 3MF por padrão, preservando nomes e a sugestão de filamento. Uma opção permite exportar cada corpo como arquivo próprio, útil quando tampa e base vão para impressões diferentes.

O nome do arquivo vem de um template configurável cujo padrão é `{produto}_{resumo}_{data}`, onde `resumo` é derivado dos parâmetros de texto mais salientes — tipicamente o nome gravado — e o resto é sanitizado removendo acentos, trocando espaços por hífen e descartando caracteres inválidos em nome de arquivo no Windows. Colisão de nome nunca sobrescreve silenciosamente: um sufixo numérico é acrescentado.

Toda exportação é registrada no banco com produto, versão, parâmetros completos, caminho do arquivo e timestamp, o que torna possível reproduzir exatamente um pedido antigo meses depois. Essa é a funcionalidade que mais vai importar quando o cliente voltar pedindo outro igual.

---

## 10. Integração com o Bambu Studio

A integração tem três níveis, e os três devem existir, com degradação graciosa quando o nível mais alto não estiver disponível.

O nível básico é abrir o arquivo exportado no aplicativo padrão associado a 3MF, via `QDesktopServices.openUrl` sobre uma `QUrl.fromLocalFile`. Funciona sempre e não depende de encontrar binário nenhum.

O nível intermediário é localizar o executável do Bambu Studio e invocá-lo explicitamente com o caminho do arquivo como argumento, o que garante que abra no Bambu mesmo quando outro programa tomou a associação de 3MF. A localização tenta, em ordem, um caminho salvo nas configurações, depois os caminhos usuais de instalação no Windows em `Program Files` e no `LOCALAPPDATA`, depois a chave de registro do aplicativo, depois `PATH`, e no Linux tenta o AppImage nos diretórios comuns e o `flatpak run`. Falhando tudo, a Central pede o caminho ao operador uma única vez e salva.

O nível avançado é o fatiamento headless para obter estimativa de tempo e de consumo de filamento sem abrir a interface, invocando o executável em modo CLI com o perfil de máquina e de processo apropriados e lendo os metadados do G-code resultante ou dos dados de fatiamento exportados. Esse valor alimenta a precificação e é o que transforma a Central de gerador de arquivo em ferramenta de negócio. A ressalva honesta é que os flags de linha de comando do Bambu Studio mudam entre versões e não devem ser assumidos a partir de memória: a implementação deve rodar o executável com `--help`, registrar a saída, e adaptar-se ao que encontrar, além de degradar para "estimativa indisponível" sem erro visível quando o modo CLI não responder como esperado. O timeout de uma invocação headless é de cento e vinte segundos, ela roda em subprocesso separado com a saída capturada, e nunca bloqueia a interface.

Gerar um 3MF já com o projeto Bambu configurado — plate, perfil, suportes escolhidos — está explicitamente fora do escopo inicial. O formato de projeto do Bambu é uma extensão proprietária do 3MF e persegui-lo agora troca semanas de engenharia frágil por alguns cliques poupados.

---

## 11. Interface

A janela principal tem uma barra de título com abas de navegação entre Biblioteca, Editor, Lote, Catálogo e Configurações, e um console de desenvolvimento acessível por atalho que só aparece quando há erros de produto pendentes.

A **Biblioteca** é uma grade de cards com a miniatura renderizada, o nome comercial, a categoria e a versão, filtrável por categoria e por busca em texto livre sobre nome, descrição e tags. Um clique abre o produto no Editor com os valores padrão, e um clique com modificador abre a lista de presets salvos daquele produto para partir de um deles.

O **Editor** é a tela onde o tempo é gasto e tem três painéis. À esquerda, estreito e recolhível, a árvore de corpos do resultado atual com visibilidade alternável por corpo. Ao centro, a viewport. À direita, o inspetor de parâmetros, gerado inteiramente a partir da declaração e organizado nos grupos declarados, com os parâmetros marcados como avançados dentro de uma seção colapsada ao final. Abaixo de tudo, uma barra de status que mostra o estado da geração, o resultado da checagem de qualidade, os avisos devolvidos pelo produto, e as dimensões finais da peça em milímetros.

O mapeamento de tipo para widget é fixo e não deve ser configurável por produto, porque consistência vale mais que expressividade aqui. Texto vira campo de linha com contador de caracteres quando há `max_len`. Decimal com mínimo e máximo definidos vira slider acoplado a um spinbox que mostra o número exato, porque só o slider impede digitar um valor preciso e só o spinbox impede explorar. Decimal sem limites vira apenas spinbox. Inteiro vira spinbox. Booleano vira switch. Escolha vira combo, ou um grupo de botões segmentados quando há três opções ou menos. Cor vira um botão que abre o seletor nativo. A unidade aparece como sufixo dentro do campo, nunca no rótulo.

Campos com `visivel_se` aparecem e somem com animação curta em vez de salto abrupto, e o inspetor reavalia todas as condições a cada mudança de valor. Um campo escondido mantém seu valor e continua sendo passado a `gerar`.

A barra de ferramentas superior do Editor concentra as ações: exportar, abrir no Bambu Studio, salvar preset, restaurar padrões, duplicar para o Lote. O atalho de exportar é o esperado do sistema, e abrir no Bambu tem atalho próprio, porque essa sequência será repetida centenas de vezes.

O estado de geração precisa ser legível sem esforço. Enquanto o worker trabalha, a peça anterior permanece visível com opacidade levemente reduzida e um indicador discreto de progresso aparece no canto da viewport — nunca um spinner que cobre a tela, nunca a viewport ficando vazia. Erro de geração substitui a viewport por um painel com a mensagem e o traceback copiável, mantendo o inspetor funcional para que o operador corrija o valor e tente de novo.

A aparência deve seguir tema escuro por padrão com respeito à preferência do sistema, tipografia de interface do próprio sistema operacional em vez de fonte embutida, e densidade média — nem apertado como CAD profissional, nem espaçado como aplicativo web. A cor de destaque é usada com parcimônia, reservada para o estado ativo e para o botão primário de cada tela.

---

## 12. Lote

O Lote é a funcionalidade que paga o desenvolvimento da Central, porque encomenda personalizada é onde a impressão 3D vende e fazer quarenta arquivos na mão é o gargalo real.

A tela recebe um CSV cuja primeira linha traz as chaves dos parâmetros e cada linha seguinte descreve uma unidade. Colunas ausentes assumem o padrão do produto, e colunas desconhecidas geram aviso sem impedir. Antes de gerar coisa alguma, a Central valida todas as linhas e mostra uma pré-visualização tabular com as inválidas destacadas e a razão da recusa em cada célula culpada, permitindo corrigir ali mesmo ou remover a linha. Só então o botão de executar habilita.

A execução roda num pool de processos com número de trabalhadores igual ao total de núcleos menos um, porque cada geração é CPU-bound e o OCCT não paraleliza internamente. O progresso é por item, com contagem de sucessos e falhas, e uma falha isolada nunca aborta o lote — ela é registrada e o relatório final lista o que não saiu e por quê. A checagem de qualidade roda em cada item.

Além dos arquivos individuais, o Lote oferece o arranjo automático em placa: as peças são dispostas numa grade sobre a área útil de 256 por 256 milímetros com espaçamento configurável de padrão cinco milímetros, e quando não cabem todas, o conjunto é dividido em placas sucessivas exportadas como arquivos numerados. O empacotamento é em grade simples baseada no maior bounding box do lote, não em nesting real por contorno; nesting verdadeiro é um problema difícil cujo ganho não compensa neste estágio, e a grade já resolve o caso dominante de peças de tamanho parecido.

---

## 13. Catálogo e precificação

O banco é um único arquivo SQLite no diretório de dados do aplicativo, acessado pela biblioteca padrão sem ORM, com as instruções SQL concentradas num módulo só e as migrações versionadas por número de esquema aplicadas na inicialização.

Guarda presets, que são um nome dado a um conjunto de valores de um produto e formam o catálogo de coisas que você realmente vende. Guarda o histórico de exportações, que permite reproduzir qualquer pedido antigo. Guarda os lotes executados com seus parâmetros e resultados. E guarda os dados de precificação: custo do filamento por quilo por tipo de material, custo-hora atribuído à máquina, percentual de falha esperado, e margem desejada.

O preço sugerido de uma peça sai da estimativa do fatiamento headless multiplicando gramas pelo custo do material, somando horas pelo custo-hora, aplicando o acréscimo de risco de falha e a margem. Quando a estimativa headless não está disponível, o preço aparece como indisponível em vez de um chute, porque um número inventado nesse campo é pior que a ausência dele.

---

## 14. Estrutura de diretórios

```
central-3d/
  pyproject.toml
  CENTRAL.md            este documento
  CONTRATO.md           extrato do contrato, para o Claude Code ler
  central/
    __init__.py
    app.py              ponto de entrada
    contrato/           Param, Produto, Corpo, Resultado — sem dependências
    nucleo/
      registro.py       descoberta e hot-reload
      validacao.py
      geracao.py        pipeline, worker, cancelamento
      cache.py
      tesselagem.py
      qualidade.py
      exportacao.py
      helpers.py        texto_solido memoizado e utilitários de geometria
    servicos/
      bambu.py
      banco.py
      config.py
      lote.py
      preco.py
    ui/
      janela.py
      biblioteca.py
      editor.py
      inspetor.py       geração de widgets a partir de Param
      viewport.py       wrapper do VTK
      lote.py
      catalogo.py
      configuracoes.py
      tema.py
  produtos/
    _template/          esqueleto copiado por novo_produto.py
    porta_lapis_nome/
  scripts/
    novo_produto.py
  tests/
```

---

## 15. Testes

O núcleo é testado sem interface. A validação de parâmetros ganha testes parametrizados cobrindo os limites de cada tipo. O cache é testado quanto a determinismo da chave, invalidação por mudança de versão e indiferença a parâmetros marcados como não afetando geometria. A exportação é testada gerando um sólido trivial e verificando que o arquivo resultante recarrega com o volume esperado.

Cada produto ganha um teste automático fornecido pela Central e não escrito à mão: uma fixture parametrizada que descobre todos os produtos, gera cada um com os valores padrão, e afirma que o resultado é estanque, tem volume positivo e cabe no volume de construção. Esse teste único é o que impede regressão silenciosa quando um produto é editado, e é barato justamente porque o contrato garante que todos os produtos são chamáveis da mesma forma.

A interface ganha testes de fumaça com `pytest-qt` confirmando que a janela abre, que a biblioteca lista os produtos descobertos e que abrir um produto no editor não lança exceção. Não vale a pena ir além disso em cobertura de UI.

---

## 16. Empacotamento

Empacotar é a parte desagradável e deve ficar para depois de o app estar funcionando. A dependência OCP carrega o OpenCASCADE inteiro e passa facilmente de setecentos megabytes, e o VTK acrescenta outro tanto, o que torna um instalador único grande e o PyInstaller propenso a perder bibliotecas dinâmicas do OCCT em modo `--onefile`. A recomendação é rodar direto do fonte com `uv run` durante todo o desenvolvimento e durante o uso pessoal, e só investir em empacotamento se a Central for distribuída para alguém que não vá rodar Python. Se esse dia chegar, PyInstaller em modo diretório, com os binários do OCCT declarados explicitamente, é o caminho menos doloroso.

---

## 17. Ordem de construção

A primeira entrega é o contrato completo, o registro de descoberta, um produto de teste que devolve um cubo com um texto em relevo, e um script de linha de comando que gera e exporta esse produto. Sem interface nenhuma. Se essa camada estiver certa, o resto é montagem.

A segunda entrega acrescenta a janela, a biblioteca, a viewport com a mesa, e o editor com o inspetor gerado a partir dos parâmetros, ainda sem cache nem threading — geração síncrona, aceitando o travamento momentâneo.

A terceira entrega torna a geração assíncrona com worker, cancelamento, debounce e cache, e adiciona a tesselagem em dois níveis. É aqui que o app deixa de parecer protótipo.

A quarta entrega traz o portão de qualidade, a exportação em 3MF com orientação e nomenclatura, e a abertura no Bambu Studio nos níveis básico e intermediário.

A quinta traz o Lote com CSV, pool de processos e arranjo em placa. A sexta traz o banco, os presets, o histórico, o fatiamento headless e a precificação. A sétima é polimento: plano de corte, cubo de orientação, miniaturas, tema, atalhos.

---

## 18. Convenções não negociáveis

Nenhum caminho absoluto aparece em código, tudo passa por `pathlib.Path` resolvido a partir do diretório do aplicativo ou do diretório de dados do usuário. Toda leitura e escrita de texto declara `encoding="utf-8"` explicitamente. Toda função pública tem anotação de tipo completa e docstring no estilo Google. Nenhum `except` nu existe no projeto; erros são capturados por tipo específico e sempre registrados via `logging`, nunca via `print`. Erro dentro de um produto jamais derruba a Central, jamais aborta um lote inteiro, e sempre chega ao operador com traceback legível. Nenhum widget contém regra de negócio. Nenhum módulo de produto importa qualquer coisa fora de `central.contrato` e das bibliotecas de geometria.

---

## 19. Pontos que exigem verificação durante a implementação

Alguns detalhes deste documento derivam de conhecimento que envelhece e devem ser confirmados contra a realidade antes de virar código. A API exata da classe `Mesher` do build123d para escrita de 3MF com múltiplos objetos precisa ser conferida na documentação da versão instalada. Os flags de linha de comando do Bambu Studio para fatiamento headless mudam entre versões e devem ser descobertos rodando o executável com `--help` e registrando a saída. A disponibilidade e o nome do módulo `QVTKRenderWindowInteractor` dentro de `vtkmodules` variam conforme a build do VTK instalada. E os valores de desvio de tesselagem sugeridos aqui são pontos de partida razoáveis, não medidas: eles devem ser calibrados olhando o resultado real na viewport e no arquivo exportado.
