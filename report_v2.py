"""Pipeline v2 — Report DP100K-Fp02 multi-turma (Visao Geral + turmas do mes).

Para CADA turma do mes corrente (ex Julho: S1/S2/S3) monta o bloco rico:
  - KPIs canonicos (spend/impr/clicks/visitas/IC da planilha; vendas Hubla date-bucket)
  - split por FUNIL-TIPO: Prospeccao / Quiz / RMKT (classificado pelo token da campanha)
  - top ads (CPA real Hubla + MQL por ad) com thumbnail deduplicado entre turmas
  - qualidade MQL (cross Hubla x Pesquisa, renda >= 10.001)
Mais uma VISAO GERAL do mes (comparativo entre turmas + agregacao por funil + acoes).

Fonte canonica de turma: janelas datetime derivadas da aba Investimento por Hora
(CHAVE horaria, tagada pelo time) -> a MESMA fronteira vale pra spend e pra venda.
A tag manual de Turma no Hubla ATRASA e nao cobre o mes corrente; por isso as
vendas sao bucketadas por data/hora nas janelas canonicas.

Saida: data_v2.json  (consumido por build_v2.py)
"""
import os
import re
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict

import config as C
import sheets_data as SD
from gauth import get_gspread_client, init_meta

HERE = os.path.dirname(os.path.abspath(__file__))
AD_RE = re.compile(r'AD-(\d+)', re.I)

# Planilha de trafego (granular por ad) — tem Instagram Permalink URL + Preview
# Shareable Link por anuncio; fonte canonica pra "ver a midia".
TRAFFIC_SHEET_ID = '1R2MdILmwPZKwBqFpmT5i6VEaiaHYtpwtwCI4F7HLKQo'
TRAFFIC_TAB = 'Página1'
FUNIS = ['prosp', 'quiz', 'rmkt']
FUNIL_LABEL = {'prosp': 'Prospeccao', 'quiz': 'Quiz', 'rmkt': 'RMKT'}


def ad_code(s):
    m = AD_RE.search(s or '')
    return f"AD-{int(m.group(1))}" if m else None


def funnel_of(camp):
    u = (camp or '').upper()
    if 'QUIZ' in u:
        return 'quiz'
    if 'RMKT' in u or 'RKMT' in u or 'REMARKET' in u:
        return 'rmkt'
    return 'prosp'


def _chdt(s):
    s = (s or '').strip()
    for f in ('%Y-%m-%d_%H:%M', '%Y-%m-%d_%H'):
        try:
            return datetime.strptime(s[:16], f)
        except Exception:
            pass
    return None


def _hdt(s):
    s = (s or '').strip()
    for f in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S',
              '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s[:19], f)
        except Exception:
            pass
    return None


def now_brt():
    return datetime.now().strftime('%d/%m/%Y %H:%M')


def _fmt_br(dt):
    return dt.strftime('%d/%m %Hh') if dt else ''


# --------------------------------------------------------------------------
# 1) PLANILHA: janelas canonicas + hubla/pesquisa
# --------------------------------------------------------------------------

