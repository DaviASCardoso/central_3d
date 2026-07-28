"""Testes da validação de parâmetros, parametrizados por tipo e por limite."""

from __future__ import annotations

from typing import Any

import pytest

from central.contrato import Param, Produto, TipoParam
from central.nucleo.validacao import (
    CHAVE_CRUZADA,
    ValorInvalido,
    validar,
    validar_param,
)


def p(**kwargs: Any) -> Param:
    base: dict[str, Any] = {
        "chave": "x",
        "rotulo": "X",
        "tipo": TipoParam.DECIMAL,
        "padrao": 1.0,
    }
    base.update(kwargs)
    return Param(**base)


# --- TEXTO ---------------------------------------------------------------


def test_texto_aceita_string() -> None:
    assert validar_param(p(tipo=TipoParam.TEXTO, padrao=""), "Helena") == "Helena"


@pytest.mark.parametrize("valor", [123, 4.5, None, True, ["Ana"]])
def test_texto_recusa_nao_string(valor: Any) -> None:
    with pytest.raises(ValorInvalido, match="esperava texto"):
        validar_param(p(tipo=TipoParam.TEXTO, padrao=""), valor)


def test_texto_no_limite_de_max_len_passa() -> None:
    param = p(tipo=TipoParam.TEXTO, padrao="", max_len=6)
    assert validar_param(param, "Helena") == "Helena"


def test_texto_acima_de_max_len_recusa() -> None:
    param = p(tipo=TipoParam.TEXTO, padrao="", max_len=5)
    with pytest.raises(ValorInvalido, match="o máximo é 5"):
        validar_param(param, "Helena")


def test_regex_precisa_casar_por_inteiro() -> None:
    param = p(tipo=TipoParam.TEXTO, padrao="AB", padrao_regex=r"[A-Z]+")
    assert validar_param(param, "ABC") == "ABC"
    with pytest.raises(ValorInvalido, match="por inteiro"):
        validar_param(param, "ABc")


# --- INTEIRO -------------------------------------------------------------


@pytest.mark.parametrize(("entrada", "esperado"), [(3, 3), ("7", 7), (" 8 ", 8), (5.0, 5)])
def test_inteiro_coage(entrada: Any, esperado: int) -> None:
    assert validar_param(p(tipo=TipoParam.INTEIRO, padrao=1), entrada) == esperado


@pytest.mark.parametrize("valor", [2.5, "abc", None, True])
def test_inteiro_recusa(valor: Any) -> None:
    with pytest.raises(ValorInvalido):
        validar_param(p(tipo=TipoParam.INTEIRO, padrao=1), valor)


@pytest.mark.parametrize("valor", [2, 5, 8])
def test_inteiro_dentro_da_faixa_inclusive_nos_limites(valor: int) -> None:
    param = p(tipo=TipoParam.INTEIRO, padrao=5, minimo=2, maximo=8)
    assert validar_param(param, valor) == valor


@pytest.mark.parametrize(("valor", "trecho"), [(1, "mínimo"), (9, "máximo")])
def test_inteiro_fora_da_faixa(valor: int, trecho: str) -> None:
    param = p(tipo=TipoParam.INTEIRO, padrao=5, minimo=2, maximo=8)
    with pytest.raises(ValorInvalido, match=trecho):
        validar_param(param, valor)


# --- DECIMAL -------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [(2.5, 2.5), (3, 3.0), ("4.25", 4.25), ("4,25", 4.25)],
)
def test_decimal_coage(entrada: Any, esperado: float) -> None:
    assert validar_param(p(padrao=1.0), entrada) == pytest.approx(esperado)


@pytest.mark.parametrize("valor", ["abc", None, True, []])
def test_decimal_recusa(valor: Any) -> None:
    with pytest.raises(ValorInvalido):
        validar_param(p(padrao=1.0), valor)


@pytest.mark.parametrize("valor", [0.6, 3.0, 5.0])
def test_decimal_dentro_da_faixa_inclusive_nos_limites(valor: float) -> None:
    assert validar_param(p(minimo=0.6, maximo=5.0), valor) == pytest.approx(valor)


@pytest.mark.parametrize(("valor", "trecho"), [(0.5, "mínimo"), (5.1, "máximo")])
def test_decimal_fora_da_faixa(valor: float, trecho: str) -> None:
    with pytest.raises(ValorInvalido, match=trecho):
        validar_param(p(minimo=0.6, maximo=5.0), valor)


def test_mensagem_de_faixa_traz_a_unidade() -> None:
    with pytest.raises(ValorInvalido, match="0.6 mm"):
        validar_param(p(minimo=0.6, unidade="mm"), 0.1)


