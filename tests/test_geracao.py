"""Testes do pipeline síncrono de geração."""

from __future__ import annotations

from typing import Any

import pytest
from build123d import Box, Cylinder, Location, Pos, Rotation

from central.contrato import Corpo, Param, Produto, Resultado, TipoParam
from central.nucleo.erros import ErroDeGeracao, ErroDeValidacao
from central.nucleo.geracao import gerar_sincrono, normalizar, orientar
from central.nucleo.tesselagem import NivelTesselagem


def produto(gerar, **extras: Any) -> Produto:
    return Produto(
        id="teste",
        nome="Teste",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(
            Param(
                chave="lado",
                rotulo="Lado",
                tipo=TipoParam.DECIMAL,
                padrao=10.0,
                minimo=1.0,
                maximo=50.0,
            ),
        ),
        gerar=gerar,
        **extras,
    )


# --- normalizar ----------------------------------------------------------


def test_solido_solto_vira_resultado_com_um_corpo() -> None:
    resultado = normalizar(Box(10, 10, 10))
    assert len(resultado.corpos) == 1
    assert resultado.corpos[0].nome == "corpo_1"


def test_lista_de_solidos_vira_corpos_numerados() -> None:
    resultado = normalizar([Box(1, 1, 1), Cylinder(radius=1, height=1)])
    assert [c.nome for c in resultado.corpos] == ["corpo_1", "corpo_2"]


def test_resultado_completo_passa_intacto() -> None:
    original = Resultado(
        corpos=[Corpo(nome="base", forma=Box(1, 1, 1))],
        avisos=["nome comprimido"],
        metadados={"caracteres": 6},
    )
    resultado = normalizar(original)
    assert resultado is original
    assert resultado.corpos[0].nome == "base"
    assert resultado.avisos == ["nome comprimido"]
    assert resultado.metadados == {"caracteres": 6}


def test_as_tres_formas_produzem_resultado_equivalente() -> None:
    forma = Box(10, 10, 10)
    solto = normalizar(forma)
    lista = normalizar([forma])
    completo = normalizar(Resultado(corpos=[Corpo(nome="", forma=forma)]))
    volumes = {r.corpos[0].forma.volume for r in (solto, lista, completo)}
    nomes = {r.corpos[0].nome for r in (solto, lista, completo)}
    assert len(volumes) == 1
    assert nomes == {"corpo_1"}


def test_nomes_declarados_sao_preservados_e_os_anonimos_nao_colidem() -> None:
    resultado = normalizar(
        [
            Corpo(nome="", forma=Box(1, 1, 1)),
            Corpo(nome="corpo_1", forma=Box(1, 1, 1)),
            Corpo(nome="", forma=Box(1, 1, 1)),
        ]
    )
    nomes = [c.nome for c in resultado.corpos]
    assert nomes[1] == "corpo_1"
    assert len(set(nomes)) == 3


def test_corpo_solto_e_aceito() -> None:
    resultado = normalizar(Corpo(nome="tampa", forma=Box(1, 1, 1)))
    assert resultado.corpos[0].nome == "tampa"


@pytest.mark.parametrize("saida", [None, 42, "sólido", {"a": 1}])
def test_tipo_irreconhecivel_e_recusado(saida: Any) -> None:
    with pytest.raises(ErroDeGeracao, match="não é sólido"):
        normalizar(saida)


def test_resultado_sem_corpos_e_recusado() -> None:
    with pytest.raises(ErroDeGeracao, match="sem nenhum corpo"):
        normalizar(Resultado(corpos=[]))


def test_lista_com_lixo_dentro_e_recusada() -> None:
    with pytest.raises(ErroDeGeracao, match="contém int"):
        normalizar([Box(1, 1, 1), 7])


# --- orientar ------------------------------------------------------------


def test_peca_sai_assentada_e_centralizada() -> None:
    resultado = orientar(
        normalizar(Pos(30, -12, 55) * Box(10, 20, 30)),
        produto(lambda v: v),
    )
    caixa = resultado.corpos[0].forma.bounding_box()
    assert caixa.min.Z == pytest.approx(0.0, abs=1e-6)
    assert caixa.center().X == pytest.approx(0.0, abs=1e-6)
    assert caixa.center().Y == pytest.approx(0.0, abs=1e-6)


def test_orientacao_do_manifesto_e_aplicada() -> None:
    deitado = orientar(normalizar(Box(10, 10, 40)), produto(lambda v: v))
    de_pe = orientar(
        normalizar(Box(10, 10, 40)),
        produto(lambda v: v, orientacao=Rotation(90, 0, 0)),
    )
    assert deitado.corpos[0].forma.bounding_box().size.Z == pytest.approx(40.0)
    assert de_pe.corpos[0].forma.bounding_box().size.Z == pytest.approx(10.0)


