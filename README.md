# DP100K-Fp02 — Report de otimização (multi-turma)

Report **ao vivo** do DP100K-Fp02 no formato de apresentação pro time achar pontos
de otimização. Uma aba de **Visão Geral do mês** + uma aba por **turma do mês**
(ex Julho: S1/S2/S3). Cada turma abre em blocos isolados **Prospecção / Quiz / RMKT**,
desempenho por anúncio (CPA real Hubla + MQL) e qualidade de MQL. Publica no GitHub Pages.

- **Live:** https://vianapatrick15-max.github.io/dp100k-report-live/
- **Refresh:** 1x/dia (06:20 BRT) via GitHub Action + `workflow_dispatch` manual.

## Como funciona

As **janelas de cada turma são derivadas da aba `Investimento por Hora`** (CHAVE
horária tagada pelo time) — a MESMA fronteira vale pra spend e pra venda. As turmas
do **mês corrente** (todas) puxam o Meta pesado por janela; a tag manual de Turma no
Hubla atrasa e não cobre o mês aberto, por isso **as vendas são bucketadas por
data/hora** nessas janelas canônicas (valida com os snapshots conhecidos).

```
report_v2.py   → data_v2.json
 ├─ Investimento por Hora  janelas datetime canônicas + KPIs hora-exato por turma
 ├─ Hubla (date-bucket)    vendas por turma × funil (via utm campaign) × ad + MQL
 ├─ Meta (por janela)      spend/funil por Prospecção/Quiz/RMKT + top ads (ad-level)
 └─ Pesquisa               renda → MQL (renda ≥ R$ 10.001), cross por e-mail
build_v2.py    data_v2.json → index.html (self-contained, sem libs externas)
```

**Classificação de funil (token da campanha):** `QUIZ` → Quiz · `RMKT`/`RKMT` → RMKT ·
resto → Prospecção. Vale pro spend (Meta), pra venda (utm campaign no Hubla) e pro ad.

## Regras de negócio

- **Venda = SEMPRE Hubla**, bucketada por data/hora nas janelas canônicas.
- **MQL = comprador com renda ≥ R$ 10.001** (cruza e-mail Hubla × Pesquisa).
- **Spend por bloco/ad** = rateio do investido canônico (planilha, hora-exato) pela
  participação do Meta no bloco/ad — soma exatamente o investido da turma.
- **CPA real** = investido Meta ÷ vendas Hubla (por `utm_content` = AD-XX).
- Conta Meta `act_1725623984282551`, campanhas `DP100K-Fp02` (exclui NUTRICAO).

## Rodar local

```bash
pip install -r requirements.txt
python report_v2.py     # usa os .env das skills (Sheets SA + Meta token) → data_v2.json
python build_v2.py      # data_v2.json → index.html
open index.html
```

## Deploy / CI

GitHub Action `refresh.yml` roda `report_v2.py` + `build_v2.py` e commita `index.html`.

| Secret | O que é |
|--------|---------|
| `GCP_SA_B64` | JSON da service account `ga4-reader@n8n-tathi` (base64), leitor da consolidada |
| `META_ADS_TOKEN` | token da API do Meta (mesmo da skill meta-ads-instituto-id) |
| `META_APP_ID` | app id do Meta |

Trigger manual: `gh workflow run "Refresh DP100K Report LIVE" --repo vianapatrick15-max/dp100k-report-live`

## Notas

- `data_v2.json` é intermediário (gitignored). Só o `index.html` é commitado.
- Turma aberta aparece marcada como **parcial** — vendas/pesquisa do dia corrente
  amadurecem no build do dia seguinte (pesquisa pós-evento atrasa ~5-7d).
- Pipeline antigo (single-turma rico: `run.py`/`build.py`/`persona.py`/`rank.py`)
  segue no repo como referência, mas **não é mais usado pelo CI**.
