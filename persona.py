"""Persona da turma atual — mesmo formato do persona_*.json original.

Cruza comprador (Hubla) x respondente (Pesquisa) por e-mail, agrupa por origem
e por ad campeao. Recebe as linhas ja filtradas da turma atual (in-memory).
"""
import re
from collections import Counter, defaultdict

import config as C

AD_RE = re.compile(r'AD-(\d+)', re.I)


def _ad_code(s):
    m = AD_RE.search(s or '')
    return f"AD-{int(m.group(1))}" if m else None


def _origin_group(src):
    s = (src or '').lower().strip()
    if not s:
        return 'Sem UTM'
    if 'meta' in s or 'facebook' in s:
        return 'Meta Ads'
    if s == 'instagram':
        return 'Orgânico Instagram'
    if s == 'ipm':
        return 'IPM (cross-sell)'
    if s in ('whatsapp', 'wpp'):
        return 'WhatsApp direto'
    if s in ('tathinews', 'activecampaign', 'email', 'newsletter'):
        return 'E-mail / News'
    return f'Outros ({s})'


def _dist(rows, col, top_n=None):
    c = Counter((r.get(col, '') or '').strip() for r in rows)
    c.pop('', None)
    items = sorted(c.items(), key=lambda x: -x[1])
    if top_n:
        items = items[:top_n]
    total = sum(v for _, v in items)
    return [{'k': k, 'n': v, 'pct': v / total * 100 if total else 0} for k, v in items]


def _samples(rows, col, n=6, min_len=20, max_len=200):
    out = []
    for r in rows:
        v = (r.get(col, '') or '').strip()
        if len(v) < min_len:
            continue
        v = re.sub(r'\s+', ' ', v).strip()
        if len(v) > max_len:
            v = v[:max_len - 1] + '…'
        out.append(v)
        if len(out) >= n:
            break
    return out