# --- BOOLEANO ------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [(True, True), (False, False), ("sim", True), ("não", False), ("1", True), ("0", False)],
)
def test_booleano_coage(entrada: Any, esperado: bool) -> None:
    assert validar_param(p(tipo=TipoParam.BOOLEANO, padrao=False), entrada) is esperado


@pytest.mark.parametrize("valor", ["talvez", 2, None])
def test_booleano_recusa(valor: Any) -> None:
    with pytest.raises(ValorInvalido):
        validar_param(p(tipo=TipoParam.BOOLEANO, padrao=False), valor)


# --- ESCOLHA -------------------------------------------------------------


def test_escolha_aceita_opcao_declarada() -> None:
    param = p(tipo=TipoParam.ESCOLHA, padrao="a", opcoes=("a", "b"))
    assert validar_param(param, "b") == "b"


def test_escolha_recusa_fora_do_conjunto() -> None:
    param = p(tipo=TipoParam.ESCOLHA, padrao="a", opcoes=("a", "b"))
    with pytest.raises(ValorInvalido, match="não está entre as opções"):
        validar_param(param, "c")


# --- COR -----------------------------------------------------------------


@pytest.mark.parametrize("valor", ["#8AB4F8", "#fff", "#8AB4F8FF"])
def test_cor_aceita_hexadecimal(valor: str) -> None:
    assert validar_param(p(tipo=TipoParam.COR, padrao="#000000"), valor) == valor


@pytest.mark.parametrize("valor", ["8AB4F8", "#GGGGGG", "azul", "#12345"])
def test_cor_recusa_o_resto(valor: str) -> None:
    with pytest.raises(ValorInvalido, match="hexadecimal"):
        validar_param(p(tipo=TipoParam.COR, padrao="#000000"), valor)


# --- validação do conjunto ----------------------------------------------


def _produto(validar_cruzado: Any = None) -> Produto:
    return Produto(
        id="teste",
        nome="Teste",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(
            Param(chave="nome", rotulo="Nome", tipo=TipoParam.TEXTO, padrao="Ana", max_len=5),
            Param(
                chave="altura",
                rotulo="Altura",
                tipo=TipoParam.DECIMAL,
                padrao=3.0,
                minimo=1.0,
                maximo=10.0,
                unidade="mm",
            ),
        ),
        gerar=lambda valores: valores,
        validar=validar_cruzado,
    )


def test_chaves_ausentes_recebem_o_padrao() -> None:
    resultado = validar(_produto(), {})
    assert resultado.valido
    assert resultado.valores == {"nome": "Ana", "altura": 3.0}


def test_chave_desconhecida_e_descartada_sem_invalidar() -> None:
    resultado = validar(_produto(), {"cor_do_cabelo": "ruivo"})
    assert resultado.valido
    assert "cor_do_cabelo" not in resultado.valores


def test_erro_fica_indexado_pela_chave_culpada() -> None:
    resultado = validar(_produto(), {"nome": "Helena", "altura": 99})
    assert not resultado.valido
    assert set(resultado.erros) == {"nome", "altura"}
    assert "máximo é 5" in resultado.erros["nome"][0]


def test_validar_do_manifesto_roda_e_usa_a_chave_cruzada() -> None:
    def cruzado(valores: dict[str, Any]) -> list[str]:
        if len(valores["nome"]) * 2 > valores["altura"]:
            return ["nome longo demais para essa altura"]
        return []

    resultado = validar(_produto(cruzado), {"nome": "Ana", "altura": 2.0})
    assert not resultado.valido
    assert resultado.erros[CHAVE_CRUZADA] == ["nome longo demais para essa altura"]


def test_validar_do_manifesto_nao_roda_com_erro_na_primeira_etapa() -> None:
    chamou = []

    def cruzado(valores: dict[str, Any]) -> list[str]:
        chamou.append(valores)
        return []

    resultado = validar(_produto(cruzado), {"altura": 99})
    assert not resultado.valido
    assert chamou == []


def test_validar_do_manifesto_aprova() -> None:
    resultado = validar(_produto(lambda _v: []), {"nome": "Ana", "altura": 9.0})
    assert resultado.valido
    assert resultado.valores == {"nome": "Ana", "altura": 9.0}


def test_mensagens_prefixa_com_a_chave() -> None:
    resultado = validar(_produto(), {"altura": 99})
    assert resultado.mensagens() == ["altura: é maior que o máximo de 10 mm"]


def test_mensagens_do_cruzado_nao_tem_prefixo() -> None:
    resultado = validar(_produto(lambda _v: ["parede fina demais"]), {})
    assert resultado.mensagens() == ["parede fina demais"]
