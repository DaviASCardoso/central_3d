"""Linha de comando da Central.

Gera e exporta um produto sem abrir interface nenhuma. Este é o caminho que
prova que a camada de valor não depende de Qt: se este módulo precisar importar
widget, a arquitetura da seção 3 do CENTRAL.md foi violada.

Esta é a única camada autorizada a escrever na saída padrão. Todo o resto usa
`logging`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from central import __version__, log
from central.contrato import Produto, TipoParam
from central.nucleo import Registro, descobrir
from central.nucleo.erros import ErroCentral, ErroDeValidacao
from central.nucleo.exportacao import Formato, exportar
from central.nucleo.geracao import gerar_sincrono
from central.nucleo.impressora import VOLUME_DE_CONSTRUCAO
from central.nucleo.tesselagem import NivelTesselagem
from central.nucleo.validacao import validar

_log = log.obter(__name__)

CODIGO_OK = 0
CODIGO_ERRO = 1
CODIGO_VALORES_INVALIDOS = 2

SAIDA_PADRAO = Path("saidas")
"""Diretório de saída relativo ao diretório de trabalho corrente."""

CHAVES_RESERVADAS = frozenset(
    {"saida", "formato", "nome_do_arquivo", "verboso", "versao", "help"}
)
"""Chaves de parâmetro que a linha de comando não consegue repassar ao produto.

