"""Orquestrador do REPORT LIVE DP100K-Fp02.

detecta turma atual (planilha) -> KPIs de 4 turmas -> Meta da turma atual ->
persona + rank + serie diaria -> _build_data.json -> build.py -> index.html
"""
import os
import re
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import config as C
import sheets_data
import meta_data
import persona as persona_mod
import rank as rank_mod

HERE = os.path.dirname(os.path.abspath(__file__))
AD_RE = re.compile(r'AD-(\d+)', re.I)


def ad_code(s):
    m = AD_RE.search(s or '')
    return f"AD-{int(m.group(1))}" if m else None


def now_brt():
    return datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')


def main():
    print("[run] 1/5 planilha (turmas + turma atual)...", file=sys.stderr)
    sd = sheets_data.pull()
    turmas = sd['turmas']
    cur = sd['current']
    since, until = sd['since'], sd['until']
    print(f"[run] turma atual: {cur['label']} ({cur['period']}) · {len(turmas)} turmas na janela", file=sys.stderr)

    print("[run] 2/5 Meta (turma atual)...", file=sys.stderr)
    meta = meta_data.pull(since, until, cur['days'])

    print("[run] 3/5 persona + rank...", file=sys.stderr)
    pers = persona_mod.build(cur)
    window_label = f"{cur['short']} ({cur['period']})"
    top_ads = rank_mod.build(meta['ads'], cur['hubla_rows'], cur['mql_per_ad'],
                             cur['h_src'], cur['h_cont'], window_label)

    print("[run] 4/5 serie diaria (Hubla por dia)...", file=sys.stderr)
    days = cur['days']
    quiz_codes = set()
    for a in meta['ads']:
        if C.QUIZ_KEYWORD in (a.get('campaign_name', '') or '').upper() and a.get('spend', 0) > 0:
            cc = ad_code(a.get('name', ''))
            if cc:
                quiz_codes.add(cc)
    hubla_overall = {d: dict(vendas_total=0, vendas_meta=0) for d in days}
    hubla_quiz = {d: 0 for d in days}
    h_date, h_src, h_cont = cur['h_date'], cur['h_src'], cur['h_cont']
    for r in cur['hubla_rows']:
        day = (r.get(h_date, '') or '')[:10] if h_date else ''
        if day not in hubla_overall:
            continue
        hubla_overall[day]['vendas_total'] += 1
        if 'meta' in (r.get(h_src, '') or '').lower():
            hubla_overall[day]['vendas_meta'] += 1
            if ad_code(r.get(h_cont, '')) in quiz_codes:
                hubla_quiz[day] += 1
    daily = dict(meta['daily'])
    daily['hubla_overall'] = hubla_overall
    daily['hubla_quiz'] = hubla_quiz
    daily['quiz_codes'] = sorted(quiz_codes)

    current_build = {
        'label': cur['label'], 'short': cur['short'], 'title': cur['title'], 'period': cur['period'],
        'camps': meta['camps'], 'ads': meta['ads'], 'breakdowns': meta['breakdowns'],
        'fatigue': meta['fatigue'], 'topline': meta['topline'],
        'previews': meta['previews'], 'copies': meta['copies'], 'thumbs_b64': meta['thumbs_b64'],
        'daily': daily, 'persona': pers, 'top_ads': top_ads,
        'mql_per_ad': cur['mql_per_ad'], 'email2renda': cur['email2renda'], 'stats': cur['S'],
    }
    turmas_build = [{k: t[k] for k in ('label', 'short', 'title', 'period', 'T', 'S', 'TL', 'MW')}
                    for t in turmas]

    data = {
        'account': C.ACCOUNT, 'updated_at': now_brt(),
        'turmas': turmas_build, 'current': current_build,
    }

    build_path = os.path.join(HERE, '_build_data.json')
    with open(build_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"[run] _build_data.json: {os.path.getsize(build_path)/1024/1024:.1f} MB", file=sys.stderr)

    print("[run] 5/5 build index.html...", file=sys.stderr)
    env = dict(os.environ, BUILD_DATA=build_path, BUILD_OUT=os.path.join(HERE, 'index.html'))
    subprocess.run([sys.executable, os.path.join(HERE, 'build.py')], check=True, env=env)
    print("[run] OK.", file=sys.stderr)


if __name__ == "__main__":
    main()
