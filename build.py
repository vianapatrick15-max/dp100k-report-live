"""Builder do REPORT LIVE DP100K-Fp02 — turma atual (data-driven).

NAO editar a mao: e uma copia cirurgica do build_dashboard_jul26_sem1.py.
Todo o corpo (render/CSS/JS) e identico ao report original; so o header carrega
os dados de _build_data.json (montado por run.py) e a narrativa e re-rotulada
no fim por _relabel() — os literais congelados da Sem 1/26 viram os labels da
janela de 4 turmas corrente.
"""
import json, os, re, csv
from collections import defaultdict

_D   = json.load(open(os.environ.get('BUILD_DATA', '_build_data.json')))
OUT  = os.environ.get('BUILD_OUT', 'index.html')

TURMAS = _D['turmas']                       # 4 turmas, mais antiga -> atual
T1, T2, T3, T4     = [t['T']  for t in TURMAS]
S1, S2, S3, S4     = [t['S']  for t in TURMAS]
TL1, TL2, TL3, _tl4 = [t['TL'] for t in TURMAS]
MW1, MW2, MW3, MW4 = [t['MW'] for t in TURMAS]

CUR = _D['current']
CAMP4    = CUR['camps']
ADS_RAW  = CUR['ads']
BD4_RAW  = CUR['breakdowns']
FAT4     = CUR['fatigue']
MQL4     = CUR['mql_per_ad']
PREV4    = CUR['previews']
COPY4    = CUR['copies']
DAILY    = CUR['daily']
PERSONA_BW = CUR['persona']
PERSONA    = PERSONA_BW['all']
TOP_ADS_4W = CUR['top_ads']
EMAIL2RENDA = CUR['email2renda']
THUMBS_B64  = CUR['thumbs_b64']
TL4 = CUR['topline']                        # topline real do Meta (tem link_clicks/link_ctr)
PREV_FRESH = PREV3 = PREV_S2 = PREV_S1 = {}  # sem previews historicos no modo live

GEN_TIME = _D['updated_at']


def _short_period(p):
    try:
        a, b = p.split(' \u2192 ')
        return f"{a[:5]} \u2192 {b[:5]}"
    except Exception:
        return p


def _relabel(html):
    """Re-rotula os literais congelados do template (jul26 sem1) para a janela atual.
    Single-pass (alternacao ordenada por tamanho) — sem re-scan, sem cadeia."""
    L = [t['short'] for t in TURMAS]            # ex: Jun S3, Jun S4, Jul S1, Jul S2
    Pr = [_short_period(t['period']) for t in TURMAS]
    cur, prev = TURMAS[3], TURMAS[2]
    cur_long  = cur['title'].replace('/26', '')   # "Julho Sem 2"
    prev_long = prev['title'].replace('/26', '')
    m = {
        'Julho/26 Sem 1': cur['title'],
        'Julho/26 - 1':  cur['label'],
        'Julho/26-1':    cur['label'],
        'Julho Sem 1':   cur_long,
        'Junho Sem 4':   prev_long,
        'Jul S1':        L[3],
        'Jun S4':        L[2],
        'Jun S3':        L[1],
        'Jun S2':        L[0],
        '22/06/2026 \u2192 29/06/2026': cur['period'],
        '22/06 \u2192 29/06': Pr[3],
        '15/06 \u2192 22/06': Pr[2],
        '08/06 \u2192 15/06': Pr[1],
        '01/06 \u2192 08/06': Pr[0],
        '1\u00aa semana do ciclo de julho': 'turma em andamento \u00b7 atualiza 1x/dia',
        'Semana 1 (': f'{L[3]} (',
    }
    keys = sorted(m.keys(), key=len, reverse=True)
    pat = re.compile('|'.join(re.escape(k) for k in keys))
    return pat.sub(lambda mm: m[mm.group(0)], html)

def best_thumb(ad_ids):
    for aid in ad_ids:
        if THUMBS_B64.get(aid): return THUMBS_B64[aid]
    return None

def best_preview_iframe(ad_ids):
    """Preview iframe: prefere refetch fresco > Sem 4 > Sem 3 > Sem 2 > Sem 1."""
    for aid in ad_ids:
        if PREV_FRESH.get(aid): return PREV_FRESH[aid]
    for aid in ad_ids:
        if PREV4.get(aid): return PREV4[aid]
    for aid in ad_ids:
        if PREV3.get(aid): return PREV3[aid]
    for aid in ad_ids:
        if PREV_S2.get(aid): return PREV_S2[aid]
    for aid in ad_ids:
        if PREV_S1.get(aid): return PREV_S1[aid]
    return None

_PREV_URL_RE = re.compile(r'src="([^"]+)"')

def best_preview_url(ad_ids):
    iframe = best_preview_iframe(ad_ids)
    if not iframe: return None
    m = _PREV_URL_RE.search(iframe)
    return m.group(1).replace('&amp;','&') if m else None

# === Normalize breakdowns to sem2 shape (dict keyed by string, with `purch`) ===
def normalize_bd(rows, key_fields, sep=' · '):
    out = {}
    for r in rows:
        key = sep.join(str(r.get(k,'')) for k in key_fields)
        out[key] = {
            'spend': float(r.get('spend',0)),
            'impr':  int(r.get('impr',0)),
            'clicks': int(r.get('clicks',0)),
            'lpv':    int(r.get('lpv',0) or 0),
            'ic':     int(r.get('ic',0) or 0),
            'purch':  int(r.get('v',0) or 0),
        }
    return out

BD = {
    'placement': normalize_bd(BD4_RAW.get('placement',[]),
                              ['publisher_platform','platform_position']),
    'device':    normalize_bd(BD4_RAW.get('device',[]), ['device_platform']),
    'agegender': normalize_bd(BD4_RAW.get('age_gender',[]),
                              ['age','gender'], sep='|'),
}

# === EXCLUSÕES ===
EXCLUDED_AD_IDS = set()
ADS = [a for a in ADS_RAW if a['ad_id'] not in EXCLUDED_AD_IDS]
EXCLUDED_ADS = [a for a in ADS_RAW if a['ad_id'] in EXCLUDED_AD_IDS]

# CPAs reais
CPA_META_S1 = T1['spend'] / S1['hubla_meta_ads'] if S1['hubla_meta_ads'] else 0
CPA_META_S2 = T2['spend'] / S2['hubla_meta_ads'] if S2['hubla_meta_ads'] else 0
CPA_META_S3 = T3['spend'] / S3['hubla_meta_ads'] if S3['hubla_meta_ads'] else 0
CPA_META_S4 = T4['spend'] / S4['hubla_meta_ads'] if S4['hubla_meta_ads'] else 0
CPA_TOT_S1  = T1['spend'] / S1['hubla_total'] if S1['hubla_total'] else 0
CPA_TOT_S2  = T2['spend'] / S2['hubla_total'] if S2['hubla_total'] else 0
CPA_TOT_S3  = T3['spend'] / S3['hubla_total'] if S3['hubla_total'] else 0
CPA_TOT_S4  = T4['spend'] / S4['hubla_total'] if S4['hubla_total'] else 0

# Helpers
def fmt_money(v): return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
def fmt_int(v): return f"{int(v):,}".replace(",",".")
def fmt_pct(v): return f"{v:.2f}%".replace(".",",")
def fmt_pct1(v): return f"{v:.1f}%".replace(".",",")
def fmt_freq(v): return f"{v:.2f}".replace(".",",")

def delta_html(s_prev, s_now, lower_better=False, pp=False):
    if s_prev == 0: return ''
    d = (s_now - s_prev) / s_prev * 100 if not pp else (s_now - s_prev)
    if pp:
        sign = '+' if d >= 0 else ''
        good = (d <= 0) if lower_better else (d >= 0)
        cls = 'ok' if good else 'bad'
        return f'<span class="delta {cls}">{sign}{d:.1f} pp</span>'
    sign = '+' if d >= 0 else ''
    good = (d <= 0) if lower_better else (d >= 0)
    cls = 'ok' if good else 'bad'
    return f'<span class="delta {cls}">{sign}{d:.1f}%</span>'

def derive(t):
    out = dict(t)
    out['ctr'] = t['clicks']/t['impr']*100 if t['impr'] else 0
    out['cpc'] = t['spend']/t['clicks'] if t['clicks'] else 0
    out['cpm'] = t['spend']/t['impr']*1000 if t['impr'] else 0
    out['custo_lpv'] = t['spend']/t['visitas'] if t['visitas'] else 0
    out['custo_ic']  = t['spend']/t['ic'] if t['ic'] else 0
    out['lpv_ic'] = t['ic']/t['visitas']*100 if t['visitas'] else 0
    out['ic_v']   = t['vendas']/t['ic']*100 if t['ic'] else 0
    return out
T1d = derive(T1); T2d = derive(T2); T3d = derive(T3); T4d = derive(T4)

# Classify ads (semana corrente)
def classify(r):
    if r['spend'] >= 200 and r['purch'] == 0: return ('🔴 Morto','Pausar')
    if r.get('frequency',0) > 3: return ('🟡 Fadiga','Refresh criativo')
    f = FAT4.get(r['ad_id'], {})
    chg = f.get('ctr_change_pct')
    if chg is not None and chg < -35: return ('🟡 Fadiga','Refresh criativo')
    if r['purch'] >= 5: return ('🟢 Escalar','+30-50% budget')
    if r['purch'] >= 1: return ('🟢 Convertendo','Manter')
    if r['spend'] < 50: return ('🔵 Aprendendo','Aguardar')
    if r['lpv'] >= 30 and r['purch']==0:
        if r['ic'] >= 1: return ('🟠 Sinal fraco','Trocar copy/CTA')
        return ('🟠 Sem sinal','Pausar em 24h')
    return ('⚪ Indefinido','Observar')

for r in ADS:
    r['status_tag'], r['action_rec'] = classify(r)
    m = re.search(r'AD-(\d+)', r['name'])
    key = f"AD-{int(m.group(1))}" if m else None
    r['ad_key'] = key
    mq = MQL4.get(key, {}) if key else {}
    r['mql_total'] = mq.get('total',0)
    r['mql_count'] = mq.get('mql',0)
    r['mql_pct']   = r['mql_count']/r['mql_total']*100 if r['mql_total'] else None
    f = FAT4.get(r['ad_id'], {})
    r['ctr_change_pct'] = f.get('ctr_change_pct')

# Builders
def render_kpi_grid(items):
    html = '<div class="kpi-grid">'
    for it in items:
        cls = f" {it.get('cls','')}"
        sub = f'<div class="sub">{it["sub"]}</div>' if it.get('sub') else ''
        delta = it.get('delta','')
        html += f'<div class="kpi{cls}"><div class="lbl">{it["lbl"]}</div><div class="val">{it["val"]}</div>{sub}{delta}</div>'
    html += '</div>'
    return html

def render_funnel_row(label, val, base, color, conv_label=None, conv_color='#34d399'):
    width = (val/base*100) if base else 0
    width = max(width, 1.5)
    conv = f'<span style="color:{conv_color}">{conv_label}</span>' if conv_label else '—'
    return f'<div class="step"><div class="label">{label}</div><div class="bar"><div class="fill" style="background:{color};width:{width:.1f}%">{fmt_int(val)}</div></div><div class="conv">{conv}</div></div>'

# === Sections ===

# 1. Overview KPIs (sem 4 vs sem 3)
overview_kpis = [
    {'lbl':'Investimento turma','val':fmt_money(T4['spend']),'sub':'Julho/26 - 1','delta':delta_html(T3['spend'], T4['spend'], lower_better=True)},
    {'lbl':'Vendas Hubla total','val':str(S4['hubla_total']),'sub':'todas origens','delta':delta_html(S3['hubla_total'], S4['hubla_total'])},
    {'lbl':'Vendas via meta_ads','val':str(S4['hubla_meta_ads']),'sub':'UTM Hubla','delta':delta_html(S3['hubla_meta_ads'], S4['hubla_meta_ads'])},
    {'lbl':'CPA Meta_ads','val':fmt_money(CPA_META_S4),'sub':'spend/vendas meta','cls':'warn','delta':delta_html(CPA_META_S3, CPA_META_S4, lower_better=True)},
    {'lbl':'CPA todas origens','val':fmt_money(CPA_TOT_S4),'sub':'inclui orgânico','cls':'ok','delta':delta_html(CPA_TOT_S3, CPA_TOT_S4, lower_better=True)},
    {'lbl':'CTR','val':fmt_pct(T4d['ctr']),'sub':'todos os cliques','cls':'ok','delta':delta_html(T3d['ctr'], T4d['ctr'])},
    {'lbl':'CTR (link)','val':fmt_pct(TL4.get('link_ctr',0)),'sub':'cliques no link · Meta API','cls':'ok','delta':delta_html(TL3.get('link_ctr',0), TL4.get('link_ctr',0))},
    {'lbl':'CPM','val':fmt_money(T4d['cpm']),'delta':delta_html(T3d['cpm'], T4d['cpm'], lower_better=True)},
    {'lbl':'MQL rate (compradores)','val':fmt_pct(MW4['mql_pct']),'sub':f"{MW4['mql']}/{MW4['matched']} compradores renda≥10k",'cls':'ok','delta':delta_html(MW3['mql_pct'], MW4['mql_pct'], pp=True)},
]

