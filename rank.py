"""Ranking de Top Ads da turma atual — vendas Hubla + CPA real + MQL.

Score composto (0-100): vendas 45% + MQL 25% + CPA 30%. Recebe ads (Meta),
hubla_rows (venda canonica) e mql_per_ad (in-memory).
"""
import re
from collections import Counter, defaultdict

import config as C

AD_RE = re.compile(r'AD-(\d+)', re.I)


def _ad_code(s):
    m = AD_RE.search(s or '')
    return f"AD-{int(m.group(1))}" if m else None


def build(ads, hubla_rows, mql_per_ad, h_src, h_cont, window_label):
    spend = defaultdict(float)
    ad_names = {}
    ad_ids = defaultdict(list)
    purch_meta = defaultdict(int)
    lpv = defaultdict(int)
    ic = defaultdict(int)
    impr = defaultdict(int)
    link_clicks = defaultdict(int)

    for a in ads:
        code = _ad_code(a.get('name', ''))
        if not code:
            continue
        spend[code] += float(a.get('spend', 0) or 0)
        ad_names[code] = a.get('name', code)
        if a.get('ad_id'):
            ad_ids[code].append(a['ad_id'])
        purch_meta[code] += int(a.get('purch', 0) or 0)
        lpv[code] += int(a.get('lpv', 0) or 0)
        ic[code] += int(a.get('ic', 0) or 0)
        impr[code] += int(a.get('impr', 0) or 0)
        link_clicks[code] += int(a.get('link_clicks', 0) or 0)

    hubla = Counter()
    for r in hubla_rows:
        if 'meta' not in (r.get(h_src, '') or '').lower():
            continue
        code = _ad_code(r.get(h_cont, ''))
        if code:
            hubla[code] += 1

    mql_total = defaultdict(int)
    mql_count = defaultdict(int)
    for code, v in mql_per_ad.items():
        if code == 'unknown':
            continue
        mql_total[code] += v.get('total', 0)
        mql_count[code] += v.get('mql', 0)

    all_codes = set(spend) | set(hubla) | set(mql_count)
    rows = []
    for code in all_codes:
        sp = spend.get(code, 0)
        vd = hubla.get(code, 0)
        mq = mql_count.get(code, 0)
        rows.append({
            'ad_code': code, 'name': ad_names.get(code, code),
            'ad_ids': list(set(ad_ids.get(code, []))),
            'spend_4w': sp, 'vendas_hubla': vd,
            'cpa_real': (sp / vd) if vd else None,
            'mql_count': mq, 'pesquisa_total': mql_total.get(code, 0),
            'mql_pct': (mq / mql_total.get(code, 1) * 100) if mql_total.get(code) else 0,
            'purch_meta': purch_meta.get(code, 0), 'lpv_4w': lpv.get(code, 0), 'ic_4w': ic.get(code, 0),
            'impr_4w': impr.get(code, 0), 'link_clicks_4w': link_clicks.get(code, 0),
            'link_ctr': (link_clicks.get(code, 0) / impr.get(code, 1) * 100) if impr.get(code) else 0,
        })

    SPEND_MIN = 200
    elig = [r for r in rows if r['spend_4w'] >= SPEND_MIN and (r['vendas_hubla'] >= 1 or r['mql_count'] >= 2)]

    CPA_ALVO = C.CPA_ALVO
    W_V, W_M, W_C = 0.45, 0.25, 0.30
    max_v = max((r['vendas_hubla'] for r in elig), default=1) or 1
    max_mql = max((r['mql_count'] for r in elig), default=1) or 1
    for r in elig:
        sv = r['vendas_hubla'] / max_v * 100
        sm = r['mql_count'] / max_mql * 100
        sc = 0 if r['cpa_real'] is None else max(0.0, (1 - r['cpa_real'] / (2 * CPA_ALVO)) * 100)
        r['score_vendas'] = round(sv, 1)
        r['score_mql'] = round(sm, 1)
        r['score_cpa'] = round(sc, 1)
        r['score_total'] = round(W_V * sv + W_M * sm + W_C * sc, 1)
    elig.sort(key=lambda r: -r['score_total'])

    def classify(r):
        sp, vh, l, i = r['spend_4w'], r['vendas_hubla'], r['lpv_4w'], r['ic_4w']
        if sp < 100:
            return ('🔵 Aprendendo', 'Aguardar volume')
        if sp >= 400 and vh == 0:
            return ('🔴 Morto', 'Pausar')
        if vh >= 10:
            return ('🟢 Escalar', '+30-50% budget')
        if vh >= 4:
            return ('🟢 Convertendo', 'Manter')
        if vh >= 1:
            if r['cpa_real'] and r['cpa_real'] <= CPA_ALVO * 0.8:
                return ('🟢 Eficiente', 'Manter / testar escala')
            return ('🟢 Convertendo', 'Manter')
        if l >= 60 and i >= 2:
            return ('🟠 Sinal fraco', 'Trocar copy/CTA')
        if l >= 60 and i == 0:
            return ('🟠 Sem sinal', 'Pausar em 24h')
        if sp >= 200:
            return ('🔴 Morto', 'Pausar')
        return ('⚪ Indefinido', 'Observar')

    for r in rows:
        r['status_tag'], r['action_rec'] = classify(r)
        for k in ('score_total', 'score_vendas', 'score_mql', 'score_cpa'):
            r.setdefault(k, 0)

    all_ads = sorted(rows, key=lambda r: -r['spend_4w'])

    return {
        'window': window_label,
        'criteria': {
            'spend_min': SPEND_MIN, 'cpa_alvo_ref': CPA_ALVO,
            'weights': {'vendas': W_V, 'mql': W_M, 'cpa': W_C},
            'eligibility': f'spend >= R$ {SPEND_MIN} AND (vendas_hubla >= 1 OR mql >= 2)',
            'cpa_real': 'spend_meta / vendas_hubla (utm_content = AD-XX)',
            'classification': {
                '🔵 Aprendendo': 'spend < R$ 100', '🟢 Escalar': 'vendas_hubla >= 10',
                '🟢 Convertendo': 'vendas_hubla >= 4 OU (vendas>=1 e CPA <= alvo)',
                '🟢 Eficiente': 'vendas >= 1 e CPA <= 80% do alvo',
                '🟠 Sinal fraco': 'lpv>=60 + ic>=2 + 0 vendas Hubla',
                '🟠 Sem sinal': 'lpv>=60 + ic=0 + 0 vendas Hubla',
                '🔴 Morto': 'spend >= R$ 400 e 0 vendas Hubla (ou >= R$ 200 sem sinal)',
            },
        },
        'normalization': {'max_vendas_hubla': max_v, 'max_mql': max_mql},
        'ranking': elig, 'all_ads': all_ads, 'excluded_count': len(rows) - len(elig),
    }
