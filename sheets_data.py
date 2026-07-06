"""Camada de planilha — detecta a turma atual e monta KPIs de todas as turmas.

A tabela de tendencia das 4 turmas sai INTEIRA daqui (Investimento por Hora +
Hubla + Pesquisa). So a turma atual carrega tambem as linhas cruas de Hubla e
Pesquisa (usadas por persona/rank/daily) + o mapa email->renda.
"""
import re
from collections import defaultdict, Counter
from datetime import date, timedelta

import config as C
from gauth import get_gspread_client

AD_RE = re.compile(r'AD-(\d+)', re.I)


def ad_code(s):
    m = AD_RE.search(s or '')
    return f"AD-{int(m.group(1))}" if m else None


def _pdate(s):
    y, m, d = s.split('-')
    return date(int(y), int(m), int(d))


def _read_tab(sh, tab):
    """Retorna (header, rows) — header disambigua colunas duplicadas (ex: 2x 'Turma')."""
    ws = sh.worksheet(tab)
    rows = ws.get_all_values()
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _rows_as_dicts(header, rows):
    seen = {}
    norm = []
    for h in header:
        h = h or ''
        if h in seen:
            seen[h] += 1
            norm.append(f"{h}__{seen[h]}")
        else:
            seen[h] = 1
            norm.append(h)
    out = []
    for r in rows:
        if not any((c or '').strip() for c in r):
            continue
        out.append({h: (r[i] if i < len(r) else '') for i, h in enumerate(norm)})
    return out


def _turma_cols(header):
    return [i for i, h in enumerate(header) if 'turma' in (h or '').lower()]


def _col(header, *needles):
    for i, h in enumerate(header):
        hl = (h or '').lower()
        if all(n in hl for n in needles):
            return i
    return None


# ---------------------------------------------------------------------------

def detect_turmas(invest_values):
    """Descobre turmas semanais rotuladas + a turma ATUAL (ultima) e sua janela.
    Retorna (ordered[list of (label, {dmin,dmax})], cur_label, since, until)."""
    labeled = {}
    max_date_all = ''
    for r in invest_values:
        if not r:
            continue
        d = (r[C.INV_COL_DATA] if len(r) > C.INV_COL_DATA else '').strip()[:10]
        if d and d > max_date_all:
            max_date_all = d
        lbl = (r[C.INV_COL_TURMA] if len(r) > C.INV_COL_TURMA else '').strip()
        if not C.TURMA_RE.match(lbl) or not d:
            continue
        L = labeled.setdefault(lbl, {"dmin": d, "dmax": d})
        if d < L["dmin"]:
            L["dmin"] = d
        if d > L["dmax"]:
            L["dmax"] = d

    if not labeled:
        raise SystemExit("[sheets] nenhuma turma semanal rotulada na Investimento por Hora")

    ordered = sorted(labeled.items(), key=lambda kv: kv[1]["dmin"])
    cur_label, cur = ordered[-1]
    since = cur["dmin"]
    until = cur["dmax"]
    # estende 'until' pra incluir a cauda ainda nao-rotulada da turma atual
    if max_date_all > until:
        win_end = _pdate(since) + timedelta(days=C.TURMA_DAYS + C.TURMA_TAIL_SLACK)
        if _pdate(max_date_all) <= win_end:
            until = max_date_all
    return ordered, cur_label, since, until


def _turma_T(invest_values, label, since=None, until=None, current=False):
    T = dict(spend=0.0, vendas=0, ic=0, visitas=0, impr=0, clicks=0)
    for r in invest_values:
        if not r:
            continue
        lbl = (r[C.INV_COL_TURMA] if len(r) > C.INV_COL_TURMA else '').strip()
        d = (r[C.INV_COL_DATA] if len(r) > C.INV_COL_DATA else '').strip()[:10]
        match = (lbl == label)
        if current and not match and lbl == '' and d and since <= d <= until:
            match = True   # cauda nao-rotulada da turma aberta
        if not match:
            continue
        T['spend']   += C.parse_money(r[C.INV_COL_INVEST]) if len(r) > C.INV_COL_INVEST else 0
        T['vendas']  += C.parse_int(r[C.INV_COL_VENDAS]) if len(r) > C.INV_COL_VENDAS else 0
        T['ic']      += C.parse_int(r[C.INV_COL_IC]) if len(r) > C.INV_COL_IC else 0
        T['visitas'] += C.parse_int(r[C.INV_COL_VISITAS]) if len(r) > C.INV_COL_VISITAS else 0
        T['impr']    += C.parse_int(r[C.INV_COL_IMPR]) if len(r) > C.INV_COL_IMPR else 0
        T['clicks']  += C.parse_int(r[C.INV_COL_CLICKS]) if len(r) > C.INV_COL_CLICKS else 0
    return T