cost_per_step = [
    {'lbl':'CPM','val':fmt_money(TL4['cpm']),'delta':delta_html(TL3['cpm'], TL4['cpm'], lower_better=True)},
    {'lbl':'Custo / Click','val':fmt_money(TL4['cpc']),'delta':delta_html(TL3['cpc'], TL4['cpc'], lower_better=True),'cls':'ok'},
    {'lbl':'Custo / LPV','val':fmt_money(TL4['spend']/TL4['lpv'] if TL4['lpv'] else 0),'delta':delta_html(TL3['spend']/TL3['lpv'] if TL3['lpv'] else 0, TL4['spend']/TL4['lpv'] if TL4['lpv'] else 0, lower_better=True)},
    {'lbl':'Custo / IC','val':fmt_money(TL4['spend']/TL4['ic'] if TL4['ic'] else 0),'sub':'🚨 gargalo página','cls':'danger','delta':delta_html(TL3['spend']/TL3['ic'] if TL3['ic'] else 0, TL4['spend']/TL4['ic'] if TL4['ic'] else 0, lower_better=True)},
    {'lbl':'CPA Meta atrib.','val':fmt_money(TL4['cpa']),'sub':'só pixel','cls':'warn','delta':delta_html(TL3['cpa'], TL4['cpa'], lower_better=True)},
]

# 2. Comparativo Sem 3 vs Sem 4
def cmp_row(label, v_prev, v_now, fmt, lower_better=False):
    delta = delta_html(v_prev, v_now, lower_better=lower_better)
    return f'<tr><td><b>{label}</b></td><td>{fmt(v_prev)}</td><td>{fmt(v_now)}</td><td>{delta}</td></tr>'

cmp_rows = []
cmp_rows.append(cmp_row('Investimento turma', T3['spend'], T4['spend'], fmt_money, True))
cmp_rows.append(cmp_row('Vendas Hubla (todas)', S3['hubla_total'], S4['hubla_total'], lambda x: str(int(x))))
cmp_rows.append(cmp_row('Vendas via meta_ads (Hubla)', S3['hubla_meta_ads'], S4['hubla_meta_ads'], lambda x: str(int(x))))
cmp_rows.append(cmp_row('CPA real meta_ads', CPA_META_S3, CPA_META_S4, fmt_money, True))
cmp_rows.append(cmp_row('CPA real todas origens', CPA_TOT_S3, CPA_TOT_S4, fmt_money, True))
cmp_rows.append(cmp_row('Pesquisa total (respostas)', S3['pesquisa_total'], S4['pesquisa_total'], lambda x: str(int(x))))
cmp_rows.append(cmp_row('Compradores meta identificados', MW3['matched'], MW4['matched'], lambda x: str(int(x))))
cmp_rows.append(cmp_row('MQL absolutos (renda≥10k)', MW3['mql'], MW4['mql'], lambda x: str(int(x))))
cmp_rows.append(cmp_row('MQL rate (dos identificados)', MW3['mql_pct'], MW4['mql_pct'], fmt_pct))
cmp_rows.append(cmp_row('Impressões', TL3['impr'], TL4['impr'], fmt_int))
cmp_rows.append(cmp_row('Clicks', TL3['clicks'], TL4['clicks'], fmt_int))
cmp_rows.append(cmp_row('CTR', TL3['ctr'], TL4['ctr'], fmt_pct))
cmp_rows.append(cmp_row('CPM', TL3['cpm'], TL4['cpm'], fmt_money, True))
cmp_rows.append(cmp_row('CPC', TL3['cpc'], TL4['cpc'], fmt_money, True))
cmp_rows.append(cmp_row('Visitas LP', TL3['lpv'], TL4['lpv'], fmt_int))
cmp_rows.append(cmp_row('Initiate Checkout', TL3['ic'], TL4['ic'], fmt_int))
cmp_rows.append(cmp_row('Vendas Meta-pixel', TL3['purch'], TL4['purch'], fmt_int))
cmp_rows.append(cmp_row('LPV → IC', TL3['lpv_ic'], TL4['lpv_ic'], fmt_pct))
cmp_rows.append(cmp_row('IC → Venda', TL3['ic_v'], TL4['ic_v'], fmt_pct))

# 2b. Comparativo 4 semanas
def trend_row(label, v1, v2, v3, v4, fmt, lower_better=False):
    """Tabela com Sem 1..4 + Δ Sem4 vs Sem3 + Δ Sem4 vs Sem1 + setinhas."""
    d_w = delta_html(v3, v4, lower_better=lower_better)
    d_t = delta_html(v1, v4, lower_better=lower_better)
    def arrow(a, b):
        if b == a: return '<span style="color:#64748b">→</span>'
        good = (b < a) if lower_better else (b > a)
        return ('<span style="color:#34d399">↑</span>' if b > a else '<span style="color:#f87171">↓</span>') if good else ('<span style="color:#f87171">↑</span>' if b > a else '<span style="color:#34d399">↓</span>')
    trend = f'{arrow(v1,v2)} {arrow(v2,v3)} {arrow(v3,v4)}'
    return (f'<tr><td><b>{label}</b></td>'
            f'<td>{fmt(v1)}</td><td>{fmt(v2)}</td><td>{fmt(v3)}</td><td>{fmt(v4)}</td>'
            f'<td>{trend}</td>'
            f'<td>{d_w}</td><td>{d_t}</td></tr>')

trend_rows = []
trend_rows.append(trend_row('Investimento turma', T1['spend'], T2['spend'], T3['spend'], T4['spend'], fmt_money, True))
trend_rows.append(trend_row('Vendas Hubla (todas)', S1['hubla_total'], S2['hubla_total'], S3['hubla_total'], S4['hubla_total'], lambda x: str(int(x))))
trend_rows.append(trend_row('Vendas via meta_ads', S1['hubla_meta_ads'], S2['hubla_meta_ads'], S3['hubla_meta_ads'], S4['hubla_meta_ads'], lambda x: str(int(x))))
trend_rows.append(trend_row('CPA real meta_ads', CPA_META_S1, CPA_META_S2, CPA_META_S3, CPA_META_S4, fmt_money, True))
trend_rows.append(trend_row('CPA real todas origens', CPA_TOT_S1, CPA_TOT_S2, CPA_TOT_S3, CPA_TOT_S4, fmt_money, True))
trend_rows.append(trend_row('Pesquisa total (respostas)', S1['pesquisa_total'], S2['pesquisa_total'], S3['pesquisa_total'], S4['pesquisa_total'], lambda x: str(int(x))))
trend_rows.append(trend_row('Compradores meta identificados', MW1['matched'], MW2['matched'], MW3['matched'], MW4['matched'], lambda x: str(int(x))))
trend_rows.append(trend_row('MQL absolutos (renda≥10k)', MW1['mql'], MW2['mql'], MW3['mql'], MW4['mql'], lambda x: str(int(x))))
trend_rows.append(trend_row('MQL rate (dos identificados)', MW1['mql_pct'], MW2['mql_pct'], MW3['mql_pct'], MW4['mql_pct'], fmt_pct))
trend_rows.append(trend_row('Impressões', TL1['impr'], TL2['impr'], TL3['impr'], TL4['impr'], fmt_int))
trend_rows.append(trend_row('Clicks', TL1['clicks'], TL2['clicks'], TL3['clicks'], TL4['clicks'], fmt_int))
trend_rows.append(trend_row('CTR', TL1['ctr'], TL2['ctr'], TL3['ctr'], TL4['ctr'], fmt_pct))
trend_rows.append(trend_row('CPM', TL1['cpm'], TL2['cpm'], TL3['cpm'], TL4['cpm'], fmt_money, True))
trend_rows.append(trend_row('CPC', TL1['cpc'], TL2['cpc'], TL3['cpc'], TL4['cpc'], fmt_money, True))
trend_rows.append(trend_row('Visitas LP', TL1['lpv'], TL2['lpv'], TL3['lpv'], TL4['lpv'], fmt_int))
trend_rows.append(trend_row('Initiate Checkout', TL1['ic'], TL2['ic'], TL3['ic'], TL4['ic'], fmt_int))
trend_rows.append(trend_row('Vendas Meta-pixel', TL1['purch'], TL2['purch'], TL3['purch'], TL4['purch'], fmt_int))
trend_rows.append(trend_row('LPV → IC', TL1['lpv_ic'], TL2['lpv_ic'], TL3['lpv_ic'], TL4['lpv_ic'], fmt_pct))
trend_rows.append(trend_row('IC → Venda', TL1['ic_v'], TL2['ic_v'], TL3['ic_v'], TL4['ic_v'], fmt_pct))
trend_rows.append(trend_row('CPA Meta pixel', TL1['cpa'], TL2['cpa'], TL3['cpa'], TL4['cpa'], fmt_money, True))

# Acumulado das 4 semanas
TOT_SPEND = T1['spend'] + T2['spend'] + T3['spend'] + T4['spend']
TOT_VENDAS_HUBLA = S1['hubla_total'] + S2['hubla_total'] + S3['hubla_total'] + S4['hubla_total']
TOT_VENDAS_META  = S1['hubla_meta_ads'] + S2['hubla_meta_ads'] + S3['hubla_meta_ads'] + S4['hubla_meta_ads']
TOT_MQL          = MW1['mql'] + MW2['mql'] + MW3['mql'] + MW4['mql']
TOT_MATCHED      = MW1['matched'] + MW2['matched'] + MW3['matched'] + MW4['matched']
CPA_META_4W = TOT_SPEND / TOT_VENDAS_META if TOT_VENDAS_META else 0
CPA_TOT_4W  = TOT_SPEND / TOT_VENDAS_HUBLA if TOT_VENDAS_HUBLA else 0
MQL_RATE_4W = TOT_MQL / TOT_MATCHED * 100 if TOT_MATCHED else 0

trend_kpis = [
    {'lbl':'Spend últimas 4 turmas','val':fmt_money(TOT_SPEND),'sub':f'{TOT_VENDAS_HUBLA} vendas Hubla'},
    {'lbl':'Vendas via meta_ads','val':str(TOT_VENDAS_META),'sub':f'de {TOT_VENDAS_HUBLA} totais'},
    {'lbl':'CPA real meta_ads (4 turmas)','val':fmt_money(CPA_META_4W),'cls':'warn'},
    {'lbl':'CPA real todas origens (4 turmas)','val':fmt_money(CPA_TOT_4W),'cls':'ok'},
    {'lbl':'MQL rate acumulada','val':fmt_pct(MQL_RATE_4W),'sub':f'{TOT_MQL}/{TOT_MATCHED} compradores'},
]

# 3. Campanhas table
def short_name(n):
    return n.replace('[DP100K-Fp02][VENDA]','').replace('[DP100K-Fp02]','').strip('[]')

camp_sorted = sorted(CAMP4, key=lambda x: -x.get('spend',0))
camps_rows = []
for c in camp_sorted:
    if c.get('spend',0) == 0: continue
    cpa = c['spend']/c['purch'] if c.get('purch',0) else 0
    ctr = c['clicks']/c['impr']*100 if c['impr'] else 0
    cpc = c['spend']/c['clicks'] if c['clicks'] else 0
    cpm = c['spend']/c['impr']*1000 if c['impr'] else 0
    c_lpv = c['spend']/c['lpv'] if c.get('lpv',0) else 0
    c_ic  = c['spend']/c['ic'] if c.get('ic',0) else 0
    cls = 'win-hard' if c.get('purch',0) >= 10 else ('win' if c.get('purch',0)>=3 else ('warn-row' if c['spend']>200 and c.get('purch',0)==0 else ''))
    camps_rows.append(
        f'<tr class="{cls}"><td><b>{short_name(c["name"])}</b></td>'
        f'<td>{fmt_money(c["spend"])}</td><td>{fmt_int(c["impr"])}</td>'
        f'<td>{fmt_pct(ctr)}</td><td>{fmt_money(cpc)}</td><td>{fmt_money(cpm)}</td>'
        f'<td>{fmt_money(c_lpv) if c_lpv else "—"}</td><td>{fmt_money(c_ic) if c_ic else "—"}</td>'
        f'<td>{int(c.get("purch",0))}</td><td>{fmt_money(cpa) if cpa else "—"}</td></tr>'
    )

