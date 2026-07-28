"""Escrita dos arquivos de saída.

O 3MF é escrito chamando o `lib3mf` **diretamente**, a partir da mesma malha
que o portão de qualidade valida. A classe `Mesher` do build123d não serve
aqui: ela faz `deepcopy` da forma e remalha incondicionalmente, com desvio
relativo ao tamanho da aresta, de modo que a malha gravada nunca seria a malha
aprovada. Ver a emenda da seção 9 do CENTRAL.md e `docs/NOTAS_VERIFICACAO.md`.

O que vai para o arquivo é o nome de cada corpo, como atributo `name` do
`<object>`, e a cor, como `<basematerials>` com `displaycolor`. O campo
`Corpo.filamento` não é gravável em 3MF genérico.
"""

from __future__ import annotations

import ctypes
from enum import StrEnum
from pathlib import Path

import trimesh
from lib3mf import Lib3MF, Wrapper  # type: ignore[import-untyped]

from central.contrato import Corpo
from central.log import obter
from central.nucleo.erros import ErroDeExportacao
from central.nucleo.geracao import ResultadoGeracao
from central.nucleo.tesselagem import NivelTesselagem

_log = obter(__name__)

_TRINCA_FLOAT = ctypes.c_float * 3
_TRINCA_UINT = ctypes.c_uint * 3

COR_PADRAO = "#8AB4F8"
"""Cor usada quando a do corpo não é hexadecimal reconhecível."""


class Formato(StrEnum):
    """Formatos de saída disponíveis.

    O 3MF é o padrão porque carrega unidades explicitamente, suporta múltiplos
    objetos nomeados num mesmo arquivo e é o formato nativo do ecossistema
    Bambu. Ver a seção 9 do CENTRAL.md.
    """

    TRES_MF = "3mf"
    STL = "stl"

    @property
    def sufixo(self) -> str:
        """Extensão de arquivo, com ponto."""
        return f".{self.value}"


def _componentes_rgb(cor: str) -> tuple[int, int, int]:
    """Converte `#RRGGBB` ou `#RGB` em três inteiros de 0 a 255."""
    texto = cor.lstrip("#")
    if len(texto) == 3:
        texto = "".join(caractere * 2 for caractere in texto)
    if len(texto) not in (6, 8):
        _log.warning("cor %r não é hexadecimal; usando %s", cor, COR_PADRAO)
        return _componentes_rgb(COR_PADRAO)
    try:
        return (
            int(texto[0:2], 16),
            int(texto[2:4], 16),
            int(texto[4:6], 16),
        )
    except ValueError:
        _log.warning("cor %r não é hexadecimal; usando %s", cor, COR_PADRAO)
        return _componentes_rgb(COR_PADRAO)