def load_sheets():
    cli = get_gspread_client()
    sh = cli.open_by_key(C.CONSOLIDADO_SHEET_ID)
    inv_h, inv_v = SD._read_tab(sh, C.TAB_INVEST)
    hub_h, hub_r = SD._read_tab(sh, C.TAB_HUBLA)
    pes_h, pes_r = SD._read_tab(sh, C.TAB_PESQUISA)
    hd = SD._rows_as_dicts(hub_h, hub_r)
    pd = SD._rows_as_dicts(pes_h, pes_r)

    # email -> renda (Pesquisa inteira)
    p_email = next((h for h in pd[0] if 'mail' in h.lower()), None) if pd else None
    e2r = {}
    for r in pd:
        em = (r.get(p_email, '') or '').strip().lower() if p_email else ''
        rd = (r.get(C.COL_INCOME, '') or '').strip()
        if em and '@' in em and rd:
            e2r.setdefault(em, rd)

    # janelas canonicas por turma (start via CHAVE horaria), contiguas
    starts = {}
    for r in inv_v:
        lbl = (r[C.INV_COL_TURMA] if len(r) > C.INV_COL_TURMA else '').strip()
        if not C.TURMA_RE.match(lbl):
            continue
        dt = _chdt(r[C.INV_COL_CHAVE] if len(r) > C.INV_COL_CHAVE else '')
        if not dt:
            continue
        starts[lbl] = min(starts.get(lbl, dt), dt)
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    now = datetime.now()
    wins = {}
    for i, (lbl, st) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else now
        wins[lbl] = (st, end)

    # KPIs canonicos da Investimento por turma
    sheet_kpi = defaultdict(lambda: dict(spend=0.0, vendas=0, ic=0, visitas=0, impr=0, clicks=0))
    for r in inv_v:
        lbl = (r[C.INV_COL_TURMA] if len(r) > C.INV_COL_TURMA else '').strip()
        if lbl not in wins:
            continue
        K = sheet_kpi[lbl]
        g = lambda i: r[i] if len(r) > i else ''
        K['spend'] += C.parse_money(g(C.INV_COL_INVEST))
        K['vendas'] += C.parse_int(g(C.INV_COL_VENDAS))
        K['ic'] += C.parse_int(g(C.INV_COL_IC))
        K['visitas'] += C.parse_int(g(C.INV_COL_VISITAS))
        K['impr'] += C.parse_int(g(C.INV_COL_IMPR))
        K['clicks'] += C.parse_int(g(C.INV_COL_CLICKS))

    return dict(hd=hd, e2r=e2r, wins=wins, ordered=ordered, sheet_kpi=sheet_kpi, now=now)


def hubla_bucket(hd, e2r, start, end):
    """Vendas Hubla na janela [start,end) -> split por funil (via utm campaign) + por ad + MQL."""
    fun = {f: dict(v=0, vm=0, match=0, mql=0) for f in FUNIS}
    per_ad = defaultdict(lambda: dict(v=0, vm=0, match=0, mql=0, funnel='prosp'))
    tot = dict(v=0, vm=0, match=0, mql=0)
    for r in hd:
        dt = _hdt(r.get('data', ''))
        if not dt or not (start <= dt < end):
            continue
        camp = r.get('utm campaign', '') or ''
        ft = funnel_of(camp)
        code = ad_code(r.get('utm content', '')) or 'sem_utm'
        src = (r.get('utm source', '') or '').lower()
        is_meta = 'meta' in src
        em = (r.get('email', '') or '').strip().lower()
        matched = em in e2r
        is_mql = matched and C.is_mql_renda(e2r[em])

        A = fun[ft]
        A['v'] += 1
        tot['v'] += 1
        pa = per_ad[code]
        pa['v'] += 1
        pa['funnel'] = ft
        if is_meta:
            A['vm'] += 1
            tot['vm'] += 1
            pa['vm'] += 1
            if matched:
                A['match'] += 1
                tot['match'] += 1
                pa['match'] += 1
                if is_mql:
                    A['mql'] += 1
                    tot['mql'] += 1
                    pa['mql'] += 1
    return fun, dict(per_ad), tot


# --------------------------------------------------------------------------
# 2) META: pull por janela (account-level, 1 chamada por nivel)
# --------------------------------------------------------------------------

def _acts(d, kind):
    for a in d.get('actions', []) or []:
        if a.get('action_type') == kind:
            return float(a.get('value', 0))
    return 0.0


