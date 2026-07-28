"""Contrato entre a Central e os módulos de produto.

Esta é a camada da base: não importa nada do resto do sistema, não conhece Qt,
não conhece VTK, não conhece build123d, e pode ser importada por um script de
linha de comando sem carregar interface nenhuma. Os módulos de produto dependem
apenas dela.

A regra que sustenta o projeto inteiro: o produto devolve geometria e nada
mais. Ele não escreve arquivos, não conhece o Bambu Studio, não sabe o que é
uma janela, não lê configuração, não imprime log. Se um produto precisar fazer
qualquer uma dessas coisas, o contrato está incompleto e é o contrato que deve
mudar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TipoParam(StrEnum):
    """Tipo de um parâmetro, que determina o widget e a coerção de valor."""

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


@dataclass(slots=True)
class Corpo:
    """Um sólido nomeado dentro do resultado de um produto.

    Attributes:
        nome: Identificador curto, usado no nome do arquivo quando exportado
            separadamente e como rótulo na árvore da viewport.
        forma: O sólido em si (build123d Part ou Compound).
        cor: Cor de exibição em hexadecimal. Não afeta a impressão.
        filamento: Índice de filamento sugerido para AMS, ou None. Não é
            gravado no 3MF — atribuição de AMS é extensão proprietária do
            Bambu, fora do escopo. Ver a emenda da seção 9 do CENTRAL.md.
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
        params: Declaração completa dos parâmetros.
        gerar: A função de geometria.
        tags: Termos de busca livres.
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
