# DP100K-Fp02 — Report LIVE

Versão **ao vivo** do report semanal do DP100K-Fp02. Em vez de um HTML congelado
gerado à mão a cada semana, este repositório **regenera o report completo da
turma ABERTA atual todo dia** (thumbnails de criativo, top ads, persona, fatigue,
CTR, ranking, breakdowns) e publica no GitHub Pages.

- **Live:** https://vianapatrick15-max.github.io/dp100k-report-live/
- **Refresh:** 1x/dia (06:20 BRT) via GitHub Action + `workflow_dispatch` manual.

## Como funciona

A turma atual é **detectada automaticamente** da aba `Investimento por Hora`
(última turma semanal rotulada, ex `Julho/26 - 2`), incluindo a cauda de horas
ainda não rotuladas pelo time. A janela de datas sai das próprias linhas.

Insight que barateia tudo: a **tabela de tendência das 4 turmas** sai inteira da
planilha (Investimento + Hubla + Pesquisa). Só a **turma atual** paga o pull
pesado do Meta (criativos, thumbnails, persona, fatigue).

```
run.py
 ├─ sheets_data.py  detecta turma atual + KPIs de 4 turmas (T/S/TL/MW) + detalhe atual
 ├─ meta_data.py    turma atual: camps, ads, breakdowns, fatigue, topline, previews, copies, thumbs(base64), daily
 ├─ persona.py      persona (comprador Hubla × respondente Pesquisa, por origem e por ad)
 ├─ rank.py         top ads (vendas Hubla + CPA real + MQL, score composto)
 └─ build.py        renderiza index.html (mesmo visual do report original)
```

## Regras de negócio (herdadas do report original)

- **Venda = SEMPRE Hubla** cruzada por `utm_content` (AD-XX), nunca pixel.
- **MQL = comprador com renda ≥ R$ 10.001** (cruza e-mail Hubla × Pesquisa).
- Conta Meta `act_1725623984282551`, campanhas `DP100K-Fp02` (exclui NUTRICAO).
- CPA real = spend Meta ÷ vendas Hubla.

## Rodar local

```bash
pip install -r requirements.txt
python run.py           # usa os .env das skills (Sheets SA + Meta token)
open index.html
```

## Deploy / CI

GitHub Action `refresh.yml` roda `run.py` e commita `index.html`. Secrets:

| Secret | O que é |
|--------|---------|
| `GCP_SA_B64` | JSON da service account `ga4-reader@n8n-tathi` (base64), leitor da planilha consolidada |
| `META_ADS_TOKEN` | token da API do Meta (mesmo da skill meta-ads-instituto-id) |
| `META_APP_ID` | app id do Meta |

Trigger manual: `gh workflow run "Refresh DP100K Report LIVE" --repo vianapatrick15-max/dp100k-report-live`

## Notas

- `_build_data.json` é intermediário (gitignored, ~6 MB com thumbnails).
- A narrativa do `build.py` é re-rotulada por `_relabel()`: o template é uma cópia
  congelada do `build_dashboard_jul26_sem1.py` e os labels da Sem 1/jul viram os da
  janela de 4 turmas corrente a cada build.
- Vendas/Pesquisa da turma atual são filtradas pelo rótulo do time (Hubla/Pesquisa);
  vendas do dia corrente ainda não rotuladas podem entrar no build do dia seguinte.