def _derive_TL(T):
    spend, impr, clicks = T['spend'], T['impr'], T['clicks']
    lpv, ic, purch = T['visitas'], T['ic'], T['vendas']
    return dict(
        spend=spend, impr=impr, clicks=clicks, link_clicks=0, lpv=lpv, ic=ic,
        atc=0, purch=purch, reach=0,
        ctr=clicks / impr * 100 if impr else 0, link_ctr=0,
        cpc=spend / clicks if clicks else 0, cpm=spend / impr * 1000 if impr else 0,
        cpa=spend / purch if purch else 0,
        lpv_ic=ic / lpv * 100 if lpv else 0, ic_v=purch / ic * 100 if ic else 0,
    )


def _turma_S_MW(hubla_dicts, pesq_dicts, label, email2renda, h_email, h_src, h_cont):
    hubla_total = vendas_meta = matched = mql = 0
    pesq_total = 0
    for r in pesq_dicts:
        if _row_turma(r) == label:
            pesq_total += 1
    for r in hubla_dicts:
        if _row_turma(r) != label:
            continue
        hubla_total += 1
        src = (r.get(h_src, '') or '').lower()
        if 'meta' not in src:
            continue
        vendas_meta += 1
        em = (r.get(h_email, '') or '').strip().lower()
        if em in email2renda:
            matched += 1
            if C.is_mql_renda(email2renda[em]):
                mql += 1
    S = dict(
        hubla_total=hubla_total, hubla_meta_ads=vendas_meta, pesquisa_total=pesq_total,
        vendas_meta=vendas_meta, vendas_meta_matched=matched,
        match_pct=(matched / vendas_meta * 100 if vendas_meta else 0),
        pesquisa_mql=mql, pesquisa_mql_pct=(mql / matched * 100 if matched else 0),
    )
    MW = dict(vendas_meta=vendas_meta, matched=matched, mql=mql,
              mql_pct=(mql / matched * 100 if matched else 0))
    return S, MW


_TURMA_KEYS = None


def _row_turma(d):
    """Le a coluna Turma de um dict de linha (pode haver 'Turma' e 'Turma__2')."""
    for k in ('Turma', 'Turma__2', 'turma'):
        v = (d.get(k, '') or '').strip()
        if v:
            return v
    return ''


