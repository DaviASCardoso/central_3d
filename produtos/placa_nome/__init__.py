"""Placa com nome em relevo.

Produto de referência da Central: o mais simples que ainda exercita texto
vetorial, operação booleana, chanfro, validação cruzada e aviso ao operador.
"""

from __future__ import annotations

from central.contrato import Param, Produto, TipoParam

from .geometria import gerar, validar

MANIFESTO = Produto(
    id="placa_nome",
    nome="Placa com Nome",
    versao="1.0.0",
    descricao=(
        "Placa retangular com um nome em relevo na face superior. Serve de "
        "plaquinha de porta, de mesa ou de identificação de caixa."
    ),
    categoria="Papelaria",
    tags=("nome", "placa", "personalizado", "texto"),
    params=(
        Param(
            chave="nome",
            rotulo="Nome",
            tipo=TipoParam.TEXTO,
            padrao="Helena",
            max_len=24,
            grupo="Texto",
            ordem=0,
            ajuda="O texto gravado em relevo. Nomes longos são comprimidos "
            "para caber na largura.",
        ),
        Param(
            chave="altura_texto",
            rotulo="Altura do texto",
            tipo=TipoParam.DECIMAL,
            padrao=9.0,
            minimo=4.0,
            maximo=40.0,
            passo=0.5,
            unidade="mm",
            grupo="Texto",
            ordem=1,
            ajuda="Abaixo de 4 mm o traço fica fino demais para bico de 0,4 mm "
            "e o texto vira borrão.",
        ),
        Param(
            chave="relevo",
            rotulo="Relevo",
            tipo=TipoParam.DECIMAL,
            padrao=1.0,
            minimo=0.6,
            maximo=3.0,
            passo=0.1,
            unidade="mm",
            grupo="Texto",
            ordem=2,
            ajuda="Quanto o texto sobressai. Abaixo de 0,6 mm o relevo some no "
            "acabamento.",
        ),
        Param(
            chave="fonte",
            rotulo="Fonte",
            tipo=TipoParam.ESCOLHA,
            padrao="Arial",
            opcoes=("Arial", "Segoe UI", "Verdana", "Tahoma", "Georgia"),
            grupo="Texto",
            ordem=3,
            ajuda="Fontes de traço grosso imprimem melhor que as de traço fino.",
        ),
        Param(
            chave="largura",
            rotulo="Largura",
            tipo=TipoParam.DECIMAL,
            padrao=80.0,
            minimo=20.0,
            maximo=250.0,
            passo=1.0,
            unidade="mm",
            grupo="Placa",
            ordem=0,
        ),
        Param(
            chave="profundidade",
            rotulo="Profundidade",
            tipo=TipoParam.DECIMAL,
            padrao=25.0,
            minimo=15.0,
            maximo=250.0,
            passo=1.0,
            unidade="mm",
            grupo="Placa",
            ordem=1,
        ),
        Param(
            chave="espessura",
            rotulo="Espessura",
            tipo=TipoParam.DECIMAL,
            padrao=4.0,
            minimo=1.6,
            maximo=15.0,
            passo=0.2,
            unidade="mm",
            grupo="Placa",
            ordem=2,
            ajuda="Abaixo de 1,6 mm a placa entorta ao descolar da mesa.",
        ),
        Param(
            chave="chanfro",
            rotulo="Chanfro das quinas",
            tipo=TipoParam.DECIMAL,
            padrao=1.0,
            minimo=0.0,
            maximo=10.0,
            passo=0.2,
            unidade="mm",
            grupo="Placa",
            ordem=3,
            avancado=True,
            ajuda="Quebra as quatro quinas verticais. Zero deixa a placa reta.",
        ),
        Param(
            chave="cor",
            rotulo="Cor de exibição",
            tipo=TipoParam.COR,
            padrao="#8AB4F8",
            grupo="Placa",
            ordem=4,
            avancado=True,
            afeta_geometria=False,
            ajuda="Só afeta o preview e o 3MF; não muda o filamento usado.",
        ),
    ),
    gerar=gerar,
    validar=validar,
    tempo_estimado_min=25,
)