def escrever_3mf(
    malhas: dict[str, trimesh.Trimesh],
    corpos: list[Corpo],
    caminho: Path,
) -> Path:
    """Escreve um 3MF com um objeto nomeado por corpo.

    Args:
        malhas: Malha de cada corpo, indexada pelo nome do corpo.
        corpos: Os corpos, na ordem em que devem aparecer no arquivo.
        caminho: Arquivo a escrever. O diretório é criado se não existir.

    Returns:
        O caminho escrito.

    Raises:
        ErroDeExportacao: Se algum corpo não tem malha, se uma malha resulta
            inválida para o lib3mf, ou se a escrita falha.
    """
    if not corpos:
        raise ErroDeExportacao("não há corpo nenhum para exportar")

    embrulho = Wrapper()
    modelo = embrulho.CreateModel()
    modelo.SetUnit(Lib3MF.ModelUnit.MilliMeter)
    grupo = modelo.AddBaseMaterialGroup()

    for corpo in corpos:
        malha = malhas.get(corpo.nome)
        if malha is None:
            raise ErroDeExportacao(f"o corpo '{corpo.nome}' não tem malha")

        objeto = modelo.AddMeshObject()
        objeto.SetName(corpo.nome)
        objeto.SetGeometry(
            [Lib3MF.Position(_TRINCA_FLOAT(*ponto)) for ponto in malha.vertices],
            [Lib3MF.Triangle(_TRINCA_UINT(*face)) for face in malha.faces],
        )

        vermelho, verde, azul = _componentes_rgb(corpo.cor)
        indice = grupo.AddMaterial(
            corpo.nome, embrulho.RGBAToColor(vermelho, verde, azul, 255)
        )
        objeto.SetObjectLevelProperty(grupo.GetResourceID(), indice)

        if not objeto.IsValid():
            raise ErroDeExportacao(f"a malha do corpo '{corpo.nome}' é inválida")
        if not objeto.IsManifoldAndOriented():
            _log.warning("corpo '%s' não é manifold para o lib3mf", corpo.nome)

        modelo.AddBuildItem(objeto, embrulho.GetIdentityTransform())

    caminho.parent.mkdir(parents=True, exist_ok=True)
    try:
        modelo.QueryWriter("3mf").WriteToFile(str(caminho))
    except OSError as erro:
        raise ErroDeExportacao(f"não foi possível escrever {caminho}: {erro}") from erro

    _log.info(
        "3MF escrito em %s: %d objeto(s), %d triângulo(s)",
        caminho,
        len(corpos),
        sum(len(malhas[c.nome].faces) for c in corpos),
    )
    return caminho


def escrever_stl(
    malhas: dict[str, trimesh.Trimesh],
    corpos: list[Corpo],
    caminho: Path,
) -> Path:
    """Escreve um STL com todos os corpos fundidos.

    O STL não tem noção de objeto nomeado nem de cor, então os corpos viram uma
    malha só. É a alternativa de compatibilidade, não o formato padrão.

    Args:
        malhas: Malha de cada corpo, indexada pelo nome do corpo.
        corpos: Os corpos a incluir.
        caminho: Arquivo a escrever.

    Returns:
        O caminho escrito.

    Raises:
        ErroDeExportacao: Se algum corpo não tem malha ou se a escrita falha.
    """
    if not corpos:
        raise ErroDeExportacao("não há corpo nenhum para exportar")

    faltantes = [c.nome for c in corpos if c.nome not in malhas]
    if faltantes:
        raise ErroDeExportacao(f"corpos sem malha: {', '.join(faltantes)}")

    fundida = trimesh.util.concatenate([malhas[c.nome] for c in corpos])

    caminho.parent.mkdir(parents=True, exist_ok=True)
    try:
        caminho.write_bytes(fundida.export(file_type="stl"))
    except OSError as erro:
        raise ErroDeExportacao(f"não foi possível escrever {caminho}: {erro}") from erro

    _log.info("STL escrito em %s: %d triângulo(s)", caminho, len(fundida.faces))
    return caminho


def exportar(
    geracao: ResultadoGeracao,
    caminho: Path,
    formato: Formato = Formato.TRES_MF,
) -> Path:
    """Escreve o resultado de uma geração no formato pedido.

    Args:
        geracao: Resultado de `gerar_sincrono`, que precisa ter sido tesselado
            no nível de exportação.
        caminho: Arquivo a escrever, com ou sem extensão. A extensão do formato
            é acrescentada quando ausente.
        formato: Formato de saída.

    Returns:
        O caminho efetivamente escrito.

    Raises:
        ErroDeExportacao: Se a geração não está no nível de exportação ou se a
            escrita falha.
    """
    if geracao.nivel is not NivelTesselagem.EXPORTACAO:
        raise ErroDeExportacao(
            f"a geração está no nível {geracao.nivel} e exportar exige "
            f"{NivelTesselagem.EXPORTACAO}"
        )

    destino = caminho if caminho.suffix else caminho.with_suffix(formato.sufixo)
    corpos = geracao.resultado.corpos

    if formato is Formato.TRES_MF:
        return escrever_3mf(geracao.malhas, corpos, destino)
    return escrever_stl(geracao.malhas, corpos, destino)