def pull():
    client = get_gspread_client()
    sh = client.open_by_key(C.CONSOLIDADO_SHEET_ID)

    inv_header, inv_values = _read_tab(sh, C.TAB_INVEST)
    hub_header, hub_rows = _read_tab(sh, C.TAB_HUBLA)
    pes_header, pes_rows = _read_tab(sh, C.TAB_PESQUISA)

    hubla_dicts = _rows_as_dicts(hub_header, hub_rows)
    pesq_dicts = _rows_as_dicts(pes_header, pes_rows)

    # indices de coluna (Hubla)
    h_email = next((h for h in hubla_dicts[0].keys() if h.strip().lower() == 'email'), None) if hubla_dicts else None
    h_src = next((h for h in hubla_dicts[0].keys() if 'utm' in h.lower() and 'source' in h.lower()), None) if hubla_dicts else None
    h_cont = next((h for h in hubla_dicts[0].keys() if 'utm' in h.lower() and 'content' in h.lower()), None) if hubla_dicts else None
    h_date = next((h for h in hubla_dicts[0].keys() if h.strip().lower() == 'data'), None) if hubla_dicts else None

    # email -> renda (Pesquisa inteira; renda e atributo da pessoa, nao da turma)
    p_email = next((h for h in pesq_dicts[0].keys() if 'mail' in h.lower()), None) if pesq_dicts else None
    email2renda = {}
    for r in pesq_dicts:
        em = (r.get(p_email, '') or '').strip().lower() if p_email else ''
        rd = (r.get(C.COL_INCOME, '') or '').strip()
        if em and '@' in em and rd:
            email2renda.setdefault(em, rd)

    ordered, cur_label, since, until = detect_turmas(inv_values)

    # ultimas N turmas (inclui a atual)
    window = ordered[-C.N_TURMAS:]
    turmas = []
    for label, meta in window:
        is_current = (label == cur_label)
        T = _turma_T(inv_values, label,
                     since=since if is_current else None,
                     until=until if is_current else None,
                     current=is_current)
        S, MW = _turma_S_MW(hubla_dicts, pesq_dicts, label, email2renda, h_email, h_src, h_cont)
        TL = _derive_TL(T)
        dmin, dmax = meta["dmin"], (until if is_current else meta["dmax"])
        turmas.append({
            "label": label,
            "short": C.turma_short(label),
            "title": C.turma_title(label),
            "since": dmin,
            "until": dmax,
            "period": f"{_fmt_br(dmin)} → {_fmt_br(dmax)}",
            "is_current": is_current,
            "T": T, "S": S, "TL": TL, "MW": MW,
        })

    # ---- detalhe da turma atual ----
    cur_hubla = [r for r in hubla_dicts if _row_turma(r) == cur_label]
    cur_pesq = [r for r in pesq_dicts if _row_turma(r) == cur_label]

    # mql_per_ad (por AD-XX) da turma atual
    mql_per_ad = defaultdict(lambda: dict(total=0, mql=0, vendas=0))
    for r in cur_hubla:
        src = (r.get(h_src, '') or '').lower()
        if 'meta' not in src:
            continue
        code = ad_code(r.get(h_cont, '')) or 'unknown'
        mql_per_ad[code]['vendas'] += 1
        em = (r.get(h_email, '') or '').strip().lower()
        if em in email2renda:
            mql_per_ad[code]['total'] += 1
            if C.is_mql_renda(email2renda[em]):
                mql_per_ad[code]['mql'] += 1

    # dias da turma (p/ grafico diario)
    days = []
    d = _pdate(since)
    dend = _pdate(until)
    while d <= dend:
        days.append(d.isoformat())
        d += timedelta(days=1)

    cur = turmas[-1]
    current = dict(cur)
    current.update({
        "days": days,
        "hubla_rows": cur_hubla,
        "pesquisa_rows": cur_pesq,
        "email2renda": email2renda,
        "mql_per_ad": {k: dict(v) for k, v in mql_per_ad.items()},
        "stats": cur["S"],
        "h_email": h_email, "h_src": h_src, "h_cont": h_cont, "h_date": h_date,
        "p_email": p_email,
    })

    return {"turmas": turmas, "current": current, "cur_label": cur_label,
            "since": since, "until": until, "ordered_labels": [l for l, _ in ordered]}


def _fmt_br(iso):
    try:
        y, m, d = iso.split('-')
        return f"{d}/{m}/{y}"
    except Exception:
        return iso


if __name__ == "__main__":
    data = sheets = pull()
    print("Turma atual:", data["cur_label"], data["since"], "->", data["until"])
    for t in data["turmas"]:
        T, S, MW = t["T"], t["S"], t["MW"]
        print(f"  {t['short']:8s} {t['period']:24s} spend R${T['spend']:>9,.0f}  "
              f"hubla {S['hubla_total']:3d} (meta {S['hubla_meta_ads']:3d})  "
              f"MQL {MW['mql']:2d}/{MW['matched']:2d} ({MW['mql_pct']:.0f}%)")
    cur = data["current"]
    print(f"  current detail: hubla_rows={len(cur['hubla_rows'])} pesq_rows={len(cur['pesquisa_rows'])} "
          f"email2renda={len(cur['email2renda'])} ads={len(cur['mql_per_ad'])} days={len(cur['days'])}")
