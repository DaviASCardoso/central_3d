"""Descoberta dos módulos de produto.

A varredura importa cada pacote de `produtos/` isoladamente. Um produto que
falha ao importar não derruba os outros nem o aplicativo: ele vira um
`ProdutoComFalha` com o traceback preservado, para aparecer na biblioteca como
um card vermelho. Ver a seção 5 do CENTRAL.md.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from central.contrato import Produto
from central.log import obter
from central.nucleo.erros import ErroDeDescoberta

_log = obter(__name__)

NOME_MANIFESTO = "MANIFESTO"
"""Nome da variável de módulo que cada produto expõe."""

DIRETORIO_PADRAO = Path(__file__).resolve().parent.parent.parent / "produtos"
"""Diretório de produtos do repositório, resolvido a partir deste arquivo."""


@dataclass(frozen=True, slots=True)
class ProdutoComFalha:
    """Um pacote de produto que não pôde ser carregado.

    Attributes:
        id: Nome do pacote, usado como identificador na ausência de manifesto.
        caminho: Caminho do pacote em disco.
        mensagem: Resumo de uma linha, adequado para o card da biblioteca.
        traceback_completo: Traceback formatado, exibido sob um clique.
    """

    id: str
    caminho: Path
    mensagem: str
    traceback_completo: str


@dataclass(slots=True)
class Registro:
    """Resultado de uma varredura do diretório de produtos.

    Attributes:
        produtos: Manifestos válidos, indexados por `id`.
        falhas: Pacotes que não carregaram, indexados por nome de pacote.
        diretorio: Diretório varrido.
    """

    diretorio: Path
    produtos: dict[str, Produto] = field(default_factory=dict)
    falhas: dict[str, ProdutoComFalha] = field(default_factory=dict)

    def __len__(self) -> int:
        """Quantidade de produtos válidos."""
        return len(self.produtos)

    def __contains__(self, id_produto: object) -> bool:
        """Diz se um `id` de produto está registrado."""
        return id_produto in self.produtos

    def obter(self, id_produto: str) -> Produto:
        """Devolve um manifesto pelo `id`.

        Args:
            id_produto: Identificador declarado no manifesto.

        Returns:
            O manifesto correspondente.

        Raises:
            KeyError: Se nenhum produto válido tem esse `id`.
        """
        return self.produtos[id_produto]

    def ordenados(self) -> list[Produto]:
        """Devolve os manifestos ordenados por categoria e depois por nome."""
        return sorted(self.produtos.values(), key=lambda p: (p.categoria, p.nome))

    def categorias(self) -> list[str]:
        """Devolve as categorias distintas presentes, em ordem alfabética."""
        return sorted({p.categoria for p in self.produtos.values()})


def _preparar_import(diretorio: Path) -> str:
    """Torna o diretório de produtos importável e devolve o nome do pacote.

    O diretório é tratado como um pacote comum: seu pai entra no `sys.path` e
    os produtos passam a ser importáveis por nome pontuado. Isso mantém os
    imports relativos dentro do produto funcionando e permite `importlib.reload`
    no recarregamento a quente.

    Args:
        diretorio: Diretório que contém um pacote por produto.

    Returns:
        Nome do pacote que representa o diretório.

    Raises:
        ErroDeDescoberta: Se o diretório não existe ou não é um pacote Python.
    """
    if not diretorio.is_dir():
        raise ErroDeDescoberta(f"diretório de produtos inexistente: {diretorio}")
    if not (diretorio / "__init__.py").is_file():
        raise ErroDeDescoberta(f"diretório de produtos sem __init__.py: {diretorio}")

    pai = str(diretorio.parent)
    if pai not in sys.path:
        sys.path.insert(0, pai)
    return diretorio.name


def _carregar(nome_completo: str) -> Produto:
    """Importa um pacote de produto e extrai seu manifesto.

    Args:
        nome_completo: Nome pontuado do pacote, como `produtos.placa_nome`.

    Returns:
        O manifesto declarado pelo pacote.

    Raises:
        ErroDeDescoberta: Se o pacote não expõe `MANIFESTO` ou se o que ele
            expõe não é um `Produto`.
    """
    modulo = importlib.import_module(nome_completo)
    manifesto = getattr(modulo, NOME_MANIFESTO, None)
    if manifesto is None:
        raise ErroDeDescoberta(f"o pacote não expõe a variável {NOME_MANIFESTO}")
    if not isinstance(manifesto, Produto):
        raise ErroDeDescoberta(
            f"{NOME_MANIFESTO} é {type(manifesto).__name__}, deveria ser Produto"
        )
    return manifesto


def descobrir(diretorio: Path | None = None) -> Registro:
    """Varre o diretório de produtos e monta o registro em memória.

    Cada pacote é importado dentro de um `try` que captura `Exception`, de modo
    que um produto quebrado não impeça os demais de aparecerem. Pacotes cujo
    nome começa com sublinhado são ignorados, o que é como `_template` fica
    fora da biblioteca.

    Args:
        diretorio: Diretório a varrer. Por padrão, `produtos/` do repositório.

    Returns:
        O registro com os manifestos válidos e as falhas.

    Raises:
        ErroDeDescoberta: Se o próprio diretório não pode ser varrido.
    """
    alvo = (diretorio or DIRETORIO_PADRAO).resolve()
    pacote = _preparar_import(alvo)
    registro = Registro(diretorio=alvo)

    for info in pkgutil.iter_modules([str(alvo)]):
        if info.name.startswith("_"):
            _log.debug("ignorando %s: nome começa com sublinhado", info.name)
            continue

        nome_completo = f"{pacote}.{info.name}"
        try:
            manifesto = _carregar(nome_completo)
        except Exception as erro:  # noqa: BLE001 -- seção 5: falha isolada
            _log.warning("produto %s falhou ao carregar: %s", info.name, erro)
            registro.falhas[info.name] = ProdutoComFalha(
                id=info.name,
                caminho=alvo / info.name,
                mensagem=f"{type(erro).__name__}: {erro}",
                traceback_completo=traceback.format_exc(),
            )
            continue

        if manifesto.id in registro.produtos:
            anterior = registro.produtos[manifesto.id]
            mensagem = f"id '{manifesto.id}' já usado pelo produto '{anterior.nome}'"
            _log.warning("produto %s ignorado: %s", info.name, mensagem)
            registro.falhas[info.name] = ProdutoComFalha(
                id=info.name,
                caminho=alvo / info.name,
                mensagem=mensagem,
                traceback_completo="",
            )
            continue

        registro.produtos[manifesto.id] = manifesto
        _log.debug("produto %s carregado como '%s'", info.name, manifesto.id)

    _log.info(
        "descoberta em %s: %d produto(s), %d falha(s)",
        alvo,
        len(registro.produtos),
        len(registro.falhas),
    )
    return registro