Elas colidem com as opções da própria CLI. Um produto que declare uma delas
continua funcionando na interface gráfica; só não é gerável por aqui, e o
comando diz isso em vez de usar o valor errado em silêncio.
"""


def _montar_analisador() -> argparse.ArgumentParser:
    """Monta o analisador de argumentos com os dois subcomandos."""
    # allow_abbrev=False é obrigatório: com a abreviação ligada, um parâmetro
    # de produto chamado `nome` casaria com `--nome-do-arquivo` da própria CLI
    # e o valor iria para o lugar errado sem nenhum aviso.
    analisador = argparse.ArgumentParser(
        prog="central-cli",
        description="Gera e exporta produtos da Central pela linha de comando.",
        allow_abbrev=False,
    )
    analisador.add_argument("--versao", action="version", version=f"central {__version__}")
    analisador.add_argument(
        "--verboso",
        action="store_true",
        help="mostra o log de depuração do núcleo",
    )

    sub = analisador.add_subparsers(dest="comando", required=True)

    # allow_abbrev não se propaga do analisador principal para os subparsers,
    # e é justamente no subcomando `gerar` que moram as opções que colidiriam.
    listar = sub.add_parser(
        "listar", help="lista os produtos descobertos", allow_abbrev=False
    )
    listar.add_argument(
        "--detalhado",
        action="store_true",
        help="mostra também os parâmetros de cada produto",
    )

    gerar = sub.add_parser(
        "gerar",
        help="gera um produto e escreve o arquivo",
        allow_abbrev=False,
        epilog=(
            "Os parâmetros do produto viram opções longas: um produto com o "
            "parâmetro 'nome' aceita --nome. Use 'listar --detalhado' para ver "
            "quais existem."
        ),
    )
    gerar.add_argument("id", help="identificador do produto, como aparece em listar")
    gerar.add_argument(
        "--saida",
        type=Path,
        default=SAIDA_PADRAO,
        help=f"diretório onde escrever o arquivo (padrão: {SAIDA_PADRAO})",
    )
    gerar.add_argument(
        "--formato",
        choices=[f.value for f in Formato],
        default=Formato.TRES_MF.value,
        help="formato de saída (padrão: 3mf)",
    )
    gerar.add_argument(
        "--nome-do-arquivo",
        default=None,
        help="nome do arquivo sem extensão (padrão: o id do produto)",
    )
    return analisador


def _comando_listar(registro: Registro, detalhado: bool) -> int:
    """Imprime os produtos descobertos e os que falharam ao carregar."""
    if not registro.produtos and not registro.falhas:
        print(f"nenhum produto em {registro.diretorio}")
        return CODIGO_OK

    for produto in registro.ordenados():
        print(f"{produto.id}")
        print(f"    {produto.nome} — {produto.categoria} — v{produto.versao}")
        if produto.descricao:
            print(f"    {produto.descricao}")
        if detalhado:
            for param in sorted(produto.params, key=lambda p: (p.grupo, p.ordem)):
                print(f"      --{param.chave.replace('_', '-')}  {_descrever(param)}")
        print()

    if registro.falhas:
        print(f"{len(registro.falhas)} produto(s) com falha:")
        for falha in registro.falhas.values():
            print(f"    {falha.id}: {falha.mensagem}")

    return CODIGO_OK


def _descrever(param: Any) -> str:
    """Monta a linha de ajuda de um parâmetro para o modo detalhado."""
    partes = [f"{param.tipo}", f"padrão {param.padrao!r}"]
    if param.minimo is not None or param.maximo is not None:
        partes.append(f"de {param.minimo} a {param.maximo}")
    if param.opcoes:
        partes.append(f"opções: {', '.join(param.opcoes)}")
    if param.max_len is not None:
        partes.append(f"até {param.max_len} caracteres")
    if param.unidade:
        partes.append(param.unidade)
    return "  ".join(partes)


def _coletar_valores(produto: Produto, extras: list[str]) -> dict[str, Any]:
    """Lê os parâmetros do produto a partir dos argumentos não reconhecidos.

    Cada `Param` vira uma opção longa com hífens no lugar dos sublinhados.
    Booleanos aceitam tanto `--avancado` sozinho quanto `--avancado false`.

    Args:
        produto: O manifesto, que declara quais opções existem.
        extras: Os argumentos que o analisador principal não reconheceu.

    Returns:
        Os valores crus indexados pela chave do parâmetro.

    Raises:
        SystemExit: Se um argumento desconhecido foi passado.
    """
    analisador = argparse.ArgumentParser(
        prog=f"central-cli gerar {produto.id}", allow_abbrev=False
    )
    for param in produto.params:
        opcao = f"--{param.chave.replace('_', '-')}"
        if param.tipo is TipoParam.BOOLEANO:
            analisador.add_argument(opcao, nargs="?", const="true", default=None)
        else:
            analisador.add_argument(opcao, default=None)

    analisado = vars(analisador.parse_args(extras))
    return {
        param.chave: analisado[param.chave]
        for param in produto.params
        if analisado.get(param.chave) is not None
    }


def _comando_gerar(registro: Registro, argumentos: argparse.Namespace, extras: list[str]) -> int:
    """Gera o produto pedido e escreve o arquivo."""
    if argumentos.id not in registro:
        print(f"produto '{argumentos.id}' não existe", file=sys.stderr)
        if argumentos.id in registro.falhas:
            print(
                f"ele foi encontrado mas falhou ao carregar: "
                f"{registro.falhas[argumentos.id].mensagem}",
                file=sys.stderr,
            )
        else:
            print(f"disponíveis: {', '.join(sorted(registro.produtos))}", file=sys.stderr)
        return CODIGO_ERRO

    produto = registro.obter(argumentos.id)

    colididas = sorted(CHAVES_RESERVADAS.intersection(p.chave for p in produto.params))
    if colididas:
        print(
            f"o produto '{produto.id}' declara parâmetro(s) cujo nome a linha de "
            f"comando reserva para si: {', '.join(colididas)}. Gere-o pela "
            "interface gráfica.",
            file=sys.stderr,
        )
        return CODIGO_ERRO

    valores = _coletar_valores(produto, extras)

    validacao = validar(produto, valores)
    if not validacao.valido:
        print(f"valores inválidos para '{produto.id}':", file=sys.stderr)
        for mensagem in validacao.mensagens():
            print(f"    {mensagem}", file=sys.stderr)
        return CODIGO_VALORES_INVALIDOS

    try:
        geracao = gerar_sincrono(produto, valores, NivelTesselagem.EXPORTACAO)
    except ErroDeValidacao as erro:
        print(f"valores inválidos: {erro}", file=sys.stderr)
        return CODIGO_VALORES_INVALIDOS
    except ErroCentral as erro:
        print(f"falha ao gerar: {erro}", file=sys.stderr)
        _log.exception("falha ao gerar o produto '%s'", produto.id)
        return CODIGO_ERRO

    for aviso in geracao.avisos:
        print(f"aviso: {aviso}", file=sys.stderr)

    if not VOLUME_DE_CONSTRUCAO.cabe(geracao.dimensoes):
        largura, profundidade, altura = geracao.dimensoes
        print(
            f"a peça mede {largura:.1f} × {profundidade:.1f} × {altura:.1f} mm e não "
            f"cabe no volume de {VOLUME_DE_CONSTRUCAO.x:.0f} × "
            f"{VOLUME_DE_CONSTRUCAO.y:.0f} × {VOLUME_DE_CONSTRUCAO.z:.0f} mm",
            file=sys.stderr,
        )
        return CODIGO_ERRO

    formato = Formato(argumentos.formato)
    nome = argumentos.nome_do_arquivo or produto.id
    destino = argumentos.saida / f"{nome}{formato.sufixo}"

    try:
        escrito = exportar(geracao, destino, formato)
    except ErroCentral as erro:
        print(f"falha ao exportar: {erro}", file=sys.stderr)
        return CODIGO_ERRO

    largura, profundidade, altura = geracao.dimensoes
    triangulos = sum(len(malha.faces) for malha in geracao.malhas.values())
    print(f"{escrito}")
    print(f"    {len(geracao.resultado.corpos)} corpo(s), {triangulos} triângulos")
    print(f"    {largura:.1f} × {profundidade:.1f} × {altura:.1f} mm")
    return CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    """Ponto de entrada da linha de comando.

    Args:
        argv: Argumentos, sem o nome do programa. Por padrão, `sys.argv[1:]`.

    Returns:
        O código de saída: 0 em sucesso, 2 para valores inválidos, 1 no resto.
    """
    analisador = _montar_analisador()
    argumentos, extras = analisador.parse_known_args(argv)

    log.configurar(logging.DEBUG if argumentos.verboso else logging.WARNING)

    try:
        registro = descobrir()
    except ErroCentral as erro:
        print(f"falha ao descobrir produtos: {erro}", file=sys.stderr)
        return CODIGO_ERRO

    if argumentos.comando == "listar":
        if extras:
            analisador.error(f"argumentos não reconhecidos: {' '.join(extras)}")
        return _comando_listar(registro, argumentos.detalhado)

    return _comando_gerar(registro, argumentos, extras)


if __name__ == "__main__":
    sys.exit(principal())