def test_o_conjunto_e_transladado_junto_preservando_o_encaixe() -> None:
    # Box do build123d nasce centrado na origem: a base ocupa -5..5 e a tampa
    # precisa começar em 5, logo seu centro fica em 7.5.
    base = Corpo(nome="base", forma=Box(20, 20, 10))
    tampa = Corpo(nome="tampa", forma=Pos(0, 0, 7.5) * Box(20, 20, 5))
    resultado = orientar(Resultado(corpos=[base, tampa]), produto(lambda v: v))

    caixa_base = resultado.corpos[0].forma.bounding_box()
    caixa_tampa = resultado.corpos[1].forma.bounding_box()
    assert caixa_base.min.Z == pytest.approx(0.0, abs=1e-6)
    assert caixa_tampa.min.Z == pytest.approx(caixa_base.max.Z, abs=1e-6)


def test_orientacao_por_location_tambem_funciona() -> None:
    resultado = orientar(
        normalizar(Box(10, 10, 40)),
        produto(lambda v: v, orientacao=Location((0, 0, 0), (0, 90, 0))),
    )
    assert resultado.corpos[0].forma.bounding_box().size.X == pytest.approx(40.0)


# --- gerar_sincrono ------------------------------------------------------


def test_pipeline_completo_devolve_malhas_por_corpo() -> None:
    def gerar(valores: dict[str, Any]) -> list[Corpo]:
        lado = valores["lado"]
        return [
            Corpo(nome="base", forma=Box(lado, lado, 5)),
            Corpo(nome="tampa", forma=Pos(0, 0, 3.5) * Box(lado, lado, 2)),
        ]

    saida = gerar_sincrono(produto(gerar), {"lado": 20.0})
    assert set(saida.malhas) == {"base", "tampa"}
    assert all(malha.is_watertight for malha in saida.malhas.values())
    assert saida.dimensoes == pytest.approx((20.0, 20.0, 7.0))
    assert saida.nivel is NivelTesselagem.PREVIEW


def test_valores_ausentes_usam_o_padrao() -> None:
    saida = gerar_sincrono(produto(lambda v: Box(v["lado"], 5, 5)), {})
    assert saida.valores == {"lado": 10.0}
    assert saida.dimensoes[0] == pytest.approx(10.0)


def test_nivel_de_exportacao_produz_mais_triangulos() -> None:
    manifesto = produto(lambda v: Cylinder(radius=v["lado"], height=5))
    leve = gerar_sincrono(manifesto, {}, NivelTesselagem.PREVIEW)
    fina = gerar_sincrono(manifesto, {}, NivelTesselagem.EXPORTACAO)
    assert len(fina.malhas["corpo_1"].faces) > len(leve.malhas["corpo_1"].faces)


def test_avisos_do_produto_chegam_ao_resultado() -> None:
    def gerar(_valores: dict[str, Any]) -> Resultado:
        return Resultado(
            corpos=[Corpo(nome="base", forma=Box(10, 10, 10))],
            avisos=["nome longo demais foi comprimido em 8%"],
        )

    saida = gerar_sincrono(produto(gerar), {})
    assert saida.avisos == ["nome longo demais foi comprimido em 8%"]


def test_valor_invalido_barra_antes_de_chamar_gerar() -> None:
    chamou = []

    def gerar(valores: dict[str, Any]):
        chamou.append(valores)
        return Box(1, 1, 1)

    with pytest.raises(ErroDeValidacao, match="máximo"):
        gerar_sincrono(produto(gerar), {"lado": 999.0})
    assert chamou == []


def test_validar_do_manifesto_barra_a_geracao() -> None:
    manifesto = produto(
        lambda v: Box(1, 1, 1),
        validar=lambda v: ["parede fina demais"] if v["lado"] < 20 else [],
    )
    with pytest.raises(ErroDeValidacao, match="parede fina"):
        gerar_sincrono(manifesto, {"lado": 10.0})


def test_falha_dentro_do_produto_vira_erro_de_geracao_com_causa() -> None:
    def gerar(_valores: dict[str, Any]):
        raise ZeroDivisionError("division by zero")

    with pytest.raises(ErroDeGeracao, match="ZeroDivisionError") as capturado:
        gerar_sincrono(produto(gerar), {})
    assert isinstance(capturado.value.__cause__, ZeroDivisionError)


def test_produto_que_devolve_lixo_vira_erro_de_geracao() -> None:
    with pytest.raises(ErroDeGeracao, match="não é sólido"):
        gerar_sincrono(produto(lambda _v: "um cubo, prometo"), {})