def meta_pull_window(acct, since, until):
    """Campanhas + ads DP100K-Fp02 na janela (dia). Retorna (funnel_spend, ads[])."""
    from facebook_business.adobjects.adaccount import AdAccount  # noqa
    tr = {'since': since, 'until': until}

    # funil-tipo via campanha
    fspend = {f: dict(spend=0.0, lpv=0, ic=0, purch=0, impr=0, clicks=0) for f in FUNIS}
    for r in acct.get_insights(params={
            'time_range': tr, 'level': 'campaign', 'limit': 500,
            'fields': ['campaign_name', 'spend', 'impressions', 'clicks',
                       'inline_link_clicks', 'actions']}):
        d = dict(r)
        nm = d.get('campaign_name', '')
        if C.CAMP_MATCH not in nm or C.CAMP_EXCLUDE in nm.upper():
            continue
        F = fspend[funnel_of(nm)]
        F['spend'] += float(d.get('spend', 0))
        F['impr'] += int(d.get('impressions', 0))
        F['clicks'] += int(d.get('clicks', 0))
        F['lpv'] += int(_acts(d, 'landing_page_view'))
        F['ic'] += int(_acts(d, 'initiate_checkout'))
        F['purch'] += int(_acts(d, 'purchase'))

    # ad-level
    ads = []
    for r in acct.get_insights(params={
            'time_range': tr, 'level': 'ad', 'limit': 800,
            'fields': ['ad_id', 'ad_name', 'campaign_name', 'spend', 'impressions',
                       'clicks', 'inline_link_clicks', 'inline_link_click_ctr',
                       'ctr', 'actions']}):
        d = dict(r)
        nm = d.get('campaign_name', '')
        if C.CAMP_MATCH not in nm or C.CAMP_EXCLUDE in nm.upper():
            continue
        ads.append(dict(
            ad_id=d.get('ad_id'), name=d.get('ad_name', ''), camp=nm,
            funnel=funnel_of(nm), code=ad_code(d.get('ad_name', '')),
            spend=float(d.get('spend', 0)), impr=int(d.get('impressions', 0)),
            clicks=int(d.get('clicks', 0)),
            link_clicks=int(d.get('inline_link_clicks', 0) or 0),
            link_ctr=float(d.get('inline_link_click_ctr', 0) or 0),
            ctr=float(d.get('ctr', 0) or 0),
            lpv=int(_acts(d, 'landing_page_view')), ic=int(_acts(d, 'initiate_checkout')),
            purch=int(_acts(d, 'purchase'))))
    return fspend, ads


# --------------------------------------------------------------------------
# 3) THUMBS + status (deduplicado por ad_id, so os que vao aparecer)
# --------------------------------------------------------------------------