# 4. Breakdowns
def bd_table(d, cols, top_n=15):
    items = sorted(d.items(), key=lambda x: -x[1]['spend'])
    tot_s = sum(v['spend'] for k,v in items)
    rows = ''
    for k,v in items[:top_n]:
        cpa = v['spend']/v['purch'] if v['purch'] else 0
        pct = v['spend']/tot_s*100 if tot_s else 0
        cls = 'win' if v['purch']>=3 else ('warn-row' if v['spend']>200 and v['purch']==0 else ('lose' if v['spend']>500 and v['purch']==0 else ''))
        rows += (f'<tr class="{cls}"><td><b>{k}</b></td><td>{fmt_money(v["spend"])}</td>'
                 f'<td>{fmt_int(v["impr"])}</td><td>{fmt_int(v["clicks"])}</td>'
                 f'<td>{fmt_int(v["lpv"])}</td><td>{fmt_int(v["ic"])}</td>'
                 f'<td>{v["purch"]}</td><td>{fmt_money(cpa) if cpa else "—"}</td>'
                 f'<td>{fmt_pct(pct)}</td></tr>')
    head = '<tr>' + ''.join(f'<th>{c}</th>' for c in cols) + '</tr>'
    return f'<table><thead>{head}</thead><tbody>{rows}</tbody></table>'

def bd_table_agegender():
    rows = ''
    items = sorted(BD['agegender'].items(), key=lambda x: -x[1]['spend'])
    for k,v in items:
        age, gender = k.split('|')
        cpa = v['spend']/v['purch'] if v['purch'] else 0
        cls = 'win-hard' if v['purch']>=10 else ('win' if v['purch']>=3 else ('lose' if v['spend']>300 and v['purch']==0 else ''))
        rows += (f'<tr class="{cls}"><td><b>{age}</b></td><td>{gender}</td>'
                 f'<td>{fmt_money(v["spend"])}</td><td>{fmt_int(v["impr"])}</td>'
                 f'<td>{fmt_int(v["lpv"])}</td><td>{v["ic"]}</td><td>{v["purch"]}</td>'
                 f'<td>{fmt_money(cpa) if cpa else "—"}</td></tr>')
    return f'<table><thead><tr><th>Idade</th><th>Gênero</th><th>Spend</th><th>Impr</th><th>LPV</th><th>IC</th><th>V</th><th>CPA</th></tr></thead><tbody>{rows}</tbody></table>'

# 5. Top Ads 4W
TOP_RANKING = TOP_ADS_4W['ranking']
TOP_CRITERIA = TOP_ADS_4W['criteria']
TOP_15 = TOP_RANKING[:15]

def render_top_ad_card_4w(r, rank):
    thumb = best_thumb(r.get('ad_ids', []))
    purl = best_preview_url(r.get('ad_ids', []))
    name = r['name']
    code = r['ad_code']
    spend = fmt_money(r['spend_4w'])
    cpa_s = fmt_money(r['cpa_real']) if r['cpa_real'] is not None else '—'
    conv_s = fmt_pct1(r['vendas_hubla'] / r['lpv_4w'] * 100) if r.get('lpv_4w') else '—'
    cpa_meta = TOP_CRITERIA['cpa_alvo_ref']
    cpa_cls = ''
    if r['cpa_real']:
        if r['cpa_real'] <= cpa_meta * 0.7: cpa_cls = 'tag-ok'
        elif r['cpa_real'] <= cpa_meta:     cpa_cls = 'tag-warn'
        else:                                cpa_cls = 'tag-danger'
    mql_html = f'{r["mql_count"]} <span class="muted-pct">({r["mql_pct"]:.0f}% de {r["pesquisa_total"]})</span>' if r['pesquisa_total'] else '0'
    rank_cls = 'win-hard' if rank <= 3 else ('win' if rank <= 8 else '')
    preview_link = (f'<a class="prev-link" href="{purl}" target="_blank" rel="noopener" title="Abrir preview no Meta">👁</a>'
                    if purl else '')
    if thumb:
        thumb_html = (f'<img class="creative-thumb" src="{thumb}" alt="{code}" loading="lazy">'
                      if not purl else
                      f'<a href="{purl}" target="_blank" rel="noopener" title="Abrir no Meta"><img class="creative-thumb" src="{thumb}" alt="{code}" loading="lazy"></a>')
    else:
        thumb_html = '<div class="creative-noimg">Sem imagem disponível</div>'
    return f'''<div class="creative-card {rank_cls}">
    {thumb_html}
    <div class="info">
        <div class="rank-row">
            <span class="rank-pos">#{rank}</span>
            <span class="rank-score" title="Score composto (vendas 45% + MQL 25% + CPA 30%)">Score <b>{r["score_total"]}</b></span>
            {preview_link}
        </div>
        <div class="name">{name}</div>
        <div class="stats">
            <div class="stat"><div class="l">Vendas Hubla</div><div class="v">{r["vendas_hubla"]}</div></div>
            <div class="stat"><div class="l">CPA real</div><div class="v">{cpa_s}</div></div>
            <div class="stat"><div class="l">MQL</div><div class="v">{mql_html}</div></div>
            <div class="stat"><div class="l">Spend</div><div class="v">{spend}</div></div>
            <div class="stat"><div class="l">CTR link</div><div class="v">{fmt_pct(r.get("link_ctr",0))}</div></div>
            <div class="stat" title="Vendas Hubla ÷ visitas na LP"><div class="l">Conv. visita→venda</div><div class="v">{conv_s}</div></div>
        </div>
        <div class="subscores">
            <div class="ss"><span class="ssl">Vendas</span><div class="ssbar"><div class="ssfill" style="width:{r["score_vendas"]:.0f}%;background:#10b981"></div></div><span class="ssv">{r["score_vendas"]:.0f}</span></div>
            <div class="ss"><span class="ssl">MQL</span><div class="ssbar"><div class="ssfill" style="width:{r["score_mql"]:.0f}%;background:#3b82f6"></div></div><span class="ssv">{r["score_mql"]:.0f}</span></div>
            <div class="ss"><span class="ssl">CPA</span><div class="ssbar"><div class="ssfill" style="width:{r["score_cpa"]:.0f}%;background:#f59e0b"></div></div><span class="ssv">{r["score_cpa"]:.0f}</span></div>
        </div>
        <div class="badges">
            <span class="tag {cpa_cls}">CPA {cpa_s}</span>
            <span class="tag tag-neutral">{code}</span>
        </div>
    </div></div>'''

ad_grid = '<div class="creative-grid">' + ''.join(
    render_top_ad_card_4w(r, i+1) for i, r in enumerate(TOP_15)
) + '</div>'

# Tabela completa elegíveis
def fmt_cpa(v): return fmt_money(v) if v is not None else '—'
ranking_table_rows = ''
for i, r in enumerate(TOP_RANKING, 1):
    cls = 'win-hard' if i<=3 else ('win' if i<=8 else '')
    ranking_table_rows += (
        f'<tr class="{cls}"><td><b>#{i}</b></td><td><b>{r["ad_code"]}</b></td>'
        f'<td>{r["name"][:55]}</td>'
        f'<td>{r["vendas_hubla"]}</td>'
        f'<td>{fmt_pct1(r["vendas_hubla"] / r["lpv_4w"] * 100) if r.get("lpv_4w") else "—"}</td>'
        f'<td>{fmt_cpa(r["cpa_real"])}</td>'
        f'<td>{r["mql_count"]} <span class="muted-pct">/ {r["pesquisa_total"]}</span></td>'
        f'<td>{fmt_money(r["spend_4w"])}</td>'
        f'<td>{fmt_pct1(r.get("link_ctr",0))}</td>'
        f'<td><b>{r["score_total"]}</b></td>'
        f'<td>{r["score_vendas"]:.0f} · {r["score_mql"]:.0f} · {r["score_cpa"]:.0f}</td>'
        f'</tr>'
    )

# 6. Health table — 4 SEMANAS
ALL_ADS_4W = TOP_ADS_4W['all_ads']
HEALTH_CLASSIFICATION = TOP_ADS_4W['criteria']['classification']

def render_health_row_4w(r):
    sp = r['spend_4w']; vh = r['vendas_hubla']
    cpa = fmt_money(r['cpa_real']) if r['cpa_real'] is not None else '—'
    mql_str = f'{r["mql_count"]}<span class="muted-pct">/{r["pesquisa_total"]}</span>' if r['pesquisa_total'] else '0'
    if r['pesquisa_total']:
        pct = r['mql_count']/r['pesquisa_total']*100
        if pct >= 70: pct_cls = 'tag-ok'
        elif pct >= 50: pct_cls = 'tag-warn'
        elif pct > 0:   pct_cls = 'tag-danger'
        else:           pct_cls = 'tag-neutral'
        mql_pct_str = f'<span class="tag {pct_cls}">{fmt_pct1(pct)}</span>'
    else:
        mql_pct_str = '<span class="muted-pct">—</span>'
    cls = ''
    if '🔴' in r['status_tag']: cls='lose'
    elif '🟢 Escalar' in r['status_tag']: cls='win-hard'
    elif '🟢 Eficiente' in r['status_tag']: cls='win-hard'
    elif '🟢' in r['status_tag']: cls='win'
    elif '🟠' in r['status_tag']: cls='warn-row'
    purl = best_preview_url(r.get('ad_ids', []))
    prev_link = (f'<a class="prev-link" href="{purl}" target="_blank" rel="noopener" title="Abrir preview do anúncio">👁</a>'
                 if purl else '<span class="prev-na" title="Sem preview disponível">—</span>')
    return (f'<tr class="{cls}"><td>{prev_link}</td>'
            f'<td><b>{r["ad_code"]}</b></td>'
            f'<td>{r["name"][:55]}</td>'
            f'<td>{fmt_money(sp)}</td>'
            f'<td>{vh}</td>'
            f'<td>{cpa}</td>'
            f'<td>{mql_str}</td>'
            f'<td>{mql_pct_str}</td>'
            f'<td>{r["lpv_4w"]}</td>'
            f'<td>{r["ic_4w"]}</td>'
            f'<td>{fmt_pct1(r.get("link_ctr",0))}</td>'
            f'<td>{r["status_tag"]}</td>'
            f'<td>{r["action_rec"]}</td></tr>')

health_rows_4w = ''.join(render_health_row_4w(r) for r in ALL_ADS_4W if r['spend_4w'] > 0)

from collections import Counter as _C
_class_count = _C(r['status_tag'] for r in ALL_ADS_4W if r['spend_4w'] > 0)
classification_summary = ''
for tag, n in _class_count.most_common():
    classification_summary += f'<span class="class-pill">{tag} <b>{n}</b></span> '

# 7. MQL table (Sem 4 só)
mql_items = sorted(MQL4.items(), key=lambda x: -x[1]['total'])
mql_rows = ''
for k, v in mql_items[:25]:
    pct = v['mql']/v['total']*100 if v['total'] else 0
    cls = 'win-hard' if pct>=70 and v['total']>=3 else ('win' if pct>=50 and v['total']>=2 else ('warn-row' if pct<40 else ''))
    mql_rows += f'<tr class="{cls}"><td><b>{k}</b></td><td>{v["total"]}</td><td>{v["mql"]}</td><td>{fmt_pct(pct)}</td></tr>'

# Actions list — classificação 4W
actions = []
killers = [r for r in ALL_ADS_4W if '🔴' in r['status_tag']]
for r in killers[:10]:
    actions.append(('kill', f'Pausar <b>{r["ad_code"]}</b> ({r["name"][:50]}) — R$ {r["spend_4w"]:.0f} em 4 sem, 0 vendas Hubla'))
scalers = sorted([r for r in ALL_ADS_4W if '🟢 Escalar' in r['status_tag']],
                 key=lambda r: -r['vendas_hubla'])
for r in scalers[:8]:
    cpa_s = fmt_money(r['cpa_real']) if r['cpa_real'] else '—'
    actions.append(('scale', f'Escalar <b>{r["ad_code"]}</b> ({r["name"][:45]}) — {r["vendas_hubla"]} vendas Hubla, CPA {cpa_s}'))
efficient = sorted([r for r in ALL_ADS_4W if '🟢 Eficiente' in r['status_tag']],
                   key=lambda r: r['cpa_real'] or 9999)
for r in efficient[:6]:
    actions.append(('scale', f'Escalar <b>{r["ad_code"]}</b> ({r["name"][:45]}) — só {r["vendas_hubla"]} vendas mas CPA campeão {fmt_money(r["cpa_real"])}'))
refreshers = [r for r in ALL_ADS_4W if '🟠' in r['status_tag']][:6]
for r in refreshers:
    actions.append(('refresh', f'Refresh <b>{r["ad_code"]}</b> ({r["name"][:45]}) — {r["status_tag"]} (LPV {r["lpv_4w"]}, IC {r["ic_4w"]}, 0 vendas)'))