def analyze(hubla_rows, pesq_rows, window_label, h_email, h_src, h_cont, p_email):
    if not hubla_rows:
        return None

    for r in hubla_rows:
        r['_origin'] = _origin_group(r.get(h_src, '') if h_src else '')

    emails_by_origin = defaultdict(set)
    for r in hubla_rows:
        em = (r.get(h_email, '') or '').strip().lower()
        if em:
            emails_by_origin[r['_origin']].add(em)

    sales_by_origin = Counter(r['_origin'] for r in hubla_rows)

    email_to_origin = {}
    prio = {'Meta Ads': 1, 'IPM (cross-sell)': 2, 'Orgânico Instagram': 3,
            'WhatsApp direto': 4, 'E-mail / News': 5, 'Sem UTM': 6}
    for origin, emails in emails_by_origin.items():
        for em in emails:
            if em not in email_to_origin or prio.get(origin, 9) < prio.get(email_to_origin[em], 9):
                email_to_origin[em] = origin

    for r in pesq_rows:
        em = (r.get(p_email, '') or '').strip().lower() if p_email else ''
        r['_is_buyer'] = em in email_to_origin
        r['_buyer_origin'] = email_to_origin.get(em)
        r['_is_mql'] = C.is_mql_renda(r.get(C.COL_INCOME, ''))

    buyer_rows = [r for r in pesq_rows if r['_is_buyer']]
    buyers_by_origin = defaultdict(list)
    for r in buyer_rows:
        buyers_by_origin[r['_buyer_origin']].append(r)

    ORIGINS_VIEW = [o for o, n in sales_by_origin.most_common() if n >= 2]
    if not ORIGINS_VIEW:
        ORIGINS_VIEW = [o for o, _ in sales_by_origin.most_common(4)]

    def dist_by_origin(col, top_n=12):
        per_origin = {}
        for o in ORIGINS_VIEW:
            c = Counter((r.get(col, '') or '').strip() for r in buyers_by_origin.get(o, []))
            c.pop('', None)
            per_origin[o] = c
        total_by_key = Counter()
        for o, c in per_origin.items():
            for k, n in c.items():
                total_by_key[k] += n
        keys = [k for k, _ in total_by_key.most_common(top_n)]
        origin_totals = {o: sum(per_origin[o].values()) for o in ORIGINS_VIEW}
        rows = []
        for k in keys:
            rows.append({
                'k': k,
                'by_origin': [{
                    'origin': o, 'n': per_origin[o].get(k, 0),
                    'pct': per_origin[o].get(k, 0) / origin_totals[o] * 100 if origin_totals[o] else 0,
                } for o in ORIGINS_VIEW],
                'total': total_by_key[k],
            })
        return {'rows': rows, 'origins': ORIGINS_VIEW, 'origin_totals': origin_totals}

    origins_summary = []
    for o, _ in sales_by_origin.most_common():
        rows_o = buyers_by_origin.get(o, [])
        mql_o = [r for r in rows_o if r['_is_mql']]
        total_sales = sales_by_origin[o]
        origins_summary.append({
            'origin': o, 'sales_total': total_sales,
            'sales_pct': total_sales / sum(sales_by_origin.values()) * 100,
            'sem1': 0, 'sem2': 0, 'sem3': 0, 'sem4': 0,
            'matched': len(rows_o), 'match_pct': len(rows_o) / total_sales * 100 if total_sales else 0,
            'mql_count': len(mql_o), 'mql_pct': len(mql_o) / len(rows_o) * 100 if rows_o else 0,
            'age_top': (_dist(rows_o, C.COL_AGE, 1) or [{'k': '—', 'n': 0, 'pct': 0}])[0],
            'gender_top': (_dist(rows_o, C.COL_GENDER, 1) or [{'k': '—', 'n': 0, 'pct': 0}])[0],
            'occup_top': (_dist(rows_o, C.COL_OCC, 1) or [{'k': '—', 'n': 0, 'pct': 0}])[0],
            'income_top': (_dist(rows_o, C.COL_INCOME, 1) or [{'k': '—', 'n': 0, 'pct': 0}])[0],
            'self_top': (_dist(rows_o, C.COL_SELF, 1) or [{'k': '—', 'n': 0, 'pct': 0}])[0],
            'desire_top': (_dist(rows_o, C.COL_DESIRE, 1) or [{'k': '—', 'n': 0, 'pct': 0}])[0],
        })

    all_buyers_mql = [r for r in buyer_rows if r['_is_mql']]

    meta_rows = [r for r in hubla_rows if r['_origin'] == 'Meta Ads']
    sales_per_ad = Counter()
    for r in meta_rows:
        code = _ad_code(r.get(h_cont, ''))
        if code:
            sales_per_ad[code] += 1
    TOP_AD_SALES = sales_per_ad.most_common(12)

    ad_personas = {}
    for code, sales in TOP_AD_SALES[:10]:
        emails_ad = {(r.get(h_email, '') or '').strip().lower()
                     for r in meta_rows if _ad_code(r.get(h_cont, '')) == code and r.get(h_email)}
        emails_ad.discard('')
        rows_p = [r for r in buyer_rows if (r.get(p_email, '') or '').strip().lower() in emails_ad]
        if not rows_p:
            continue
        rows_mql = [r for r in rows_p if r['_is_mql']]
        ad_personas[code] = {
            'sales_hubla': sales, 'matched': len(rows_p), 'mql_count': len(rows_mql),
            'mql_pct': len(rows_mql) / len(rows_p) * 100 if rows_p else 0,
            'age_top': _dist(rows_p, C.COL_AGE, 3), 'gender_top': _dist(rows_p, C.COL_GENDER, 2),
            'income_top': _dist(rows_p, C.COL_INCOME, 4), 'occup_top': _dist(rows_p, C.COL_OCC, 4),
            'self_top': _dist(rows_p, C.COL_SELF, 3),
        }

    voc_by_origin = {}
    for o in ORIGINS_VIEW:
        rows_o = buyers_by_origin.get(o, [])
        voc_by_origin[o] = {
            'thought': _samples(rows_o, C.COL_THOUGHT, 6), 'chall': _samples(rows_o, C.COL_CHALL, 6),
            'learn': _samples(rows_o, C.COL_LEARN, 6), 'question': _samples(rows_o, C.COL_QUESTION, 6),
        }

    return {
        'window': window_label, 'weeks': [1],
        'totals': {
            'hubla_total': sum(sales_by_origin.values()), 'pesquisa_total': len(pesq_rows),
            'buyer_matched': len(buyer_rows),
            'match_pct': len(buyer_rows) / sum(sales_by_origin.values()) * 100 if sales_by_origin else 0,
            'all_buyers_mql': len(all_buyers_mql),
            'all_buyers_mql_pct': len(all_buyers_mql) / len(buyer_rows) * 100 if buyer_rows else 0,
        },
        'origins_view': ORIGINS_VIEW, 'origins_summary': origins_summary,
        'by_origin': {
            'age': dist_by_origin(C.COL_AGE, 10), 'gender': dist_by_origin(C.COL_GENDER, 4),
            'income': dist_by_origin(C.COL_INCOME, 12), 'occup': dist_by_origin(C.COL_OCC, 14),
            'self': dist_by_origin(C.COL_SELF, 8), 'desire': dist_by_origin(C.COL_DESIRE, 10),
            'time': dist_by_origin(C.COL_TIME, 6), 'prev': dist_by_origin(C.COL_PREV, 3),
            'state': dist_by_origin(C.COL_STATE, 12),
        },
        'voc_by_origin': voc_by_origin,
        'top_ads_meta': [{'ad': k, 'sales': n} for k, n in TOP_AD_SALES],
        'ad_personas': ad_personas,
    }


def build(current):
    p = analyze(current['hubla_rows'], current['pesquisa_rows'],
                f"{current['short']} — {current['title']} ({current['period']})",
                current['h_email'], current['h_src'], current['h_cont'], current['p_email'])
    return {'all': p}
