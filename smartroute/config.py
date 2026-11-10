"""Parâmetros globais do SmartRoute Logística (valores do documento de abertura)."""

PRECO_COMBUSTIVEL_RS_L = 6.00   # R$/litro (seção 3.3 do documento)
TEMPO_SERVICO_MIN = 5.0         # tempo parado em cada entrega (descarga/assinatura)
VEL_REF_KMH = 40.0              # velocidade de referência usada na calibração do consumo
DEPOSITO_ID = "N33"             # nó do depósito da Construlog na malha

PRIORIDADES = {1: "Urgente", 2: "Normal", 3: "Baixa"}