# === PERSONA — helpers parametrizados por persona dict ===
def render_origin_card(o, show_weeks=True):
    cls = ''
    if o['sales_total'] >= 30: cls = 'origin-major'
    elif o['sales_total'] >= 10: cls = 'origin-mid'
    weeks_html = ''
    if show_weeks:
        weeks_html = (f'<div class="oc-week">Sem 1: <b>{o.get("sem1",0)}</b> · '
                      f'Sem 2: <b>{o.get("sem2",0)}</b> · '
                      f'Sem 3: <b>{o.get("sem3",0)}</b> · '
                      f'Sem 4: <b>{o.get("sem4",0)}</b></div>')
    return f'''<div class="origin-card {cls}">
        <div class="oc-head">
            <div class="oc-name">{o["origin"]}</div>
            <div class="oc-sales"><b>{o["sales_total"]}</b> vendas <span class="muted-pct">({o["sales_pct"]:.1f}%)</span></div>
        </div>
        {weeks_html}
        <div class="oc-match">
            <span>Pesquisa matched: <b>{o["matched"]}/{o["sales_total"]}</b> ({o["match_pct"]:.0f}%)</span>
            <span class="oc-mql">MQL: <b>{o["mql_count"]}</b> ({o["mql_pct"]:.0f}%)</span>
        </div>
        <div class="oc-attrs">
            <div><span class="al">Idade</span><span class="av">{o["age_top"]["k"] if o["age_top"]["k"]!="—" else "—"} <span class="muted-pct">({o["age_top"]["n"]})</span></span></div>
            <div><span class="al">Gênero</span><span class="av">{o["gender_top"]["k"]} <span class="muted-pct">({o["gender_top"]["n"]})</span></span></div>
            <div><span class="al">Ocupação</span><span class="av">{o["occup_top"]["k"][:30]} <span class="muted-pct">({o["occup_top"]["n"]})</span></span></div>
            <div><span class="al">Renda</span><span class="av">{o["income_top"]["k"][:30]} <span class="muted-pct">({o["income_top"]["n"]})</span></span></div>
            <div><span class="al">Auto-percep.</span><span class="av">{o["self_top"]["k"][:30]} <span class="muted-pct">({o["self_top"]["n"]})</span></span></div>
            <div><span class="al">Desejo</span><span class="av">{o["desire_top"]["k"][:30]} <span class="muted-pct">({o["desire_top"]["n"]})</span></span></div>
        </div>
    </div>'''

def render_origin_table(bo_block, label, top_n=None):
    rows_data = bo_block['rows']
    if top_n: rows_data = rows_data[:top_n]
    origins = bo_block['origins']
    origin_totals = bo_block['origin_totals']
    head = f'<tr><th>{label}</th>' + ''.join(f'<th>{o}<br><span class="muted-pct">({origin_totals.get(o,0)})</span></th>' for o in origins) + '</tr>'
    body = ''
    for r in rows_data:
        max_pct = max((x['pct'] for x in r['by_origin']), default=0)
        cells = ''
        for x in r['by_origin']:
            cell_cls = ' best' if (x['pct'] == max_pct and x['n'] > 0 and max_pct > 0) else ''
            v = f'{x["n"]} <span class="muted-pct">({x["pct"]:.0f}%)</span>' if x['n'] > 0 else '<span class="muted-pct">—</span>'
            cells += f'<td class="origin-cell{cell_cls}">{v}</td>'
        body += f'<tr><td><b>{r["k"][:55]}</b></td>{cells}</tr>'
    return f'<table class="origin-tbl"><thead>{head}</thead><tbody>{body}</tbody></table>'

def render_voc_by_origin(voc, origins):
    blocks = ''
    for o in origins:
        v = voc.get(o, {})
        has = any(v.get(k) for k in ('thought','chall','learn','question'))
        if not has: continue
        sub = ''
        for col, title in [('thought','Pensamento ao imaginar vender palestra por R$ 5k'),
                            ('chall','Desafios pra ser palestrante memorável'),
                            ('learn','O que querem aprender no desafio'),
                            ('question','Pergunta que fariam pra Thathi')]:
            ss = v.get(col, [])
            if not ss: continue
            sub += f'<h4 style="margin-top:10px;color:#fbbf24">{title}</h4>'
            sub += '<ul class="voc-list">' + ''.join(f'<li>"{s}"</li>' for s in ss) + '</ul>'
        if sub:
            blocks += f'<div class="voc-origin"><h3 style="color:#34d399;margin-bottom:8px">🗣 {o}</h3>{sub}</div>'
    return blocks

def render_ad_persona_card(code, p):
    top_age    = (p['age_top'][0]['k']    if p['age_top']    else '—')
    top_gen    = (p['gender_top'][0]['k'] if p['gender_top'] else '—')
    top_inc    = (p['income_top'][0]['k'] if p['income_top'] else '—')
    top_occ    = (p['occup_top'][0]['k']  if p['occup_top']  else '—')
    top_self   = (p['self_top'][0]['k']   if p['self_top']   else '—')
    return f'''<div class="persona-card">
        <div class="pc-head">
            <div class="pc-code">{code}</div>
            <div class="pc-sales"><b>{p["sales_hubla"]}</b> vendas Meta</div>
        </div>
        <div class="pc-stats">
            <div><span class="l">Matched</span><span class="v">{p["matched"]}</span></div>
            <div><span class="l">MQL</span><span class="v">{p["mql_count"]} ({p["mql_pct"]:.0f}%)</span></div>
        </div>
        <div class="pc-attrs">
            <div><span class="al">Idade modal</span><span class="av">{top_age}</span></div>
            <div><span class="al">Gênero modal</span><span class="av">{top_gen}</span></div>
            <div><span class="al">Renda modal</span><span class="av">{top_inc}</span></div>
            <div><span class="al">Ocupação modal</span><span class="av">{top_occ}</span></div>
            <div><span class="al">Auto-percepção</span><span class="av">{top_self}</span></div>
        </div>
    </div>'''

def render_persona_view(view_key, persona, is_default=False):
    """Renderiza um bloco persona completo (KPIs + cards + tabelas + voc + ads).
    view_key: 'all'/'sem1'/'sem2'/'sem3'/'sem4' — usado como id do container."""
    if not persona:
        return f'<div class="persona-view{" active" if is_default else ""}" data-view="{view_key}"><div class="callout danger">Sem dados nesta semana.</div></div>'
    P_TOT  = persona['totals']
    P_SUM  = persona['origins_summary']
    P_BO   = persona['by_origin']
    P_VOC  = persona['voc_by_origin']
    P_ADS  = persona['ad_personas']
    P_ORIGINS = persona['origins_view']
    period = persona['window']
    n_weeks = len(persona['weeks'])
    show_weeks_in_card = n_weeks > 1

    label_w = '4W' if n_weeks == 4 else f'Sem {persona["weeks"][0]}'

    kpis = [
        {'lbl':f'Vendas Hubla ({label_w})','val':str(P_TOT['hubla_total']),'sub':'todas as origens'},
        {'lbl':'Compradoras com pesquisa','val':str(P_TOT['buyer_matched']),'sub':f"{P_TOT['match_pct']:.1f}% match"},
        {'lbl':'Compradoras MQL','val':str(P_TOT['all_buyers_mql']),'sub':f"{P_TOT['all_buyers_mql_pct']:.1f}% das matched",'cls':'ok'},
        {'lbl':'Origens distintas','val':str(len(P_SUM))},
    ]
    active_cls = ' active' if is_default else ''
    return f'''<div class="persona-view{active_cls}" data-view="{view_key}">
<p class="muted">Janela: <b>{period}</b> · <b>{P_TOT["hubla_total"]}</b> compradoras Hubla · {P_TOT["buyer_matched"]} ({P_TOT["match_pct"]:.1f}%) responderam à pesquisa.</p>

{render_kpi_grid(kpis)}

<h3>Compradoras por origem — resumo executivo</h3>
<p class="muted">Cada card = um canal de venda. Mostra volume{(", distribuição semanal (S1-S4)" if show_weeks_in_card else "")}, taxa de MQL e os <b>atributos modais</b> (mais frequentes) da compradora desse canal.</p>
<div class="origin-grid">
{''.join(render_origin_card(o, show_weeks=show_weeks_in_card) for o in P_SUM)}
</div>

<h3>Comparativo por atributo (todas origens, lado a lado)</h3>
<p class="muted">Linha = valor da resposta · Coluna = canal de venda · Célula verde-escura = origem onde aquele valor é <b>mais representativo</b>.</p>

<h3 style="font-size:14px;color:#fbbf24">Idade</h3>
{render_origin_table(P_BO['age'], 'Faixa etária')}

<h3 style="font-size:14px;color:#fbbf24">Gênero</h3>
{render_origin_table(P_BO['gender'], 'Gênero')}

<h3 style="font-size:14px;color:#fbbf24">Renda mensal</h3>
{render_origin_table(P_BO['income'], 'Faixa de renda')}

<h3 style="font-size:14px;color:#fbbf24">Ocupação</h3>
{render_origin_table(P_BO['occup'], 'Ocupação', 14)}

<h3 style="font-size:14px;color:#fbbf24">Auto-percepção (quando se fala de palestras)</h3>
{render_origin_table(P_BO['self'], 'Como se vê')}

<h3 style="font-size:14px;color:#fbbf24">Desejo principal</h3>
{render_origin_table(P_BO['desire'], 'O que quer alcançar')}

<h3 style="font-size:14px;color:#fbbf24">Há quanto tempo conhece a Thathi</h3>
{render_origin_table(P_BO['time'], 'Tempo')}

<h3 style="font-size:14px;color:#fbbf24">Já participou antes</h3>
{render_origin_table(P_BO['prev'], 'Participou')}

<h3 style="font-size:14px;color:#fbbf24">Estado</h3>
{render_origin_table(P_BO['state'], 'UF')}

<h3>Persona por ad campeão — apenas Meta Ads</h3>
<p class="muted">Para os ads que mais venderam dentro do Meta, o perfil das compradoras que cada criativo atraiu (cruzando com a pesquisa).</p>
<div class="persona-grid">
{''.join(render_ad_persona_card(code, p) for code, p in P_ADS.items()) or '<div class="callout">Sem matches suficientes para gerar persona por ad nesta janela.</div>'}
</div>

<h3>🗣 Voz da compradora — por origem</h3>
<p class="muted">Trechos reais das respostas long-text das compradoras que responderam à pesquisa, agrupados por canal.</p>
{render_voc_by_origin(P_VOC, P_ORIGINS)}
</div>'''

PERSONA_VIEWS_HTML = render_persona_view('all', PERSONA_BW['all'], is_default=True)

# Funnel HTML
funnel_html = ''.join([
    render_funnel_row('Impressões', TL4['impr'], TL4['impr'], '#0ea5e9', None),
    render_funnel_row('Cliques no link', TL4.get('link_clicks',0) or TL4['clicks'], TL4['impr'], '#3b82f6', f'CTR link: {fmt_pct(TL4.get("link_ctr",0))}', '#34d399'),
    render_funnel_row('Visitas LP', TL4['lpv'], TL4['impr'], '#8b5cf6', None, '#34d399'),
    render_funnel_row('Initiate Checkout', TL4['ic'], TL4['impr'], '#dc2626', f'LPV→IC: {fmt_pct(TL4["lpv_ic"])}', '#f87171' if TL4['lpv_ic']<6 else '#34d399'),
    render_funnel_row('Vendas (atrib. Meta)', TL4['purch'], TL4['impr'], '#10b981', f'IC→Venda: {fmt_pct(TL4["ic_v"])}', '#34d399'),
])

# === Gráfico de linha diário (SVG inline, offline) ===
import math
def _nice_max(m):
    if m <= 0: return 1
    exp = math.floor(math.log10(m)); base = 10**exp
    for f in (1, 2, 2.5, 5, 10):
        if m <= f*base: return f*base
    return 10*base
def _money_k(v):
    if v >= 1000: return ('R$ %.1fk' % (v/1000)).replace('.', ',')
    return 'R$ %.0f' % v