def _embed_thumbs_sized(thumb_urls, maxpx=420, quality=78):
    """Baixa thumbs, redimensiona (max maxpx) e devolve data-URIs base64.
    Menor que o _embed_thumbs compartilhado (520px) — sao muitos ads; a midia em
    resolucao real vem pelo link do post (IG/FB)."""
    import io
    import base64
    import urllib.request
    try:
        from PIL import Image
    except Exception:
        return {}
    out, ok, tot = {}, 0, 0
    for aid, url in thumb_urls.items():
        if not url:
            out[aid] = ''
            continue
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            raw = urllib.request.urlopen(req, timeout=30).read()
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            w, h = im.size
            if max(w, h) > maxpx:
                sc = maxpx / max(w, h)
                im = im.resize((int(w * sc), int(h * sc)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=quality, optimize=True)
            b = buf.getvalue()
            out[aid] = 'data:image/jpeg;base64,' + base64.b64encode(b).decode()
            ok += 1
            tot += len(b)
        except Exception:
            out[aid] = ''
    print(f"[thumb] embutidas {ok}/{len(thumb_urls)} (~{tot/1024/1024:.1f} MB)", file=sys.stderr)
    return out


def fetch_thumbs_and_status(ad_ids):
    from facebook_business.adobjects.ad import Ad
    from facebook_business.adobjects.adcreative import AdCreative
    thumb_urls, status, meta_media = {}, {}, {}
    for i, aid in enumerate(ad_ids):
        try:
            info = Ad(aid).api_get(fields=['effective_status'])
            status[aid] = info.get('effective_status', '?')
        except Exception:
            status[aid] = '?'
        try:
            ad_obj = Ad(aid).api_get(fields=['creative'])
            cr_id = ad_obj.get('creative', {}).get('id') if ad_obj.get('creative') else None
            if cr_id:
                cr = AdCreative(cr_id).api_get(
                    fields=['thumbnail_url', 'image_url', 'instagram_permalink_url',
                            'effective_object_story_id'],
                    params={'thumbnail_width': 640, 'thumbnail_height': 640})
                d = dict(cr)
                thumb_urls[aid] = d.get('image_url') or d.get('thumbnail_url') or ''
                fb = ''
                osid = d.get('effective_object_story_id') or ''
                if osid and '_' in osid:
                    pid, post = osid.split('_', 1)
                    fb = f"https://www.facebook.com/{pid}/posts/{post}"
                meta_media[aid] = {'ig': d.get('instagram_permalink_url') or '', 'fb': fb}
            else:
                thumb_urls[aid] = ''
                meta_media[aid] = {'ig': '', 'fb': ''}
        except Exception:
            thumb_urls[aid] = ''
            meta_media[aid] = {'ig': '', 'fb': ''}
        if (i + 1) % 10 == 0:
            print(f"[thumb] {i+1}/{len(ad_ids)}", file=sys.stderr)
    thumbs_b64 = _embed_thumbs_sized(thumb_urls)
    return thumbs_b64, status, meta_media


def load_traffic_media(client):
    """Le a planilha de trafego -> {AD-XX: {ig, fb}} (link mais recente nao-vazio).
    Fonte canonica pra 'ver a midia': Instagram Permalink URL + Preview Shareable Link."""
    try:
        sh = client.open_by_key(TRAFFIC_SHEET_ID)
        ws = sh.worksheet(TRAFFIC_TAB)
        rows = ws.get_all_values()
    except Exception as e:
        print(f"[traffic] ERR: {str(e)[:120]}", file=sys.stderr)
        return {}
    if not rows:
        return {}
    hdr = rows[0]

    def col(*needles):
        for i, h in enumerate(hdr):
            hl = (h or '').lower()
            if all(n in hl for n in needles):
                return i
        return None
    c_ad = col('ad', 'name')
    c_ig = col('instagram', 'permalink')
    c_fb = col('preview', 'shareable')
    c_date = col('date')
    out = {}
    # ordena por data pra pegar o link mais recente por ad
    body = rows[1:]
    if c_date is not None:
        body = sorted(body, key=lambda r: (r[c_date] if len(r) > c_date else ''))
    for r in body:
        code = ad_code(r[c_ad] if c_ad is not None and len(r) > c_ad else '')
        if not code:
            continue
        ig = (r[c_ig] if c_ig is not None and len(r) > c_ig else '') or ''
        fb = (r[c_fb] if c_fb is not None and len(r) > c_fb else '') or ''
        cur = out.setdefault(code, {'ig': '', 'fb': ''})
        if ig.strip():
            cur['ig'] = ig.strip()
        if fb.strip():
            cur['fb'] = fb.strip()
    print(f"[traffic] links de midia: {len(out)} ads", file=sys.stderr)
    return out


# --------------------------------------------------------------------------
# helpers de metrica
# --------------------------------------------------------------------------

def safe_div(a, b):
    return a / b if b else 0.0


def build_funnel_block(ft, hub_fun, meta_fun, canon_spend, meta_total_spend):
    """Monta o bloco de um funil-tipo (prosp/quiz/rmkt) da turma."""
    share = safe_div(meta_fun['spend'], meta_total_spend)
    spend = canon_spend * share  # rateio do investido canonico pela participacao Meta
    vm = hub_fun['vm']
    v = hub_fun['v']
    mql = hub_fun['mql']
    match = hub_fun['match']
    return dict(
        funnel=ft, label=FUNIL_LABEL[ft],
        spend=round(spend, 2), spend_share=round(share * 100, 1),
        vendas=v, vendas_meta=vm,
        cpa_meta=round(safe_div(spend, vm), 2), cpa_all=round(safe_div(spend, v), 2),
        matched=match, mql=mql, mql_pct=round(safe_div(mql, match) * 100, 1),
        cpmql=round(safe_div(spend, mql), 2),
        lpv=meta_fun['lpv'], ic=meta_fun['ic'], purch_pixel=meta_fun['purch'],
        lpv_ic=round(safe_div(meta_fun['ic'], meta_fun['lpv']) * 100, 1))


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    print("[v2] 1/4 planilha (janelas + hubla + pesquisa)...", file=sys.stderr)
    S = load_sheets()
    wins, ordered = S['wins'], S['ordered']

    # turmas do MES corrente = o mes da ultima turma rotulada
    cur_label = ordered[-1][0]
    m = C.TURMA_RE.match(cur_label)
    cur_mes_prefix = f"{m.group(1)}/{m.group(2)}"  # ex "Julho/26"
    mes_turmas = [lbl for lbl, _ in ordered if lbl.startswith(cur_mes_prefix)]
    print(f"[v2] mes={cur_mes_prefix} turmas={mes_turmas}", file=sys.stderr)

    init_meta()
    from facebook_business.adobjects.adaccount import AdAccount
    acct = AdAccount(C.ACCOUNT)

    turmas_out = []
    global_top_ad_ids = set()
    for lbl in mes_turmas:
        start, end = wins[lbl]
        is_current = (lbl == cur_label)
        since = start.strftime('%Y-%m-%d')
        until = end.strftime('%Y-%m-%d')
        print(f"[v2] 2/4 Meta turma {lbl} ({since}..{until})...", file=sys.stderr)

        hub_fun, hub_per_ad, hub_tot = hubla_bucket(S['hd'], S['e2r'], start, end)
        fspend, ads = meta_pull_window(acct, since, until)

        canon = S['sheet_kpi'][lbl]
        meta_total_spend = sum(f['spend'] for f in fspend.values()) or 1.0
        canon_spend = canon['spend'] or meta_total_spend
        scale = safe_div(canon_spend, meta_total_spend)

        # blocos por funil
        funnels = {ft: build_funnel_block(ft, hub_fun[ft], fspend[ft], canon_spend, meta_total_spend)
                   for ft in FUNIS}

        # top ads: agrega meta ad-level por code (soma variacoes do mesmo AD), aplica scale, cruza hubla
        by_code = defaultdict(lambda: dict(spend=0.0, impr=0, clicks=0, link_clicks=0,
                                           lpv=0, ic=0, purch=0, name='', camp='', funnel='prosp',
                                           ad_ids=set()))
        for a in ads:
            code = a['code'] or a['ad_id']
            B = by_code[code]
            B['spend'] += a['spend'] * scale
            B['impr'] += a['impr']
            B['clicks'] += a['clicks']
            B['link_clicks'] += a['link_clicks']
            B['lpv'] += a['lpv']
            B['ic'] += a['ic']
            B['purch'] += a['purch']
            B['funnel'] = a['funnel']
            if not B['name'] or len(a['name']) > len(B['name']):
                B['name'] = a['name']
            B['camp'] = a['camp']
            if a['ad_id']:
                B['ad_ids'].add(a['ad_id'])

        top_ads = []
        for code, B in by_code.items():
            ph = hub_per_ad.get(code, dict(v=0, vm=0, match=0, mql=0))
            vendas_hubla = ph['v']
            top_ads.append(dict(
                code=code, name=B['name'], camp=B['camp'], funnel=B['funnel'],
                spend=round(B['spend'], 2), impr=B['impr'],
                link_ctr=round(safe_div(B['link_clicks'], B['impr']) * 100, 2),
                ctr=round(safe_div(B['clicks'], B['impr']) * 100, 2),
                vendas_hubla=vendas_hubla, vendas_meta=ph['vm'],
                cpa_real=round(safe_div(B['spend'], vendas_hubla), 2),
                matched=ph['match'], mql=ph['mql'],
                mql_pct=round(safe_div(ph['mql'], ph['match']) * 100, 1),
                purch_pixel=B['purch'],
                ad_id=sorted(B['ad_ids'])[0] if B['ad_ids'] else None))
        top_ads.sort(key=lambda x: -x['spend'])
        # marca TODOS os ads com investimento p/ buscar thumb (tabela mostra todos)
        for a in top_ads:
            if a['ad_id'] and a['spend'] >= 1:
                global_top_ad_ids.add(a['ad_id'])

        # KPIs canonicos da turma
        vm = hub_tot['vm']
        vh = hub_tot['v']
        kpi = dict(
            spend=round(canon_spend, 2), vendas_hubla=vh, vendas_meta=vm,
            impr=canon['impr'], clicks=canon['clicks'], visitas=canon['visitas'], ic=canon['ic'],
            ctr=round(safe_div(canon['clicks'], canon['impr']) * 100, 2),
            visita_ic=round(safe_div(canon['ic'], canon['visitas']) * 100, 1),
            ic_venda=round(safe_div(vm, canon['ic']) * 100, 1),
            cpa_meta=round(safe_div(canon_spend, vm), 2),
            cpa_all=round(safe_div(canon_spend, vh), 2),
            matched=hub_tot['match'], mql=hub_tot['mql'],
            mql_pct=round(safe_div(hub_tot['mql'], hub_tot['match']) * 100, 1),
            faturamento=round(vh * 97, 2), roas=round(safe_div(vh * 97, canon_spend), 2))

        turmas_out.append(dict(
            label=lbl, short=C.turma_short(lbl), title=C.turma_title(lbl),
            period=f"{_fmt_br(start)} -> {_fmt_br(end)}",
            since=since, until=until, is_current=is_current,
            kpi=kpi, funnels=funnels, top_ads=top_ads,
            _meta_total_spend=round(meta_total_spend, 2), _scale=round(scale, 4)))

    # thumbs + status (dedupe global) + links de midia
    print(f"[v2] 3/4 thumbs+status de {len(global_top_ad_ids)} ads unicos...", file=sys.stderr)
    thumbs_b64, status, meta_media = ({}, {}, {})
    if global_top_ad_ids:
        thumbs_b64, status, meta_media = fetch_thumbs_and_status(sorted(global_top_ad_ids))
    # links de midia: planilha de trafego (IG real + preview fb.me, por AD-XX) tem
    # prioridade; Meta API (FB post) como fallback -> todo ad fica com "ver midia".
    code_media = load_traffic_media(get_gspread_client())
    media = {}
    for t in turmas_out:
        for a in t['top_ads']:
            aid = a['ad_id']
            if not aid:
                continue
            mm = meta_media.get(aid, {'ig': '', 'fb': ''})
            sm = code_media.get(a['code'] or '', {'ig': '', 'fb': ''})
            ig = sm.get('ig') or mm.get('ig') or ''
            fb = sm.get('fb') or mm.get('fb') or ''
            if ig or fb:
                media[aid] = {'ig': ig, 'fb': fb}

    # overview do mes
    print("[v2] 4/4 visao geral + acoes...", file=sys.stderr)
    overview = build_overview(turmas_out, cur_mes_prefix)

    data = dict(
        account=C.ACCOUNT, updated_at=now_brt(),
        month_label=cur_mes_prefix, cur_label=cur_label,
        turmas=turmas_out, overview=overview,
        thumbs_b64=thumbs_b64, ad_status=status, media_links=media)

    out = os.path.join(HERE, 'data_v2.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"[v2] data_v2.json: {os.path.getsize(out)/1024/1024:.2f} MB", file=sys.stderr)
    return data


def build_overview(turmas, mes):
    """Consolida o mes + gera comparativo entre turmas + agregacao por funil + acoes."""
    tot = dict(spend=0.0, vendas=0, vendas_meta=0, matched=0, mql=0)
    fun_agg = {f: dict(spend=0.0, vendas=0, vendas_meta=0, matched=0, mql=0, lpv=0, ic=0)
               for f in FUNIS}
    for t in turmas:
        k = t['kpi']
        tot['spend'] += k['spend']
        tot['vendas'] += k['vendas_hubla']
        tot['vendas_meta'] += k['vendas_meta']
        tot['matched'] += k['matched']
        tot['mql'] += k['mql']
        for ft in FUNIS:
            b = t['funnels'][ft]
            A = fun_agg[ft]
            A['spend'] += b['spend']
            A['vendas'] += b['vendas']
            A['vendas_meta'] += b['vendas_meta']
            A['matched'] += b['matched']
            A['mql'] += b['mql']
            A['lpv'] += b['lpv']
            A['ic'] += b['ic']

    month_kpi = dict(
        spend=round(tot['spend'], 2), vendas=tot['vendas'], vendas_meta=tot['vendas_meta'],
        cpa_meta=round(safe_div(tot['spend'], tot['vendas_meta']), 2),
        cpa_all=round(safe_div(tot['spend'], tot['vendas']), 2),
        matched=tot['matched'], mql=tot['mql'],
        mql_pct=round(safe_div(tot['mql'], tot['matched']) * 100, 1),
        faturamento=round(tot['vendas'] * 97, 2),
        roas=round(safe_div(tot['vendas'] * 97, tot['spend']), 2))

    funis = []
    for ft in FUNIS:
        A = fun_agg[ft]
        funis.append(dict(
            funnel=ft, label=FUNIL_LABEL[ft],
            spend=round(A['spend'], 2),
            spend_share=round(safe_div(A['spend'], tot['spend']) * 100, 1),
            vendas=A['vendas'], vendas_meta=A['vendas_meta'],
            cpa_meta=round(safe_div(A['spend'], A['vendas_meta']), 2),
            matched=A['matched'], mql=A['mql'],
            mql_pct=round(safe_div(A['mql'], A['matched']) * 100, 1),
            cpmql=round(safe_div(A['spend'], A['mql']), 2)))

    acoes = gen_acoes(turmas, funis, month_kpi)
    return dict(month_kpi=month_kpi, funis=funis, acoes=acoes,
                trend=[dict(short=t['short'], title=t['title'], period=t['period'],
                            is_current=t['is_current'], kpi=t['kpi'],
                            mix={ft: t['funnels'][ft]['spend_share'] for ft in FUNIS})
                       for t in turmas])


def gen_acoes(turmas, funis, month_kpi):
    """Pontos de otimizacao no estilo Jerry (regra + confianca)."""
    A = []
    fmap = {f['funnel']: f for f in funis}
    prosp, quiz, rmkt = fmap['prosp'], fmap['quiz'], fmap['rmkt']

    # 1) RMKT dilui MQL?
    if rmkt['vendas_meta'] >= 8 and rmkt['mql_pct'] + 8 < prosp['mql_pct']:
        A.append(dict(
            tag='QUALIDADE', dono='trafego', conf='ALTA',
            titulo='RMKT escala volume mas dilui MQL',
            texto=(f"RMKT no mes: {rmkt['vendas']} vendas ({rmkt['spend_share']}% do spend) "
                   f"a MQL {rmkt['mql_pct']}% vs Prospeccao {prosp['mql_pct']}%. "
                   f"Puxa CPA pra baixo mas entrega lead de renda menor. "
                   f"Acao: segmentar RMKT por janela quente (visitantes IC/checkout) e "
                   f"medir MQL isolado antes de somar verba.")))
    # 2) Quiz amostra pequena?
    if quiz['vendas_meta'] < 15:
        A.append(dict(
            tag='AMOSTRA', dono='trafego', conf='MEDIA',
            titulo='Quiz com volume baixo — veredito inconclusivo',
            texto=(f"Quiz no mes: {quiz['vendas_meta']} vendas meta / {quiz['matched']} matched. "
                   f"Amostra pequena p/ cravar MQL ({quiz['mql_pct']}%). "
                   f"Acao: manter verba de teste, so escalar com >=20 vendas maduras (pesquisa atrasa ~5-7d).")))
    # 3) tendencia de CPA meta entre turmas
    if len(turmas) >= 2:
        prev, cur = turmas[-2]['kpi'], turmas[-1]['kpi']
        if cur['cpa_meta'] > prev['cpa_meta'] * 1.15 and turmas[-1]['is_current']:
            A.append(dict(
                tag='CPA', dono='trafego', conf='MEDIA',
                titulo='CPA meta subindo na turma atual',
                texto=(f"CPA meta {turmas[-1]['short']} R$ {cur['cpa_meta']:.0f} vs "
                       f"{turmas[-2]['short']} R$ {prev['cpa_meta']:.0f} (+{(cur['cpa_meta']/prev['cpa_meta']-1)*100:.0f}%). "
                       f"Turma corrente parcial — reavaliar no fechamento.")))
    # 4) tendencia de MQL rate
    if len(turmas) >= 2:
        prev, cur = turmas[-2]['kpi'], turmas[-1]['kpi']
        if cur['mql_pct'] + 4 < prev['mql_pct']:
            A.append(dict(
                tag='QUALIDADE', dono='trafego/comercial', conf='MEDIA',
                titulo='MQL rate caindo vs turma anterior',
                texto=(f"MQL {turmas[-1]['short']} {cur['mql_pct']}% vs {turmas[-2]['short']} {prev['mql_pct']}%. "
                       f"Cruzar com o mix de funil (RMKT dilui) e com maturidade da pesquisa.")))
    # 5) meta de MQL do funil (50%)
    if month_kpi['mql_pct'] < 45:
        A.append(dict(
            tag='META', dono='trafego', conf='ALTA',
            titulo='MQL do mes abaixo da meta (50%)',
            texto=(f"MQL blended {month_kpi['mql_pct']}% (meta 50%). "
                   f"Gargalo historico do funil = renda do publico, nao a pagina. "
                   f"Acao: priorizar publicos/criativos que puxam renda >= 10k, nao so CPA barato.")))
    # 6) RMKT eficiente mas com teto (colheita de publico quente)
    if rmkt['vendas_meta'] >= 8 and rmkt['cpmql'] > 0 and rmkt['cpmql'] < prosp['cpmql']:
        A.append(dict(
            tag='TETO', dono='trafego', conf='ALTA',
            titulo='RMKT e eficiente, mas nao escala como prospeccao',
            texto=(f"RMKT entrega MQL a R$ {rmkt['cpmql']:.0f} (vs Prospeccao R$ {prosp['cpmql']:.0f}) e "
                   f"CPA R$ {rmkt['cpa_meta']:.0f} — parece o mais barato, mas e COLHEITA de "
                   f"publico quente (visitantes), pool finito. Manter com teto de verba; "
                   f"o crescimento incremental vem da PROSPECCAO, nao de empilhar RMKT.")))
    # 7) melhor bloco FRIO por CPMQL (prospeccao/quiz — o que realmente escala)
    frios = sorted([f for f in funis if f['funnel'] in ('prosp', 'quiz') and f['mql'] > 0],
                   key=lambda x: x['cpmql'])
    if frios:
        best = frios[0]
        A.append(dict(
            tag='ESCALA', dono='trafego', conf='MEDIA',
            titulo=f"Melhor bloco frio p/ escalar: {best['label']}",
            texto=(f"Entre os blocos que geram demanda nova (prospeccao/quiz), {best['label']} "
                   f"entrega MQL a R$ {best['cpmql']:.0f} ({best['mql']} MQL / R$ {best['spend']:.0f}, "
                   f"MQL {best['mql_pct']:.0f}%). Candidato a mais verba com qualidade preservada.")))
    return A


if __name__ == '__main__':
    main()
