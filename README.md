# SmartRoute Logística

Sistema de roteirização inteligente com eficiência energética — Projeto Integrador IV
(Engenharia de Computação, UNISAL · Prof. Me. Warner Brezolin · 2026/2).
Empresa parceira fictícia: **Construlog Materiais de Construção** (35 entregas/dia, 2 motos + 1 caminhão).

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                      # abre em http://127.0.0.1:5000
```

No dashboard: **Carregar 35 entregas de demo** → o sistema já planeja as rotas. Clique numa rota
(aba *Rotas*) para destacá-la no mapa, use **Avançar simulação ▶** para ver o AFD e a posição do
veículo mudarem, e clique numa via do mapa para bloqueá-la (obra/acidente) e ver o recálculo.

Testes: `python -m pytest -q` (47 testes). O mapa usa Leaflet + OpenStreetMap via CDN, então o
navegador precisa de internet; o resto roda 100% local (SQLite, sem serviços externos).

## Estrutura

```
run.py                     inicia o servidor
smartroute/
  graph.py                 Grafo (lista de adjacências, pesos dinâmicos, bloqueio de vias)
  dijkstra.py              Dijkstra com heap mínimo, custo injetável  O((V+E) log V)
  physics.py               Atrito, resistência do ar, potência, rendimento -> litros
  custos.py                Funções de custo por aresta: energia | distância | tempo
  router.py                Roteirizador (atribuição, ordem das paradas, 2-opt, baseline)
  ordenacao.py             Merge Sort e Fila de Prioridade
  enderecos.py             Trie para busca/autocomplete de endereços
  delivery_fsm.py          AFD dos estados da entrega
  malha.py                 Malha viária sintética 7x7 (~15 km²) com depósito no centro
  db.py                    Persistência SQLite (classe Repo)
  servico.py               Planejamento, desvio de rotas, simulação, KPIs
  reports.py               Relatórios CSV e PDF
  api.py                   API REST (Flask)
  templates/ static/       Dashboard (HTML/CSS/JavaScript puro + Leaflet)
tests/                     47 testes (núcleo, roteirizador, API)
docs/ARQUITETURA.md        Diagramas, fórmulas e rastreabilidade com o documento de abertura
```

## Como cada objetivo do documento de abertura foi atendido

| # | Objetivo específico | Disciplina | Onde está |
|---|---|---|---|
| 1 | Grafo com pesos dinâmicos | Estrutura de Dados | `graph.py`, `malha.py` |
| 2 | Dijkstra com heap mínimo | Algorítmica | `dijkstra.py`, `router.py` |
| 3 | Função de custo física | Física II | `physics.py`, `custos.py` |
| 4 | AFD dos estados da entrega | Teoria da Computação | `delivery_fsm.py` |
| 5 | Dashboard com KPIs e relatórios | Gestão de TI | `templates/`, `static/`, `servico.kpis`, `reports.py` |
| 6 | Modelo de negócio SaaS | Empreendedorismo | `docs/ARQUITETURA.md` (seção 6) |
| 7 | Aplicação integrada | Todas | `run.py` |

Funcionalidades da seção 4.2: cadastro de entregas, roteirização, dashboard em tempo real
(simulado), relatórios PDF/CSV e bloqueio manual de vias com recálculo.

## Decisões e premissas que vale conhecer (para a banca)

1. **Calibração do consumo.** O modelo físico puro dá um consumo muito menor que 8 km/L (moto) e
   4 km/L (caminhão), valores do documento, porque ignora arranca-e-para e marcha lenta. Cada veículo
   tem um `fator_calibracao` que ajusta a escala ao km/L informado; a dependência de **carga** e
   **velocidade** continua vindo da física. Para usar números mais realistas, altere `kml_ref`
   em `physics.veiculos_padrao()`; o sistema recalibra sozinho.
2. **Economia medida.** Compara-se a rota otimizada com uma rota "empírica" simulada: **mesmas
   entregas por viagem**, na ordem de cadastro e pelo caminho mais curto em km. Ou seja, mede o ganho de
   ordenar paradas e escolher caminhos, não o de distribuir entregas entre veículos. É um resultado
   simulado, não uma medição na Construlog.
3. **Malha fictícia.** A malha é uma grade sintética (coordenadas em Lorena-SP só para desenhar o
   mapa), conforme o escopo do documento, que evita integrar Google Maps em tempo real.
4. **Rastreamento simulado.** A posição dos veículos avança pelo botão *Avançar simulação*, sem GPS real.
5. **Prazos.** `prazo_min` é em minutos desde o início do expediente; o ETA considera 5 min de serviço
   por parada (`config.TEMPO_SERVICO_MIN`).
6. **Heurística.** Atribuição gulosa + vizinho mais próximo + 2-opt. Não garante o ótimo global
   (problema NP-difícil), mas é determinística e rápida (~0,02 s para 35 entregas).

## Próximos passos sugeridos

- Trocar SQLite por PostgreSQL (só `db.py` muda).
- Importar malha real do OpenStreetMap (OSMnx) no lugar da grade sintética.
- Autenticação por perfil (operador x gestor) e multiempresa para o modelo SaaS.