def render_daily_chart(days, spend_by, l1_by, l1_lbl, l1_col, l2_by=None, l2_lbl=None, l2_col=None):
    W, H = 1080, 380
    ml, mr, mt, mb = 70, 52, 52, 54
    pw, ph = W-ml-mr, H-mt-mb
    n = len(days); slot = pw/max(n, 1)
    spend_vals = [spend_by.get(d, 0) for d in days]
    l1_vals = [l1_by.get(d, 0) for d in days]
    l2_vals = [l2_by.get(d, 0) for d in days] if l2_by else []
    smax = _nice_max(max(spend_vals+[1]))
    vmax = _nice_max(max(l1_vals+l2_vals+[1]))
    def ys(v): return mt+ph*(1-v/smax)
    def yv(v): return mt+ph*(1-v/vmax)
    def cx(i): return ml+slot*(i+0.5)
    base = mt+ph
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" style="background:#0f172a;border:1px solid #334155;border-radius:10px;font-family:inherit">']
    for g in range(5):
        y = mt+ph*g/4
        p.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+pw}" y2="{y:.1f}" stroke="#1e293b" stroke-width="1"/>')
        p.append(f'<text x="{ml-8}" y="{y+4:.1f}" text-anchor="end" font-size="10" fill="#f59e0b">{_money_k(smax*(1-g/4))}</text>')
        p.append(f'<text x="{ml+pw+8}" y="{y+4:.1f}" text-anchor="start" font-size="10" fill="#34d399">{vmax*(1-g/4):.0f}</text>')
    bw = slot*0.46
    for i, d in enumerate(days):
        v = spend_vals[i]; x = cx(i)-bw/2; y = ys(v)
        p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{base-y:.1f}" fill="rgba(245,158,11,.30)" stroke="#f59e0b" stroke-width="1" rx="2"><title>{d}: {fmt_money(v)}</title></rect>')
    for i, d in enumerate(days):
        p.append(f'<text x="{cx(i):.1f}" y="{base+18:.1f}" text-anchor="middle" font-size="10" fill="#94a3b8">{d[8:10]}/{d[5:7]}</text>')
    def polyline(vals, col, dash=''):
        pts = ' '.join(f'{cx(i):.1f},{yv(v):.1f}' for i, v in enumerate(vals))
        dd = f' stroke-dasharray="{dash}"' if dash else ''
        return f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5"{dd}/>'
    if l2_by:
        p.append(polyline(l2_vals, l2_col, dash='5,4'))
        for i, v in enumerate(l2_vals):
            p.append(f'<circle cx="{cx(i):.1f}" cy="{yv(v):.1f}" r="3" fill="{l2_col}"><title>{days[i]}: {l2_lbl} {v:.0f}</title></circle>')
    p.append(polyline(l1_vals, l1_col))
    for i, v in enumerate(l1_vals):
        p.append(f'<circle cx="{cx(i):.1f}" cy="{yv(v):.1f}" r="4" fill="{l1_col}"><title>{days[i]}: {l1_lbl} {v:.0f}</title></circle>')
        p.append(f'<text x="{cx(i):.1f}" y="{yv(v)-9:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="{l1_col}">{v:.0f}</text>')
    ly = mt-30
    p.append(f'<rect x="{ml}" y="{ly}" width="12" height="12" fill="rgba(245,158,11,.30)" stroke="#f59e0b"/><text x="{ml+18}" y="{ly+11}" font-size="11" fill="#cbd5e1">Investimento (eixo esq.)</text>')
    lx2 = ml+200
    p.append(f'<line x1="{lx2}" y1="{ly+6}" x2="{lx2+16}" y2="{ly+6}" stroke="{l1_col}" stroke-width="3"/><text x="{lx2+22}" y="{ly+11}" font-size="11" fill="#cbd5e1">{l1_lbl} (eixo dir.)</text>')
    if l2_by:
        lx3 = lx2+230
        p.append(f'<line x1="{lx3}" y1="{ly+6}" x2="{lx3+16}" y2="{ly+6}" stroke="{l2_col}" stroke-width="3" stroke-dasharray="5,4"/><text x="{lx3+22}" y="{ly+11}" font-size="11" fill="#cbd5e1">{l2_lbl} (eixo dir.)</text>')
    p.append('</svg>')
    return ''.join(p)

# Dados diários — overall (Visão Geral)
DD = DAILY['days']
_ov_spend = {d: DAILY['overall'][d]['spend'] for d in DD}
_ov_vmeta = {d: DAILY['hubla_overall'][d]['vendas_meta'] for d in DD}
_ov_vtot  = {d: DAILY['hubla_overall'][d]['vendas_total'] for d in DD}
daily_chart_html = render_daily_chart(DD, _ov_spend, _ov_vmeta, 'Vendas meta (Hubla)', '#34d399',
                                      _ov_vtot, 'Vendas totais (Hubla)', '#38bdf8')
daily_table_rows = ''
for d in DD:
    sp = DAILY['overall'][d]['spend']; vm = DAILY['hubla_overall'][d]['vendas_meta']
    vt = DAILY['hubla_overall'][d]['vendas_total']; px = DAILY['overall'][d]['purch']
    lpv = DAILY['overall'][d]['lpv']; ic = DAILY['overall'][d]['ic']
    cpa = sp/vm if vm else 0
    daily_table_rows += (f'<tr><td><b>{d[8:10]}/{d[5:7]}</b></td><td>{fmt_money(sp)}</td>'
                         f'<td>{vm}</td><td>{vt}</td><td>{fmt_money(cpa) if cpa else "—"}</td>'
                         f'<td>{fmt_int(lpv)}</td><td>{ic}</td><td>{px}</td></tr>')

# === QUIZ — recorte das campanhas de quiz ===
ALL_ADS_BY_CODE = {r['ad_code']: r for r in TOP_ADS_4W['all_ads']}
QUIZ_CAMPS = [c for c in CAMP4 if 'QUIZ' in c.get('name', '').upper() and c.get('spend', 0) > 0]
quiz_ad_rows = [a for a in ADS if 'QUIZ' in (a.get('campaign_name', '') or '').upper() and a.get('spend', 0) > 0]
quiz_code_ids = defaultdict(list)
quiz_code_meta = defaultdict(lambda: dict(spend=0, lpv=0, ic=0, purch=0, impr=0, link_clicks=0))
for a in quiz_ad_rows:
    m = re.search(r'AD-(\d+)', a.get('name', ''))
    code = f"AD-{int(m.group(1))}" if m else None
    if not code: continue
    quiz_code_ids[code].append(a['ad_id'])
    qm = quiz_code_meta[code]
    for k in ('spend', 'lpv', 'ic', 'purch', 'impr', 'link_clicks'):
        qm[k] += a.get(k, 0) or 0

quiz_codes_sorted = sorted(quiz_code_meta.keys(),
                           key=lambda c: -(ALL_ADS_BY_CODE.get(c, {}).get('vendas_hubla', 0)))
Q_spend  = sum(v['spend'] for v in quiz_code_meta.values())
Q_lpv    = sum(v['lpv']   for v in quiz_code_meta.values())
Q_ic     = sum(v['ic']    for v in quiz_code_meta.values())
Q_pixel  = sum(v['purch'] for v in quiz_code_meta.values())
Q_vendas = sum(ALL_ADS_BY_CODE.get(c, {}).get('vendas_hubla', 0) for c in quiz_code_meta)
Q_mql    = sum((MQL4.get(c, {}) or {}).get('mql', 0) for c in quiz_code_meta)
Q_cpa    = Q_spend/Q_vendas if Q_vendas else 0
Q_lpvic  = Q_ic/Q_lpv*100 if Q_lpv else 0
Q_icv    = Q_pixel/Q_ic*100 if Q_ic else 0
# Direto (não-quiz) p/ comparação
DIR_spend  = TL4['spend'] - Q_spend
DIR_vendas = S4['hubla_meta_ads'] - Q_vendas
DIR_cpa    = DIR_spend/DIR_vendas if DIR_vendas else 0
QUIZ_SHARE = Q_vendas/S4['hubla_meta_ads']*100 if S4['hubla_meta_ads'] else 0

quiz_kpis = [
    {'lbl':'Investimento quiz','val':fmt_money(Q_spend),'sub':f'{len(quiz_codes_sorted)} ads com spend'},
    {'lbl':'Vendas (Hubla)','val':str(Q_vendas),'sub':f'{fmt_pct1(QUIZ_SHARE)} das vendas meta','cls':'ok'},
    {'lbl':'CPA real','val':fmt_money(Q_cpa),'sub':'spend ÷ vendas Hubla','cls':'warn'},
    {'lbl':'MQL (renda≥10k)','val':str(Q_mql),'cls':'ok'},
    {'lbl':'Visitas quiz (LPV)','val':fmt_int(Q_lpv)},
    {'lbl':'Checkout (IC)','val':fmt_int(Q_ic),'sub':f'Visita→IC {fmt_pct(Q_lpvic)}'},
    {'lbl':'Compras pixel','val':str(Q_pixel),'sub':f'IC→Compra {fmt_pct(Q_icv)}'},
]
quiz_funnel_html = ''.join([
    render_funnel_row('Visitas quiz (LPV)', Q_lpv, Q_lpv or 1, '#8b5cf6', None),
    render_funnel_row('Initiate Checkout', Q_ic, Q_lpv or 1, '#dc2626', f'Visita→IC: {fmt_pct(Q_lpvic)}', '#f87171' if Q_lpvic<6 else '#34d399'),
    render_funnel_row('Compras (pixel)', Q_pixel, Q_lpv or 1, '#10b981', f'IC→Compra: {fmt_pct(Q_icv)}', '#34d399'),
])
_q_spend_by = {d: DAILY['quiz'][d]['spend'] for d in DD}
_q_vendas_by = {d: DAILY['hubla_quiz'][d] for d in DD}
_q_pixel_by = {d: DAILY['quiz'][d]['purch'] for d in DD}
quiz_chart_html = render_daily_chart(DD, _q_spend_by, _q_vendas_by, 'Vendas quiz (Hubla)', '#34d399',
                                     _q_pixel_by, 'Compras pixel', '#38bdf8')

def render_quiz_ad_card(code):
    r = ALL_ADS_BY_CODE.get(code, {})
    qm = quiz_code_meta[code]
    thumb = best_thumb(quiz_code_ids[code])
    purl  = best_preview_url(quiz_code_ids[code])
    vendas = r.get('vendas_hubla', 0); cpa = r.get('cpa_real')
    mql = (MQL4.get(code, {}) or {}).get('mql', 0)
    cpa_s = fmt_money(cpa) if cpa else '—'
    lpvic = qm['ic']/qm['lpv']*100 if qm['lpv'] else 0
    if thumb:
        img = f'<img class="creative-thumb" src="{thumb}" alt="{code}" loading="lazy">'
        thumb_html = f'<a href="{purl}" target="_blank" rel="noopener">{img}</a>' if purl else img
    else:
        thumb_html = '<div class="creative-noimg">Sem imagem</div>'
    cls = 'win-hard' if vendas >= 5 else ('win' if vendas >= 1 else '')
    return f'''<div class="creative-card {cls}">{thumb_html}<div class="info">
    <div class="name">{code} <span class="muted-pct">{r.get("name","")[:34]}</span></div>
    <div class="stats">
        <div class="stat"><div class="l">Vendas Hubla</div><div class="v">{vendas}</div></div>
        <div class="stat"><div class="l">CPA real</div><div class="v">{cpa_s}</div></div>
        <div class="stat"><div class="l">Visitas quiz</div><div class="v">{fmt_int(qm["lpv"])}</div></div>
        <div class="stat"><div class="l">Checkout</div><div class="v">{qm["ic"]}</div></div>
        <div class="stat"><div class="l">Compras pixel</div><div class="v">{qm["purch"]}</div></div>
        <div class="stat"><div class="l">MQL</div><div class="v">{mql}</div></div>
        <div class="stat"><div class="l">Spend</div><div class="v">{fmt_money(qm["spend"])}</div></div>
        <div class="stat"><div class="l">Visita→IC</div><div class="v">{fmt_pct1(lpvic)}</div></div>
    </div></div></div>'''
quiz_cards = '<div class="creative-grid">' + ''.join(render_quiz_ad_card(c) for c in quiz_codes_sorted) + '</div>'

quiz_table_rows = ''
for code in quiz_codes_sorted:
    r = ALL_ADS_BY_CODE.get(code, {}); qm = quiz_code_meta[code]
    vendas = r.get('vendas_hubla', 0); cpa = r.get('cpa_real')
    mql = (MQL4.get(code, {}) or {}).get('mql', 0)
    lpvic = qm['ic']/qm['lpv']*100 if qm['lpv'] else 0
    cls = 'win-hard' if vendas >= 5 else ('win' if vendas >= 1 else ('warn-row' if qm['spend'] > 200 else ''))
    quiz_table_rows += (f'<tr class="{cls}"><td><b>{code}</b></td><td>{fmt_money(qm["spend"])}</td>'
                        f'<td>{fmt_int(qm["lpv"])}</td><td>{qm["ic"]}</td><td>{fmt_pct1(lpvic)}</td>'
                        f'<td>{qm["purch"]}</td><td>{vendas}</td>'
                        f'<td>{fmt_money(cpa) if cpa else "—"}</td><td>{mql}</td></tr>')

