"""Config — DP100K-Fp02 Report LIVE (turma atual, refresh diario).

Regenera o relatorio rico (thumbnails + persona + fatigue + ranking) da turma
ABERTA atual todo dia. Toda a tabela de tendencia sai da planilha; so a turma
atual puxa o Meta pesado.
"""
import os
import re

# --- Conta Meta ---
ACCOUNT = "act_1725623984282551"
CAMP_MATCH = "DP100K-Fp02"          # substring que identifica campanhas do funil
CAMP_EXCLUDE = "NUTRICAO"           # excluir retargeting de nutricao
QUIZ_KEYWORD = "QUIZ"

# --- Planilha consolidada (fonte canonica) ---
CONSOLIDADO_SHEET_ID = "1G6fjdMB9iwCrnDIHhmSoCC2nbHYIOaEvfRYxPUpBIK8"
TAB_INVEST   = "Investimento por Hora"   # KPIs por turma (spend/vendas/impr/clicks/lpv/ic)
TAB_HUBLA    = "Dados_venda_Hubla"        # vendas reais (venda canonica)
TAB_PESQUISA = "Pesquisa"                 # persona + renda (MQL)

# Colunas da aba Investimento por Hora (posicionais).
# Coluna "Mês" inserida no inicio (jul/26) -> todos os indices deslocados +1.
# Header atual: Mês | TURMA | CHAVE | DATA | HORA | INVESTIDO | VENDAS | IC | CTR | VISITAS | IMPRESSÕES | CLICKS
INV_COL_TURMA  = 1
INV_COL_CHAVE  = 2
INV_COL_DATA   = 3
INV_COL_INVEST = 5
INV_COL_VENDAS = 6
INV_COL_IC     = 7
INV_COL_VISITAS= 9
INV_COL_IMPR   = 10
INV_COL_CLICKS = 11

# Janela de turmas na tabela de tendencia
N_TURMAS = 4
TURMA_DAYS = 7           # duracao tipica de uma turma (boundary compartilhado)
TURMA_TAIL_SLACK = 2     # dias de folga p/ incluir cauda nao-rotulada da turma atual

# Regex de turma semanal, ex "Julho/26 - 2"
TURMA_RE = re.compile(r'^\s*([A-Za-zçÇãéêíóúâ]+)\s*/\s*(\d{2})\s*-\s*(\d+)\s*$')

# --- Meta info ---
CLIENTE = "C1 - Tathi Deandhela"
PRODUTO = "DP100K-Fp02"
FUNIL_NOME = 'Desafio Palestrante 100K'
CPA_ALVO = 250.0         # ref p/ score e classificacao de saude

# --- Persona: nomes oficiais das colunas da Pesquisa ---
COL_AGE      = "Quantos anos você tem? (multiple-choice)"
COL_GENDER   = "Qual é o seu gênero? (multiple-choice)"
COL_TIME     = "Há quanto tempo você me conhece? (multiple-choice)"
COL_PREV     = "Já participou de algum evento/curso meu antes? (yes-no)"
COL_OCC      = "Qual é sua ocupação atual? (multiple-choice)"
COL_INCOME   = "Qual a sua faixa de renda mensal atual? (multiple-choice)"
COL_SELF     = "Quando se fala em palestras, você se considera: (multiple-choice)"
COL_DESIRE   = "O que você deseja alcançar com o seu conhecimento? (multiple-choice)"
COL_THOUGHT  = "Qual primeiro pensamento que vem na sua mente quando pensa em vender uma palestra por 5 mil reais? (long-text)"
COL_CHALL    = "Quais desafios e problemas estão impedindo você de ser um palestrante memorável? (long-text)"
COL_LEARN    = "O que você precisa aprender durante o desafio para dizer que valeu a pena participar das 5 aulas? (long-text)"
COL_QUESTION = "Se você tivesse uma oportunidade de estar comigo em um evento presencial, que pergunta você gostaria que eu te respondesse? (long-text)"
COL_STATE    = "State"
PESQ_EMAIL   = "Por fim, qual é o seu e-mail? (email)"

MESES_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_ABBR = {"Janeiro": "Jan", "Fevereiro": "Fev", "Março": "Mar", "Marco": "Mar",
              "Abril": "Abr", "Maio": "Mai", "Junho": "Jun", "Julho": "Jul",
              "Agosto": "Ago", "Setembro": "Set", "Outubro": "Out",
              "Novembro": "Nov", "Dezembro": "Dez"}


def mes_num(nome):
    n = (nome or '').strip().lower().replace('marco', 'março')
    for i, m in enumerate(MESES_PT):
        if m.lower() == n:
            return i
    return 0


def turma_short(label):
    """'Julho/26 - 2' -> 'Jul S2'."""
    m = TURMA_RE.match(label or '')
    if not m:
        return label
    mes, _, n = m.group(1), m.group(2), m.group(3)
    return f"{MESES_ABBR.get(mes.strip(), mes[:3])} S{n}"


def turma_title(label):
    """'Julho/26 - 2' -> 'Julho/26 Sem 2'."""
    m = TURMA_RE.match(label or '')
    if not m:
        return label
    mes, yy, n = m.group(1), m.group(2), m.group(3)
    return f"{mes.strip()}/{yy} Sem {n}"


# --- parsers BR ---
def parse_money(s):
    if not s:
        return 0.0
    s = str(s).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def parse_int(s):
    if not s:
        return 0
    s = str(s).replace(".", "").replace(",", ".").strip()
    try:
        return int(float(s))
    except Exception:
        return 0


def is_mql_renda(renda):
    """MQL DP100K (oficial 08/06/2026): renda mensal >= R$ 10.001.
    A faixa 8.001-10.000 NAO conta."""
    s = (renda or '').lower().strip()
    if 'r$ 10.001' in s or 'r$ 15.001' in s or 'r$ 20.001' in s:
        return True
    if 'acima de r$' in s:
        m = re.search(r'acima de r\$\s?([\d.]+)', s)
        if m:
            try:
                return float(m.group(1).replace('.', '')) >= 10000
            except Exception:
                return False
    return False
