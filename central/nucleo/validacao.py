"""Validação dos valores de parâmetros, em duas etapas.

A primeira etapa olha cada `Param` isoladamente: tipo, faixa, comprimento,
regex e pertinência ao conjunto de opções. A segunda chama o `validar` do
manifesto, que enxerga todos os valores juntos e conhece a física da peça.

Nenhum produto deve validar o que couber na declaração de `Param`, e a função
`gerar` pode assumir que tipos e faixas declaradas foram respeitados. Ver as
seções 4 e 6 do CENTRAL.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from central.contrato import Param, Produto, TipoParam
from central.log import obter

_log = obter(__name__)

CHAVE_CRUZADA = "__cruzada__"
"""Chave sob a qual ficam os erros devolvidos pelo `validar` do manifesto."""

_HEXADECIMAL = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")

_VERDADEIROS = frozenset({"true", "1", "sim", "verdadeiro", "on"})
_FALSOS = frozenset({"false", "0", "nao", "não", "falso", "off"})


class ValorInvalido(ValueError):
    """Um valor não satisfaz a declaração do seu `Param`."""


@dataclass(slots=True)
class ResultadoValidacao:
    """O que a validação devolve.

    Attributes:
        valores: Valores coeridos e completados com os padrões. Só é confiável
            quando `valido` é verdadeiro.
        erros: Mensagens de erro indexadas pela chave do parâmetro culpado. Os
            erros do `validar` do manifesto ficam sob `CHAVE_CRUZADA`.
    """

    valores: dict[str, Any] = field(default_factory=dict)
    erros: dict[str, list[str]] = field(default_factory=dict)

    @property
    def valido(self) -> bool:
        """Diz se nenhum erro foi encontrado."""
        return not self.erros

    def mensagens(self) -> list[str]:
        """Achata os erros numa lista legível, prefixada pela chave."""
        achatadas: list[str] = []
        for chave, lista in self.erros.items():
            prefixo = "" if chave == CHAVE_CRUZADA else f"{chave}: "
            achatadas.extend(f"{prefixo}{mensagem}" for mensagem in lista)
        return achatadas


def _coagir_texto(param: Param, valor: Any) -> str:
    if not isinstance(valor, str):
        raise ValorInvalido(f"esperava texto, recebeu {type(valor).__name__}")
    if param.max_len is not None and len(valor) > param.max_len:
        raise ValorInvalido(
            f"tem {len(valor)} caracteres, o máximo é {param.max_len}"
        )
    if param.padrao_regex is not None and re.fullmatch(param.padrao_regex, valor) is None:
        raise ValorInvalido(f"não satisfaz o padrão {param.padrao_regex!r} por inteiro")
    return valor


def _coagir_inteiro(param: Param, valor: Any) -> int:
    if isinstance(valor, bool):
        raise ValorInvalido("esperava inteiro, recebeu booleano")
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, float) and valor.is_integer():
        numero = int(valor)
    elif isinstance(valor, str):
        try:
            numero = int(valor.strip())
        except ValueError as erro:
            raise ValorInvalido(f"{valor!r} não é um inteiro") from erro
    else:
        raise ValorInvalido(f"esperava inteiro, recebeu {type(valor).__name__}")
    _conferir_faixa(param, numero)
    return numero


def _coagir_decimal(param: Param, valor: Any) -> float:
    if isinstance(valor, bool):
        raise ValorInvalido("esperava número, recebeu booleano")
    if isinstance(valor, (int, float)):
        numero = float(valor)
    elif isinstance(valor, str):
        try:
            numero = float(valor.strip().replace(",", "."))
        except ValueError as erro:
            raise ValorInvalido(f"{valor!r} não é um número") from erro
    else:
        raise ValorInvalido(f"esperava número, recebeu {type(valor).__name__}")
    _conferir_faixa(param, numero)
    return numero


def _conferir_faixa(param: Param, numero: float) -> None:
    unidade = f" {param.unidade}" if param.unidade else ""
    if param.minimo is not None and numero < param.minimo:
        raise ValorInvalido(f"é menor que o mínimo de {param.minimo:g}{unidade}")
    if param.maximo is not None and numero > param.maximo:
        raise ValorInvalido(f"é maior que o máximo de {param.maximo:g}{unidade}")


def _coagir_booleano(_param: Param, valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if texto in _VERDADEIROS:
            return True
        if texto in _FALSOS:
            return False
        raise ValorInvalido(f"{valor!r} não é um booleano reconhecível")
    raise ValorInvalido(f"esperava booleano, recebeu {type(valor).__name__}")


def _coagir_escolha(param: Param, valor: Any) -> str:
    if not isinstance(valor, str):
        raise ValorInvalido(f"esperava texto, recebeu {type(valor).__name__}")
    opcoes = param.opcoes or ()
    if valor not in opcoes:
        disponiveis = ", ".join(opcoes) if opcoes else "nenhuma"
        raise ValorInvalido(f"{valor!r} não está entre as opções: {disponiveis}")
    return valor


def _coagir_cor(_param: Param, valor: Any) -> str:
    if not isinstance(valor, str):
        raise ValorInvalido(f"esperava texto, recebeu {type(valor).__name__}")
    if _HEXADECIMAL.fullmatch(valor) is None:
        raise ValorInvalido(f"{valor!r} não é uma cor hexadecimal como #8AB4F8")
    return valor


_COERCOES = {
    TipoParam.TEXTO: _coagir_texto,
    TipoParam.INTEIRO: _coagir_inteiro,
    TipoParam.DECIMAL: _coagir_decimal,
    TipoParam.BOOLEANO: _coagir_booleano,
    TipoParam.ESCOLHA: _coagir_escolha,
    TipoParam.COR: _coagir_cor,
}


def validar_param(param: Param, valor: Any) -> Any:
    """Coage e valida um único valor contra a declaração do seu parâmetro.

    Args:
        param: A declaração do parâmetro.
        valor: O valor cru, tipicamente vindo da interface ou da linha de
            comando, ainda como string em muitos casos.

    Returns:
        O valor coerido para o tipo declarado.

    Raises:
        ValorInvalido: Se o valor não pode ser coerido ou viola uma restrição.
    """
    return _COERCOES[param.tipo](param, valor)


def validar(produto: Produto, valores: dict[str, Any]) -> ResultadoValidacao:
    """Valida um conjunto de valores contra o manifesto de um produto.

    Chaves ausentes recebem o padrão declarado. Chaves desconhecidas são
    descartadas com aviso no log, porque um preset antigo ou um CSV com coluna
    a mais não deve impedir a geração.

    Args:
        produto: O manifesto do produto.
        valores: Valores crus indexados pela chave do parâmetro.

    Returns:
        O resultado com os valores coeridos e os erros por chave.
    """
    resultado = ResultadoValidacao()
    declarados = {param.chave for param in produto.params}

    for chave in set(valores) - declarados:
        _log.warning(
            "produto '%s' não declara o parâmetro '%s'; valor descartado",
            produto.id,
            chave,
        )

    for param in produto.params:
        if param.chave not in valores:
            resultado.valores[param.chave] = param.padrao
            continue
        try:
            resultado.valores[param.chave] = validar_param(param, valores[param.chave])
        except ValorInvalido as erro:
            resultado.erros.setdefault(param.chave, []).append(str(erro))

    if resultado.erros or produto.validar is None:
        return resultado

    cruzados = produto.validar(resultado.valores)
    if cruzados:
        resultado.erros[CHAVE_CRUZADA] = list(cruzados)

    return resultado