# === HTML Template ===
CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
html,body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:#0f172a;color:#e2e8f0;line-height:1.5}
.wrap{max-width:1480px;margin:0 auto;padding:24px}
header.hero{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);padding:32px 24px;border-radius:12px;margin-bottom:24px;border:1px solid #334155}
header.hero h1{font-size:32px;margin-bottom:8px;color:#f8fafc}
header.hero .sub{color:#94a3b8;font-size:14px}
header.hero .meta{margin-top:14px;display:flex;gap:24px;flex-wrap:wrap;font-size:13px;color:#cbd5e1}
header.hero .meta b{color:#fbbf24}
nav.tabs{display:flex;gap:4px;background:#1e293b;border-radius:10px;padding:6px;margin-bottom:24px;overflow-x:auto;position:sticky;top:0;z-index:100}
nav.tabs button{flex:1;min-width:140px;background:transparent;color:#94a3b8;border:none;padding:14px 16px;font-size:14px;font-weight:600;cursor:pointer;border-radius:8px;transition:all .2s;text-align:center;white-space:nowrap}
nav.tabs button:hover{color:#f8fafc;background:#334155}
nav.tabs button.active{background:#f59e0b;color:#0f172a}
section{display:none;animation:fadeIn .25s ease-out}
section.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
h2{font-size:22px;margin:0 0 6px;color:#f8fafc;display:flex;align-items:center;gap:10px}
h2::before{content:"";width:5px;height:24px;background:#f59e0b;border-radius:3px}
h3{font-size:16px;margin:24px 0 10px;color:#e2e8f0;font-weight:600}
p.muted{color:#94a3b8;font-size:13px;margin-bottom:14px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:14px 0}
.kpi{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:18px;transition:all .2s;position:relative}
.kpi:hover{border-color:#f59e0b}
.kpi .lbl{font-size:11px;text-transform:uppercase;color:#94a3b8;letter-spacing:1px;margin-bottom:6px}
.kpi .val{font-size:24px;font-weight:700;color:#f8fafc}
.kpi .sub{font-size:11px;color:#64748b;margin-top:4px}
.kpi .delta{font-size:11px;font-weight:600;display:inline-block;margin-top:6px;padding:2px 6px;border-radius:4px}
.kpi .delta.ok{color:#34d399;background:rgba(52,211,153,.12)}
.kpi .delta.bad{color:#f87171;background:rgba(248,113,113,.12)}
.kpi.warn .val{color:#fbbf24}
.kpi.danger .val{color:#f87171}
.kpi.ok .val{color:#34d399}
table{width:100%;border-collapse:collapse;background:#1e293b;border-radius:10px;overflow:hidden;margin:12px 0;font-size:13px}
thead{background:#0f172a}
th{padding:12px 14px;text-align:left;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;border-bottom:2px solid #334155}
td{padding:12px 14px;border-bottom:1px solid #334155}
tr:last-child td{border-bottom:none}
tr:hover td{background:#293548}
tr.win td{background:rgba(52,211,153,.05);border-left:3px solid #34d399}
tr.win-hard td{background:rgba(52,211,153,.12);border-left:3px solid #10b981;font-weight:600}
tr.lose td{background:rgba(248,113,113,.05);border-left:3px solid #f87171}
tr.warn-row td{background:rgba(251,191,36,.05);border-left:3px solid #fbbf24}
.tag{display:inline-block;padding:3px 8px;border-radius:4px;font-size:11px;font-weight:600;white-space:nowrap}
.tag-ok{background:#10b981;color:#fff}
.tag-warn{background:#f59e0b;color:#0f172a}
.tag-danger{background:#dc2626;color:#fff}
.tag-neutral{background:#475569;color:#fff}
.callout{background:#1e293b;border-left:4px solid #f59e0b;padding:14px 18px;border-radius:6px;margin:14px 0;font-size:13px}
.callout.danger{border-color:#dc2626;background:rgba(220,38,38,.08)}
.callout.ok{border-color:#10b981;background:rgba(16,185,129,.08)}
.callout b{color:#fbbf24}
.callout.danger b{color:#f87171}
.callout.ok b{color:#34d399}
.funnel{margin:20px 0}
.funnel .step{margin:8px 0;display:flex;align-items:center;gap:14px;font-size:13px}
.funnel .step .label{flex:0 0 180px;font-weight:600}
.funnel .step .bar{flex:1;background:#1e293b;border-radius:6px;overflow:hidden;height:32px;border:1px solid #334155;position:relative}
.funnel .step .bar .fill{height:100%;display:flex;align-items:center;padding-left:12px;color:#fff;font-weight:600;font-size:13px}
.funnel .step .conv{flex:0 0 200px;font-weight:700;font-size:13px;text-align:right}
.creative-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:14px}
.creative-card{background:#1e293b;border:1px solid #334155;border-radius:10px;overflow:hidden;transition:all .2s;display:flex;flex-direction:column}
.creative-card:hover{border-color:#f59e0b;transform:translateY(-2px)}
.creative-card.win{border-color:#10b981}
.creative-card.lose{border-color:#dc2626;opacity:.85}
.creative-card iframe{width:100%;height:540px;border:none;background:#0f172a;border-bottom:1px solid #334155}
.creative-card .creative-thumb{width:100%;height:420px;object-fit:contain;background:#0f172a;border-bottom:1px solid #334155;display:block}
.creative-card .creative-noimg{height:420px;display:flex;align-items:center;justify-content:center;color:#64748b;background:#0f172a;border-bottom:1px solid #334155}
.creative-card .info{padding:14px}
.creative-card .name{font-size:13px;font-weight:700;color:#f8fafc;margin-bottom:4px}
.creative-card .stats{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:10px;font-size:12px}
.creative-card .stat{background:#0f172a;padding:6px 8px;border-radius:4px}
.creative-card .stat .l{color:#64748b;font-size:10px;text-transform:uppercase}
.creative-card .stat .v{color:#f8fafc;font-weight:600}
.creative-card .badges{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
ol li,ul li{margin-bottom:6px;color:#cbd5e1}
ol li b,ul li b{color:#f8fafc}
.col2{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:14px 0}
@media(max-width:768px){.col2{grid-template-columns:1fr}}
pre.copy{background:#0f172a;border:1px solid #334155;padding:18px;border-radius:8px;color:#e2e8f0;font-size:13px;line-height:1.7;white-space:pre-wrap;font-family:Menlo,Consolas,monospace;overflow-x:auto}
footer{margin-top:40px;padding:20px;text-align:center;color:#64748b;font-size:12px;border-top:1px solid #334155}
.actions-list{background:#1e293b;border-left:4px solid #f59e0b;padding:14px 18px;border-radius:6px;margin:14px 0}
.actions-list .item{padding:8px 0;border-bottom:1px solid #334155;font-size:13px}
.actions-list .item:last-child{border-bottom:none}
.actions-list .item.kill{color:#fca5a5}
.actions-list .item.scale{color:#86efac}
.actions-list .item.refresh{color:#fde68a}
.prev-link{display:inline-block;width:24px;height:24px;line-height:22px;text-align:center;border-radius:6px;background:#0f172a;border:1px solid #334155;color:#fbbf24;text-decoration:none;font-size:13px;transition:all .15s}
.prev-link:hover{background:#f59e0b;color:#0f172a;border-color:#f59e0b}
.prev-na{color:#475569;font-size:13px}
.muted-pct{color:#64748b;font-size:11px}
.voc-list{margin:8px 0 14px 0;padding-left:18px}
.voc-list li{margin-bottom:8px;font-size:13px;color:#cbd5e1;font-style:italic;line-height:1.5}
.persona-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-top:14px}
.persona-card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px}
.persona-card:hover{border-color:#f59e0b}
.persona-card .pc-head{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #334155;padding-bottom:8px;margin-bottom:10px}
.persona-card .pc-code{font-weight:700;color:#fbbf24;font-size:15px}
.persona-card .pc-sales{font-size:12px;color:#cbd5e1}
.persona-card .pc-sales b{color:#34d399;font-size:16px}
.persona-card .pc-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:10px}
.persona-card .pc-stats div{background:#0f172a;padding:6px 8px;border-radius:4px;display:flex;flex-direction:column}
.persona-card .pc-stats .l{font-size:10px;color:#64748b;text-transform:uppercase}
.persona-card .pc-stats .v{font-size:13px;color:#f8fafc;font-weight:600;margin-top:2px}
.persona-card .pc-attrs div{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid #1e293b}
.persona-card .pc-attrs div:last-child{border-bottom:none}
.persona-card .pc-attrs .al{color:#94a3b8}
.persona-card .pc-attrs .av{color:#e2e8f0;font-weight:600;text-align:right;max-width:60%}
.origin-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;margin:14px 0 22px 0}
.origin-card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px;transition:all .15s}
.origin-card:hover{border-color:#f59e0b}
.origin-card.origin-major{border-left:4px solid #f59e0b}
.origin-card.origin-mid{border-left:4px solid #34d399}
.origin-card .oc-head{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #334155;padding-bottom:8px;margin-bottom:10px}
.origin-card .oc-name{font-weight:700;color:#fbbf24;font-size:15px}
.origin-card .oc-sales{font-size:12px;color:#cbd5e1}
.origin-card .oc-sales b{color:#f8fafc;font-size:18px}
.origin-card .oc-week{font-size:11px;color:#94a3b8;margin-bottom:10px;padding-bottom:8px;border-bottom:1px dashed #334155}
.origin-card .oc-week b{color:#e2e8f0}
.origin-card .oc-match{display:flex;justify-content:space-between;font-size:12px;color:#94a3b8;margin-bottom:10px}
.origin-card .oc-match b{color:#e2e8f0}
.origin-card .oc-match .oc-mql b{color:#34d399}
.origin-card .oc-attrs div{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid #0f172a}
.origin-card .oc-attrs div:last-child{border-bottom:none}
.origin-card .oc-attrs .al{color:#94a3b8;flex:0 0 80px}
.origin-card .oc-attrs .av{color:#e2e8f0;font-weight:600;text-align:right;flex:1;font-size:12px}
.origin-tbl th,.origin-tbl td{font-size:12px;padding:8px 10px}
.origin-tbl .origin-cell.best{background:rgba(52,211,153,.15);font-weight:700;color:#f8fafc}
.voc-origin{background:#0f172a;border:1px solid #334155;border-radius:10px;padding:14px 18px;margin:14px 0}
.rank-row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
.rank-pos{background:#f59e0b;color:#0f172a;font-weight:800;padding:3px 10px;border-radius:6px;font-size:12px}
.rank-score{font-size:12px;color:#94a3b8}
.rank-score b{color:#fbbf24;font-size:14px}
.subscores{margin:10px 0 8px;display:flex;flex-direction:column;gap:4px}
.subscores .ss{display:flex;align-items:center;gap:6px;font-size:11px}
.subscores .ssl{flex:0 0 50px;color:#94a3b8;text-transform:uppercase;font-size:10px}
.subscores .ssbar{flex:1;height:8px;background:#0f172a;border-radius:4px;overflow:hidden;border:1px solid #1e293b}
.subscores .ssfill{height:100%;transition:width .3s}
.subscores .ssv{flex:0 0 26px;text-align:right;color:#e2e8f0;font-weight:600;font-size:11px}
.criteria-box{background:#0f172a;border:1px dashed #334155;border-radius:8px;padding:12px 16px;margin:10px 0;font-size:12px;color:#94a3b8}
.criteria-box b{color:#fbbf24}
.criteria-box .crit-item{margin:4px 0}
.class-pill{display:inline-block;background:#0f172a;border:1px solid #334155;border-radius:6px;padding:6px 10px;font-size:12px;color:#cbd5e1;margin:3px 6px 3px 0}
.class-pill b{color:#fbbf24;margin-left:4px}
.persona-filters{display:flex;gap:6px;flex-wrap:wrap;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;margin:14px 0 18px 0}
.persona-filters .pf-btn{background:transparent;border:1px solid #334155;color:#94a3b8;padding:8px 14px;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s}
.persona-filters .pf-btn:hover{color:#f8fafc;border-color:#475569}
.persona-filters .pf-btn.active{background:#f59e0b;color:#0f172a;border-color:#f59e0b}
.persona-view{display:none;animation:fadeIn .25s ease-out}
.persona-view.active{display:block}
th[data-sortable]{cursor:pointer;user-select:none;position:relative;padding-right:22px;transition:color .15s}
th[data-sortable]:hover{color:#f8fafc}
th[data-sortable]::after{content:"⇅";position:absolute;right:8px;top:50%;transform:translateY(-50%);font-size:10px;opacity:.45;color:#64748b}
th[data-sortable].sorted-asc::after{content:"▲";opacity:1;color:#fbbf24}
th[data-sortable].sorted-desc::after{content:"▼";opacity:1;color:#fbbf24}
'''

JS = '''
const tabs = document.querySelectorAll('nav.tabs button');
const secs = document.querySelectorAll('section');
tabs.forEach(t => t.addEventListener('click', () => {
  tabs.forEach(x=>x.classList.remove('active'));
  secs.forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById(t.dataset.tab).classList.add('active');
}));

// Persona week filters
const pfBtns  = document.querySelectorAll('.persona-filters .pf-btn');
const pfViews = document.querySelectorAll('.persona-view');
pfBtns.forEach(b => b.addEventListener('click', () => {
  pfBtns.forEach(x=>x.classList.remove('active'));
  pfViews.forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  document.querySelector('.persona-view[data-view="'+b.dataset.view+'"]').classList.add('active');
}));

// Sortable tables — toda <table> com <thead><tbody> vira sortable
function parseCellValue(s){
  s = (s || '').trim().replace(/\\s+/g,' ');
  if (s === '' || s === '—') return -Infinity; // empties last em asc, first em desc
  // R$ X.XXX,XX  ou  -R$ X,XX
  let m = s.match(/^-?\\s*R\\$?\\s*([\\d.,]+)/);
  if (m) {
    const sign = s.trim().startsWith('-') ? -1 : 1;
    return sign * parseFloat(m[1].replace(/\\./g,'').replace(',','.'));
  }
  // XX,XX%  ou  +X.X pp
  m = s.match(/^([+\\-]?[\\d.,]+)\\s*(%|pp)/);
  if (m) return parseFloat(m[1].replace(/\\./g,'').replace(',','.'));
  // Número puro com separador de milhar por ponto (formato BR)
  if (/^-?[\\d]{1,3}(\\.[\\d]{3})+$/.test(s.split(' ')[0])) {
    return parseFloat(s.split(' ')[0].replace(/\\./g,''));
  }
  // Número decimal com vírgula (formato BR)
  if (/^-?[\\d.]*,[\\d]+$/.test(s.split(' ')[0])) {
    return parseFloat(s.split(' ')[0].replace(/\\./g,'').replace(',','.'));
  }
  // Inteiro simples
  if (/^-?\\d+$/.test(s.split(' ')[0])) return parseInt(s.split(' ')[0], 10);
  // AD-XX como número (pra ordenar por código numericamente)
  m = s.match(/^#?AD-(\\d+)/i);
  if (m) return parseInt(m[1], 10);
  // #1, #2... ranking
  m = s.match(/^#(\\d+)/);
  if (m) return parseInt(m[1], 10);
  return s.toLowerCase();
}

function sortTable(th, table){
  const idx = parseInt(th.dataset.col, 10);
  const tbody = table.querySelector('tbody');
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const curDir = th.dataset.sortDir;
  // primeiro clique numa coluna numérica = desc (mais comum em métricas)
  const sample = parseCellValue(rows[0]?.children[idx]?.innerText || '');
  const isNumeric = typeof sample === 'number' && isFinite(sample);
  const dir = curDir === 'desc' ? 'asc' : (curDir === 'asc' ? 'desc' : (isNumeric ? 'desc' : 'asc'));
  rows.sort((a, b) => {
    const va = parseCellValue(a.children[idx]?.innerText || '');
    const vb = parseCellValue(b.children[idx]?.innerText || '');
    if (typeof va === 'number' && typeof vb === 'number') {
      return dir === 'asc' ? va - vb : vb - va;
    }
    return dir === 'asc'
      ? String(va).localeCompare(String(vb), 'pt-BR', {numeric:true})
      : String(vb).localeCompare(String(va), 'pt-BR', {numeric:true});
  });
  // limpa indicadores das outras colunas
  table.querySelectorAll('thead th').forEach(x => {
    x.dataset.sortDir = '';
    x.classList.remove('sorted-asc','sorted-desc');
  });
  th.dataset.sortDir = dir;
  th.classList.add('sorted-' + dir);
  rows.forEach(r => tbody.appendChild(r));
}

function initSortable(){
  document.querySelectorAll('table').forEach(table => {
    const headerRow = table.querySelector('thead tr');
    const tbody = table.querySelector('tbody');
    if (!headerRow || !tbody || !tbody.querySelector('tr')) return;
    headerRow.querySelectorAll('th').forEach((th, i) => {
      th.dataset.sortable = '1';
      th.dataset.col = i;
      th.addEventListener('click', () => sortTable(th, table));
    });
  });
}
initSortable();
'''


# Auto-derived narrative bits
CTR_DIFF = TL4['ctr'] - TL3['ctr']
CPM_DIFF_PCT = (TL4['cpm']-TL3['cpm'])/TL3['cpm']*100 if TL3['cpm'] else 0
CPC_DIFF_PCT = (TL4['cpc']-TL3['cpc'])/TL3['cpc']*100 if TL3['cpc'] else 0
HUBLA_DIFF = S4['hubla_total'] - S3['hubla_total']
MQL_DIFF_PP = MW4['mql_pct'] - MW3['mql_pct']

TOP_CAMPS = [c for c in CAMP4 if c.get('spend',0) > 100][:6]
top_camp_names = ', '.join(short_name(c['name']) for c in TOP_CAMPS[:3])

camp_with_purch = [c for c in CAMP4 if c.get('purch',0) > 0]
best_cpa_camp = min(camp_with_purch, key=lambda c: c['spend']/c['purch']) if camp_with_purch else None
worst_cpa_camp = max(((c, c['spend']) for c in CAMP4 if c.get('purch',0)==0 and c.get('spend',0)>0), key=lambda x: x[1])[0] if any(c.get('purch',0)==0 and c.get('spend',0)>0 for c in CAMP4) else None

HTML = f'''<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DP100K-Fp02 — Julho/26 Sem 1 — Dashboard</title>
<style>{CSS}</style></head><body><div class="wrap">
<header class="hero">
<h1>DP100K-Fp02 — Julho/26 Sem 1</h1>
<div class="sub">Dashboard de performance · Funil "Desafio Palestrante 100K" · Turma Julho/26-1 (1ª semana do ciclo de julho)</div>
<div class="meta">
<span><b>Período:</b> 22/06/2026 → 29/06/2026</span>
<span><b>Conta:</b> act_1725623984282551</span>
<span><b>Cliente:</b> C1 - Tathi Deândhela</span>
<span><b>Fontes:</b> Investimento por Hora + Hubla + Pesquisa + Meta API</span>
</div></header>

<nav class="tabs">
<button class="active" data-tab="overview">Visão Geral</button>
<button data-tab="compare">vs Jun S4</button>
<button data-tab="trend">📅 Últimas 4 turmas</button>
<button data-tab="campaigns">Campanhas e Breakdowns</button>
<button data-tab="quiz">🧩 Quiz</button>
<button data-tab="creatives">Criativos Top</button>
<button data-tab="persona">👤 Público</button>
<button data-tab="health">🚦 Saúde dos Ads</button>
<button data-tab="mql">Qualidade (MQL)</button>
<button data-tab="actions">📋 Ações</button>
</nav>

<section id="overview" class="active">
<h2>Visão Geral</h2>
<p class="muted">Recorte da turma <b>Julho/26 - 1</b> consolidado da aba "Investimento por Hora" + Hubla. Deltas vs Junho Sem 4 ao lado de cada KPI.</p>
{render_kpi_grid(overview_kpis)}

<h3>📈 Performance dia a dia — Semana 1 (22/06 → 29/06)</h3>
<p class="muted">Investimento (barras, eixo esquerdo) × vendas Hubla por dia (linhas, eixo direito). Venda = Hubla cruzado por utm_content (verdade canônica), não pixel.</p>
{daily_chart_html}
<table style="margin-top:14px">
<thead><tr><th>Dia</th><th>Investimento</th><th>Vendas meta (Hubla)</th><th>Vendas totais (Hubla)</th><th>CPA real meta</th><th>Visitas LP</th><th>Checkout</th><th>Compras pixel</th></tr></thead>
<tbody>{daily_table_rows}</tbody>
</table>

<h3>💰 Custo por Etapa (recorte DP100K-Fp02 · Meta API)</h3>
<p class="muted">Onde cada R$ vira (ou não vira) próximo passo do funil. Deltas vs Junho Sem 4.</p>
{render_kpi_grid(cost_per_step)}

<h3>Funil Click → Venda</h3>
<div class="funnel">{funnel_html}</div>
<div class="callout {'ok' if TL4['lpv_ic']>=TL3['lpv_ic'] else 'danger'}"><b>LPV→IC:</b> {fmt_pct(TL4['lpv_ic'])} ({delta_html(TL3['lpv_ic'], TL4['lpv_ic'], pp=False)} vs Jun S4). IC→Venda: {fmt_pct(TL4['ic_v'])}.</div>

<div class="callout {'ok' if HUBLA_DIFF>=0 else 'danger'}">
<b>Síntese da Julho Sem 1:</b><br>
• Investimento turma {fmt_money(T3['spend'])} → {fmt_money(T4['spend'])} ({delta_html(T3['spend'], T4['spend'])})<br>
• Vendas Hubla {S3['hubla_total']} → {S4['hubla_total']} ({delta_html(S3['hubla_total'], S4['hubla_total'])}) · via meta_ads {S3['hubla_meta_ads']} → {S4['hubla_meta_ads']} ({delta_html(S3['hubla_meta_ads'], S4['hubla_meta_ads'])})<br>
• CPA real meta_ads {fmt_money(CPA_META_S3)} → {fmt_money(CPA_META_S4)} ({delta_html(CPA_META_S3, CPA_META_S4, lower_better=True)})<br>
• CTR {fmt_pct(TL3['ctr'])} → {fmt_pct(TL4['ctr'])} ({delta_html(TL3['ctr'], TL4['ctr'])}) · CPC {fmt_money(TL3['cpc'])} → {fmt_money(TL4['cpc'])} ({delta_html(TL3['cpc'], TL4['cpc'], lower_better=True)})<br>
• MQL rate (compradores) {fmt_pct(MW3['mql_pct'])} → {fmt_pct(MW4['mql_pct'])} ({delta_html(MW3['mql_pct'], MW4['mql_pct'], pp=True)})
</div>
</section>

<section id="compare">
<h2>Comparativo Junho Sem 4 vs Julho Sem 1</h2>
<p class="muted">Junho Sem 4 (15/06 → 22/06) versus Julho Sem 1 (22/06 → 29/06). Verde = melhorou, vermelho = piorou.</p>
<table>
<thead><tr><th>Métrica</th><th>Jun S4</th><th>Jul S1</th><th>Δ</th></tr></thead>
<tbody>{''.join(cmp_rows)}</tbody>
</table>

<div class="callout">
<b>Leitura síntese:</b><br>
Julho Sem 1 fechou com <b>{S4['hubla_total']} vendas Hubla</b> ({delta_html(S3['hubla_total'], S4['hubla_total'])} vs Jun S4) e <b>{S4['hubla_meta_ads']} delas via meta_ads</b>. Investimento {fmt_money(T4['spend'])} ({delta_html(T3['spend'], T4['spend'], lower_better=True)}).<br><br>
{('Campanha campeã em CPA: <b>'+short_name(best_cpa_camp['name'])+'</b> ('+fmt_money(best_cpa_camp['spend']/best_cpa_camp['purch'])+' por venda).') if best_cpa_camp else ''}
{(' Pior queima: <b>'+short_name(worst_cpa_camp['name'])+'</b> ('+fmt_money(worst_cpa_camp['spend'])+' sem vendas atribuídas).') if worst_cpa_camp else ''}
</div>
</section>

<section id="trend">
<h2>📅 Comparativo das últimas 4 turmas</h2>
<p class="muted">Jun S2 (01/06 → 08/06) · Jun S3 (08/06 → 15/06) · Jun S4 (15/06 → 22/06) · Jul S1 (22/06 → 29/06). Setas indicam direção ao longo das turmas (verde = melhorou, vermelho = piorou). Δ Jul S1 vs Jun S4 = turma atual contra anterior. Δ Jul S1 vs Jun S2 = janela de 4 turmas. MQL recomputado por cruzamento de e-mail (compra + renda≥10k) nas 4 turmas.</p>

{render_kpi_grid(trend_kpis)}

<table>
<thead><tr><th>Métrica</th><th>Jun S2</th><th>Jun S3</th><th>Jun S4</th><th>Jul S1</th><th>Tendência</th><th>Δ Jul S1 vs Jun S4</th><th>Δ Jul S1 vs Jun S2</th></tr></thead>
<tbody>{''.join(trend_rows)}</tbody>
</table>

<div class="callout">
<b>Leitura das últimas 4 turmas:</b><br>
• <b>Investimento</b> {fmt_money(T1['spend'])} → {fmt_money(T2['spend'])} → {fmt_money(T3['spend'])} → {fmt_money(T4['spend'])} — Jul S1 {delta_html(T3['spend'], T4['spend'], lower_better=True)} vs Jun S4.<br>
• <b>Vendas Hubla</b> {S1['hubla_total']} → {S2['hubla_total']} → {S3['hubla_total']} → {S4['hubla_total']} ({delta_html(S3['hubla_total'], S4['hubla_total'])} Jul S1 vs Jun S4).<br>
• <b>CPA real meta_ads</b> {fmt_money(CPA_META_S1)} → {fmt_money(CPA_META_S2)} → {fmt_money(CPA_META_S3)} → {fmt_money(CPA_META_S4)} ({delta_html(CPA_META_S3, CPA_META_S4, lower_better=True)} Jul S1 vs Jun S4).<br>
• <b>MQL rate (compradores)</b> {fmt_pct(MW1['mql_pct'])} → {fmt_pct(MW2['mql_pct'])} → {fmt_pct(MW3['mql_pct'])} → {fmt_pct(MW4['mql_pct'])} ({delta_html(MW3['mql_pct'], MW4['mql_pct'], pp=True)} Jul S1 vs Jun S4).<br>
• <b>LPV→IC</b> {fmt_pct(TL1['lpv_ic'])} → {fmt_pct(TL2['lpv_ic'])} → {fmt_pct(TL3['lpv_ic'])} → {fmt_pct(TL4['lpv_ic'])} — {('alvo de 6% atingido.' if TL4['lpv_ic']>=6 else 'ainda abaixo do alvo de 6%.')}<br>
• <b>CPM</b> {fmt_money(TL1['cpm'])} → {fmt_money(TL2['cpm'])} → {fmt_money(TL3['cpm'])} → {fmt_money(TL4['cpm'])}.
</div>

<div class="callout ok"><b>Acumulado últimas 4 turmas:</b> {fmt_money(TOT_SPEND)} investidos · {TOT_VENDAS_HUBLA} vendas Hubla totais ({TOT_VENDAS_META} via meta_ads) · CPA real meta_ads médio {fmt_money(CPA_META_4W)} · MQL rate acumulada {fmt_pct(MQL_RATE_4W)}.</div>
</section>

<section id="campaigns">
<h2>Campanhas e Breakdowns</h2>
<h3>Campanhas DP100K-Fp02 com spend na Julho Sem 1</h3>
<table><thead><tr><th>Campanha</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>CPM</th><th>Custo/LPV</th><th>Custo/IC</th><th>V</th><th>CPA</th></tr></thead><tbody>{''.join(camps_rows)}</tbody></table>

<h3>📊 Breakdowns (todas DP100K-Fp02)</h3>
<h3 style="font-size:14px;color:#fbbf24">Por Placement</h3>
{bd_table(BD['placement'], ['Placement','Spend','Impr','Clicks','LPV','IC','V','CPA','% Spend'], 16)}

<h3 style="font-size:14px;color:#fbbf24">Por Device</h3>
{bd_table(BD['device'], ['Device','Spend','Impr','Clicks','LPV','IC','V','CPA','% Spend'], 6)}

<h3 style="font-size:14px;color:#fbbf24">Por Idade × Gênero</h3>
{bd_table_agegender()}
</section>

<section id="quiz">
<h2>🧩 Campanhas de Quiz — Julho Sem 1</h2>
<p class="muted">Recorte das campanhas com "QUIZ" no nome ({len(quiz_codes_sorted)} ads com spend). Rota: anúncio → <b>quiz</b> (soumemoravel.com.br/quiz) → oferta → checkout. As "Visitas quiz (LPV)" contam a página do quiz, não a oferta direta — por isso a taxa de conversão da página é naturalmente menor que nos ads diretos. O que decide aqui é o <b>CPA real (Hubla)</b>. Venda = Hubla cruzado por utm_content.</p>
{render_kpi_grid(quiz_kpis)}

<div class="callout {'ok' if Q_vendas and Q_cpa <= DIR_cpa else 'danger' if Q_vendas==0 else ''}">
<b>Quiz × Direto:</b> o quiz trouxe <b>{Q_vendas} vendas Hubla</b> ({fmt_pct1(QUIZ_SHARE)} das {S4['hubla_meta_ads']} vendas via meta_ads) a <b>CPA {fmt_money(Q_cpa)}</b>, com investimento de {fmt_money(Q_spend)}. Os ads diretos (não-quiz) fecharam a CPA {fmt_money(DIR_cpa)} ({DIR_vendas} vendas / {fmt_money(DIR_spend)}). {('O quiz está mais barato que o direto — vale manter/escalar.' if Q_vendas and Q_cpa <= DIR_cpa else 'O quiz está mais caro que o direto — revisar criativos/etapa de quiz.' if Q_vendas else 'Sem vendas atribuídas ao quiz no período.')}
</div>

<h3>Funil do quiz (Visita → Checkout → Compra)</h3>
<p class="muted">Conversões da rota quiz pelo pixel. LPV = visitas à página do quiz.</p>
<div class="funnel">{quiz_funnel_html}</div>

<h3>📈 Quiz dia a dia — Semana 1 (22/06 → 29/06)</h3>
<p class="muted">Investimento das campanhas de quiz (barras) × vendas Hubla atribuídas a ads de quiz por dia (linha verde) e compras registradas pelo pixel (linha azul).</p>
{quiz_chart_html}

<h3>Ads de quiz — ordenados por vendas Hubla</h3>
{quiz_cards}

<h3>Tabela — todos os ads de quiz com spend</h3>
<table>
<thead><tr><th>AD</th><th>Spend</th><th>Visitas quiz</th><th>Checkout</th><th>Visita→IC</th><th>Compras pixel</th><th>Vendas Hubla</th><th>CPA real</th><th>MQL</th></tr></thead>
<tbody>{quiz_table_rows}</tbody>
</table>
</section>

<section id="creatives">
<h2>🏆 Top Ads — Ranking Julho Sem 1</h2>
<p class="muted">Critério composto cruzando <b>vendas Hubla</b> (utm_content) com <b>investimento Meta</b> e <b>MQL da pesquisa</b>, na turma Julho/26-1.</p>

<div class="criteria-box">
<div class="crit-item">📊 <b>Janela:</b> {TOP_ADS_4W['window']}</div>
<div class="crit-item">🎯 <b>CPA real:</b> {TOP_CRITERIA['cpa_real']} · <b>alvo</b> R$ {TOP_CRITERIA['cpa_alvo_ref']:.0f}</div>
<div class="crit-item">✅ <b>Elegibilidade:</b> {TOP_CRITERIA['eligibility']}</div>
<div class="crit-item">⚖️ <b>Pesos:</b> vendas Hubla <b>{TOP_CRITERIA['weights']['vendas']*100:.0f}%</b> · MQL <b>{TOP_CRITERIA['weights']['mql']*100:.0f}%</b> · CPA <b>{TOP_CRITERIA['weights']['cpa']*100:.0f}%</b> (cada componente normalizado 0-100)</div>
<div class="crit-item">📈 <b>{len(TOP_RANKING)} ads elegíveis</b> de {len(TOP_RANKING) + TOP_ADS_4W['excluded_count']} totais (Jul S1) — outros {TOP_ADS_4W['excluded_count']} ficaram fora do ranking por falta de volume ou conversão.</div>
</div>

<h3>Top 15 — cards com preview</h3>
<p class="muted">Cards #1-#3 destacados em verde forte (top tier). Card mostra: posição, score total, sub-scores (vendas/MQL/CPA), vendas Hubla, CPA real, MQL e spend da turma.</p>
{ad_grid}

<h3>Ranking completo ({len(TOP_RANKING)} elegíveis)</h3>
<p class="muted">Tabela com todos os ads que passaram o filtro de elegibilidade, ordenados por score total. Sub-scores na última coluna mostram a contribuição de cada critério.</p>
<table>
<thead><tr><th>#</th><th>Cód.</th><th>Nome</th><th>Vendas Hubla</th><th>Conv. visita→venda</th><th>CPA real</th><th>MQL</th><th>Spend</th><th>CTR link</th><th>Score</th><th>V · MQL · CPA</th></tr></thead>
<tbody>{ranking_table_rows}</tbody>
</table>
</section>

<section id="persona">
<h2>👤 Público — perfil da compradora (Jul S1)</h2>
<p class="muted">Quem comprou nesta turma, cruzando a venda (Hubla) com a pesquisa por e-mail. Perfil por canal de venda e por ad campeão do Meta.</p>
{PERSONA_VIEWS_HTML}
</section>

<section id="health">
<h2>🚦 Saúde dos Ads — Julho Sem 1</h2>
<p class="muted">Universo completo de ads com spend na turma Julho/26-1. <b>Vendas Hubla</b> (utm_content) cruzadas com <b>investimento Meta</b>. CPA real = spend ÷ vendas Hubla. Status calculado pelas regras abaixo.</p>

<div class="criteria-box">
<div class="crit-item"><b>🔵 Aprendendo:</b> spend_4w &lt; R$ 100 (sem volume suficiente pra decidir)</div>
<div class="crit-item"><b>🟢 Escalar:</b> vendas Hubla ≥ 10 (campeões do ciclo)</div>
<div class="crit-item"><b>🟢 Eficiente:</b> vendas ≥ 1 e CPA ≤ R$ 200 (80% do alvo R$ 250)</div>
<div class="crit-item"><b>🟢 Convertendo:</b> vendas Hubla ≥ 4 ou (vendas ≥ 1 com CPA dentro do alvo)</div>
<div class="crit-item"><b>🟠 Sinal fraco:</b> LPV ≥ 60 + IC ≥ 2 + 0 vendas Hubla (página engaja mas não converte)</div>
<div class="crit-item"><b>🟠 Sem sinal:</b> LPV ≥ 60 + IC = 0 + 0 vendas (página rejeita)</div>
<div class="crit-item"><b>🔴 Morto:</b> spend_4w ≥ R$ 400 e 0 vendas Hubla (ou ≥ R$ 200 sem sinal)</div>
</div>

<h3>Distribuição</h3>
<p>{classification_summary}</p>

<table>
<thead><tr><th></th><th>AD</th><th>Nome</th><th>Spend</th><th>Vendas Hubla</th><th>CPA real</th><th>MQL</th><th>% MQL</th><th>LPV</th><th>IC</th><th>CTR link</th><th>Status</th><th>Ação</th></tr></thead>
<tbody>{health_rows_4w}</tbody>
</table>
</section>

<section id="mql">
<h2>Qualidade da Venda (MQL)</h2>
<p class="muted">MQL = <b>comprador</b> com renda <b>≥ R$ 10.001</b> (faixas 10.001-15k, 15.001-20k, acima de 20k). Método canônico DP100K: cruza o e-mail da venda (Hubla) com a renda da Pesquisa — não usa pivot por respondente. Agrupado pelo código do ad (AD-XX = utm_content da venda).</p>
<div class="kpi-grid">
<div class="kpi"><div class="lbl">Vendas via meta_ads</div><div class="val">{S4['hubla_meta_ads']}</div></div>
<div class="kpi"><div class="lbl">Compradores identificados</div><div class="val">{MW4['matched']}</div><div class="sub">{fmt_pct1(S4['match_pct'])} match e-mail c/ Pesquisa</div></div>
<div class="kpi ok"><div class="lbl">MQL (renda≥10k)</div><div class="val">{MW4['mql']}</div></div>
<div class="kpi ok"><div class="lbl">MQL rate</div><div class="val">{fmt_pct(MW4['mql_pct'])}</div><div class="sub">dos identificados · vs {fmt_pct(MW3['mql_pct'])} na Jun S4</div></div>
</div>
<h3>MQL por Ad — Julho Sem 1</h3>
<p class="muted">"Compradores" = vendas Hubla do ad com e-mail casado na Pesquisa (renda conhecida). "MQL" = desses, os com renda ≥ R$ 10.001.</p>
<table><thead><tr><th>Ad</th><th>Compradores</th><th>MQL</th><th>% MQL</th></tr></thead><tbody>{mql_rows}</tbody></table>
</section>

<section id="actions">
<h2>📋 Plano de Ação — Próximo Ciclo</h2>
<p class="muted">Recomendações automáticas a partir dos sinais da turma Julho/26-1. Use como base pra decidir o que entra/sai do próximo funil.</p>

<h3>🔴 Pausar / Matar</h3>
<div class="actions-list">
{''.join(f'<div class="item kill">{txt}</div>' for cls, txt in actions if cls == 'kill') or '<div class="item">Nenhum ad com R$ 200+ sem vendas no período.</div>'}
</div>

<h3>🟢 Escalar (campeões do ciclo)</h3>
<div class="actions-list">
{''.join(f'<div class="item scale">{txt}</div>' for cls, txt in actions if cls == 'scale') or '<div class="item">Nenhum ad com 10+ vendas no ciclo — atenção à concentração.</div>'}
</div>

<h3>🟡 Refresh / Renovar</h3>
<div class="actions-list">
{''.join(f'<div class="item refresh">{txt}</div>' for cls, txt in actions if cls == 'refresh') or '<div class="item">Nenhum sinal forte de fadiga (Δ CTR < -35% ou freq > 3) no período.</div>'}
</div>

<h3>🎯 Targeting & Estratégia</h3>
<ol>
<li><b>Validar ICP do ciclo:</b> conferir nas tabelas de age × gender quem trouxe CPA mais baixo na turma e considerar adset dedicado pro próximo funil.</li>
<li><b>Auditar placements:</b> placements com R$ 300+ acumulados e zero venda devem ser excluídos ou setados em manual placements.</li>
<li><b>Página LP:</b> auditar o gap entre Add to Cart ({TL4['atc']}) e Initiate Checkout ({TL4['ic']}) — diferença significa drop entre carrinho e checkout Hubla.</li>
<li><b>Funil MQL:</b> MQL rate (compradores) Jul S1 em {fmt_pct(MW4['mql_pct'])}. {('Perfil qualificado — manter direção.' if MW4['mql_pct']>=50 else 'Calibrar criativos pra atrair perfil de maior renda.')}</li>
<li><b>Teste de copy:</b> rodar 3 variações de hook ainda não testadas × R$ 100/dia × 3 dias = R$ 900 pra validar.</li>
<li><b>Aprendizado pro próximo funil:</b> usar o ranking (aba Criativos Top) como base — top {min(8, len(TOP_RANKING))} ads devem ser replicados/iterados; ads 🔴 do ciclo não entram.</li>
</ol>
</section>

<footer>
DP100K-Fp02 — Julho/26 Sem 1 · Dashboard gerado em {GEN_TIME}
</footer>
</div>
<script>{JS}</script>
</body></html>'''

HTML = _relabel(HTML)
with open(OUT,'w') as f: f.write(HTML)
print(f"Dashboard escrito: {OUT}")
print(f"Tamanho: {os.path.getsize(OUT)} bytes")
