"""Builder v2 — HTML self-contained do report DP100K-Fp02 multi-turma.

Le data_v2.json (report_v2.py) -> index.html.
Estrutura: [Visao Geral | <turmas do mes>]  com blocos isolados Prospeccao/Quiz/RMKT,
top ads (CPA real Hubla + MQL) e qualidade MQL. Sem libs externas, sem emojis.
"""
import os
import json
import html

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('BUILD_DATA', os.path.join(HERE, 'data_v2.json'))
OUT = os.environ.get('BUILD_OUT', os.path.join(HERE, 'index.html'))

FUN_COLOR = {'prosp': '#3B82F6', 'quiz': '#8B5CF6', 'rmkt': '#F59E0B'}
FUN_LABEL = {'prosp': 'Prospeccao', 'quiz': 'Quiz', 'rmkt': 'RMKT'}
FUN_DESC = {'prosp': 'Publico frio — gera demanda nova',
            'quiz': 'Publico frio via quiz — qualifica na entrada',
            'rmkt': 'Publico quente — colheita (pool finito)'}


def esc(s):
    return html.escape(str(s if s is not None else ''))


def brl(v, dec=0):
    try:
        v = float(v)
    except Exception:
        return '-'
    s = f"{v:,.{dec}f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"R$ {s}"


def num(v):
    try:
        return f"{int(round(float(v))):,}".replace(',', '.')
    except Exception:
        return '-'


def pct(v, dec=0):
    try:
        return f"{float(v):.{dec}f}%".replace('.', ',')
    except Exception:
        return '-'


# --- classificadores de cor ---
def cls_mql(p):
    p = float(p or 0)
    return 'g' if p >= 45 else ('a' if p >= 30 else 'r')


def cls_cpa(v):
    v = float(v or 0)
    if v <= 0:
        return ''
    return 'g' if v <= 170 else ('a' if v <= 230 else 'r')


# ---------------------------------------------------------------- KPI tiles
def kpi_tile(label, value, sub='', tone=''):
    return (f'<div class="tile {tone}"><div class="tl">{esc(label)}</div>'
            f'<div class="tv">{value}</div>'
            f'<div class="ts">{sub}</div></div>')


def kpi_row(tiles):
    return '<div class="tiles">' + ''.join(tiles) + '</div>'


# ---------------------------------------------------------------- funil cards
def funnel_card(b, spend_ref):
    ft = b['funnel']
    color = FUN_COLOR[ft]
    barw = min(100, b['spend_share'])
    mqlc = cls_mql(b['mql_pct'])
    cpac = cls_cpa(b['cpa_meta'])
    return f'''
    <div class="fcard" style="border-top:4px solid {color}">
      <div class="fhead"><span class="fname" style="color:{color}">{esc(b['label'])}</span>
        <span class="fshare">{pct(b['spend_share'],0)} do spend</span></div>
      <div class="fdesc">{esc(FUN_DESC[ft])}</div>
      <div class="fbar"><span style="width:{barw}%;background:{color}"></span></div>
      <table class="fmini">
        <tr><td>Investido</td><td>{brl(b['spend'])}</td></tr>
        <tr><td>Vendas (meta)</td><td>{num(b['vendas'])} <span class="muted">({num(b['vendas_meta'])})</span></td></tr>
        <tr><td>CPA meta</td><td class="c-{cpac}">{brl(b['cpa_meta'])}</td></tr>
        <tr><td>MQL rate</td><td class="c-{mqlc}">{pct(b['mql_pct'],0)} <span class="muted">({b['mql']}/{b['matched']})</span></td></tr>
        <tr><td>Custo / MQL</td><td>{brl(b['cpmql']) if b['mql'] else '-'}</td></tr>
      </table>
    </div>'''


# ---------------------------------------------------------------- top ads table
def ads_table(top_ads, thumbs, status, limit=12):
    rows = []
    for a in top_ads[:limit]:
        if a['spend'] < 1:
            continue
        thumb = thumbs.get(a['ad_id'] or '', '')
        img = (f'<img src="{thumb}" class="thumb">' if thumb
               else '<div class="thumb noimg"></div>')
        st = status.get(a['ad_id'] or '', '')
        stdot = 'on' if st == 'ACTIVE' else 'off'
        color = FUN_COLOR.get(a['funnel'], '#888')
        cpac = cls_cpa(a['cpa_real']) if a['vendas_hubla'] else ''
        mqlc = cls_mql(a['mql_pct']) if a['matched'] else ''
        rows.append(f'''
        <tr data-funnel="{a['funnel']}">
          <td class="adcell">{img}
            <div><span class="adcode">{esc(a['code'] or a['name'][:16])}</span>
              <span class="fchip" style="background:{color}22;color:{color}">{FUN_LABEL[a['funnel']]}</span>
              <span class="stdot {stdot}" title="{esc(st)}"></span>
              <div class="adname">{esc((a['name'] or '')[:52])}</div></div></td>
          <td class="r">{brl(a['spend'])}</td>
          <td class="r">{num(a['vendas_hubla'])}</td>
          <td class="r c-{cpac}">{brl(a['cpa_real']) if a['vendas_hubla'] else '-'}</td>
          <td class="r c-{mqlc}">{pct(a['mql_pct'],0) if a['matched'] else '-'}<span class="muted"> {a['mql']}/{a['matched']}</span></td>
          <td class="r">{pct(a['link_ctr'],2)}</td>
        </tr>''')
    return f'''
    <div class="afilter">
      <span>Filtrar:</span>
      <button class="fbtn active" data-f="all">Todos</button>
      <button class="fbtn" data-f="prosp">Prospeccao</button>
      <button class="fbtn" data-f="quiz">Quiz</button>
      <button class="fbtn" data-f="rmkt">RMKT</button>
    </div>
    <div class="tblwrap"><table class="ads">
      <thead><tr><th>Anuncio</th><th class="r">Investido</th><th class="r">Vendas Hubla</th>
        <th class="r">CPA real</th><th class="r">MQL</th><th class="r">CTR link</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>'''


# ---------------------------------------------------------------- funil visual (barra de etapas)
def funnel_steps(kpi):
    steps = [('Impressoes', num(kpi['impr'])), ('Cliques', num(kpi['clicks'])),
             ('Visitas', num(kpi['visitas'])), ('Checkout', num(kpi['ic'])),
             ('Vendas', num(kpi['vendas_hubla']))]
    conv = [('', ''), ('CTR ' + pct(kpi['ctr'], 2), ''),
            ('', ''), ('Visita->IC ' + pct(kpi['visita_ic'], 1), ''),
            ('IC->Venda ' + pct(kpi['ic_venda'], 1), '')]
    cells = []
    for i, (lb, v) in enumerate(steps):
        conv_lb = conv[i][0]
        cells.append(f'''<div class="fstep">
          <div class="fstep-v">{v}</div><div class="fstep-l">{lb}</div>
          {'<div class="fstep-c">'+conv_lb+'</div>' if conv_lb else ''}</div>''')
    return '<div class="funnel-steps">' + '<div class="fsep">&rsaquo;</div>'.join(cells) + '</div>'


# ---------------------------------------------------------------- turma panel
def turma_panel(t, thumbs, status, idx):
    k = t['kpi']
    partial = ' <span class="badge-live">turma aberta (parcial)</span>' if t['is_current'] else ''
    tiles = [
        kpi_tile('Investido', brl(k['spend']), t['period']),
        kpi_tile('Vendas Hubla', num(k['vendas_hubla']), f"meta: {num(k['vendas_meta'])}"),
        kpi_tile('CPA meta', brl(k['cpa_meta']), 'spend / venda meta', 'c-' + cls_cpa(k['cpa_meta'])),
        kpi_tile('MQL rate', pct(k['mql_pct'], 0), f"{k['mql']}/{k['matched']} renda >=10k", 'c-' + cls_mql(k['mql_pct'])),
        kpi_tile('ROAS ingresso', f"{str(k['roas']).replace('.',',')}x", brl(k['faturamento']) + ' fat.'),
        kpi_tile('Visita->IC / IC->Venda', pct(k['visita_ic'], 1) + ' / ' + pct(k['ic_venda'], 1), 'pagina / checkout'),
    ]
    fcards = ''.join(funnel_card(t['funnels'][ft], k['spend']) for ft in ('prosp', 'quiz', 'rmkt'))
    return f'''
    <section class="panel" id="turma-{idx}" style="display:none">
      <h2>{esc(t['title'])}{partial}</h2>
      {kpi_row(tiles)}
      <h3>Funil da turma <span class="hnote">(planilha — hora-exato)</span></h3>
      {funnel_steps(k)}
      <h3>Blocos isolados <span class="hnote">Prospeccao / Quiz / RMKT</span></h3>
      <div class="fcards">{fcards}</div>
      <h3>Desempenho por anuncio <span class="hnote">CPA real = Investido Meta / Vendas Hubla (utm_content)</span></h3>
      {ads_table(t['top_ads'], thumbs, status)}
    </section>'''


# ---------------------------------------------------------------- overview panel
def overview_panel(ov, month_label):
    mk = ov['month_kpi']
    tiles = [
        kpi_tile('Investido no mes', brl(mk['spend']), month_label),
        kpi_tile('Vendas Hubla', num(mk['vendas']), f"meta: {num(mk['vendas_meta'])}"),
        kpi_tile('CPA meta', brl(mk['cpa_meta']), 'blended', 'c-' + cls_cpa(mk['cpa_meta'])),
        kpi_tile('MQL rate', pct(mk['mql_pct'], 0), f"{mk['mql']}/{mk['matched']} (meta 50%)", 'c-' + cls_mql(mk['mql_pct'])),
        kpi_tile('ROAS ingresso', f"{str(mk['roas']).replace('.',',')}x", brl(mk['faturamento']) + ' fat.'),
        kpi_tile('MQL no mes', num(mk['mql']), 'renda >= R$ 10.001'),
    ]
    # acoes
    acards = []
    for a in ov['acoes']:
        acards.append(f'''<div class="acard conf-{a['conf'].lower()}">
          <div class="atop"><span class="atag">{esc(a['tag'])}</span>
            <span class="aconf">{esc(a['conf'])}</span>
            <span class="adono">{esc(a['dono'])}</span></div>
          <div class="atitle">{esc(a['titulo'])}</div>
          <div class="atext">{esc(a['texto'])}</div></div>''')
    # trend table
    trows = []
    for tr in ov['trend']:
        k = tr['kpi']
        cur = ' cur' if tr['is_current'] else ''
        mix = tr['mix']
        mixbar = (f'<div class="mixbar">'
                  f'<span style="width:{mix["prosp"]}%;background:{FUN_COLOR["prosp"]}" title="Prospeccao {mix["prosp"]}%"></span>'
                  f'<span style="width:{mix["quiz"]}%;background:{FUN_COLOR["quiz"]}" title="Quiz {mix["quiz"]}%"></span>'
                  f'<span style="width:{mix["rmkt"]}%;background:{FUN_COLOR["rmkt"]}" title="RMKT {mix["rmkt"]}%"></span></div>')
        trows.append(f'''<tr class="{cur.strip()}">
          <td class="l">{esc(tr['short'])}{' (parcial)' if tr['is_current'] else ''}<div class="muted">{esc(tr['period'])}</div></td>
          <td class="r">{brl(k['spend'])}</td>
          <td class="r">{num(k['vendas_hubla'])} <span class="muted">({num(k['vendas_meta'])})</span></td>
          <td class="r c-{cls_cpa(k['cpa_meta'])}">{brl(k['cpa_meta'])}</td>
          <td class="r c-{cls_mql(k['mql_pct'])}">{pct(k['mql_pct'],0)}</td>
          <td class="r">{str(k['roas']).replace('.',',')}x</td>
          <td>{mixbar}</td></tr>''')
    # funis mes
    frows = []
    for f in ov['funis']:
        color = FUN_COLOR[f['funnel']]
        frows.append(f'''<tr>
          <td class="l"><span class="dot" style="background:{color}"></span>{esc(f['label'])}</td>
          <td class="r">{brl(f['spend'])}</td>
          <td class="r">{pct(f['spend_share'],0)}</td>
          <td class="r">{num(f['vendas'])} <span class="muted">({num(f['vendas_meta'])})</span></td>
          <td class="r c-{cls_cpa(f['cpa_meta'])}">{brl(f['cpa_meta'])}</td>
          <td class="r c-{cls_mql(f['mql_pct'])}">{pct(f['mql_pct'],0)} <span class="muted">{f['mql']}/{f['matched']}</span></td>
          <td class="r">{brl(f['cpmql']) if f['mql'] else '-'}</td></tr>''')
    return f'''
    <section class="panel" id="panel-overview">
      <h2>Visao geral — {esc(month_label)}</h2>
      {kpi_row(tiles)}

      <h3>Pontos de otimizacao</h3>
      <div class="acards">{''.join(acards)}</div>

      <h3>Comparativo entre turmas</h3>
      <div class="tblwrap"><table class="cmp">
        <thead><tr><th class="l">Turma</th><th class="r">Investido</th><th class="r">Vendas (meta)</th>
          <th class="r">CPA meta</th><th class="r">MQL rate</th><th class="r">ROAS</th>
          <th>Mix de funil (spend)</th></tr></thead>
        <tbody>{''.join(trows)}</tbody></table></div>
      <div class="legend">
        <span><i style="background:{FUN_COLOR['prosp']}"></i>Prospeccao</span>
        <span><i style="background:{FUN_COLOR['quiz']}"></i>Quiz</span>
        <span><i style="background:{FUN_COLOR['rmkt']}"></i>RMKT</span></div>

      <h3>Blocos no mes <span class="hnote">quem gera demanda (frio) vs quem colhe (quente)</span></h3>
      <div class="tblwrap"><table class="cmp">
        <thead><tr><th class="l">Bloco</th><th class="r">Investido</th><th class="r">% spend</th>
          <th class="r">Vendas (meta)</th><th class="r">CPA meta</th><th class="r">MQL rate</th>
          <th class="r">Custo / MQL</th></tr></thead>
        <tbody>{''.join(frows)}</tbody></table></div>
    </section>'''


def build():
    d = json.load(open(DATA, encoding='utf-8'))
    thumbs = d.get('thumbs_b64', {})
    status = d.get('ad_status', {})
    turmas = d['turmas']

    # tabs
    tabs = ['<button class="tab active" data-t="overview">Visao Geral</button>']
    for i, t in enumerate(turmas):
        lab = t['short'] + (' *' if t['is_current'] else '')
        tabs.append(f'<button class="tab" data-t="turma-{i}">{esc(lab)}</button>')

    panels = [overview_panel(d['overview'], d['month_label'])]
    for i, t in enumerate(turmas):
        panels.append(turma_panel(t, thumbs, status, i))

    css = CSS
    js = JS
    htmlout = f'''<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DP100K-Fp02 — Report {esc(d['month_label'])}</title>
<style>{css}</style></head><body>
<header>
  <div class="hwrap">
    <div><div class="brand">DP100K-Fp02 · Desafio Palestrante 100K</div>
      <div class="sub">Report de otimizacao — {esc(d['month_label'])} · turma aberta: {esc(d.get('cur_label',''))}</div></div>
    <div class="upd">Atualizado {esc(d['updated_at'])}<br><span class="muted">venda = Hubla · MQL = renda &ge; R$ 10.001 · spend por bloco/ad = rateio do investido canonico pela participacao Meta</span></div>
  </div>
  <nav class="tabs">{''.join(tabs)}</nav>
</header>
<main>{''.join(panels)}</main>
<footer>DP100K-Fp02 · fonte: Investimento por Hora (spend/funil, hora-exato) + Hubla (venda) + Pesquisa (renda) · Meta Ads act {esc(d['account'])} · Rio de Janeiro / BR</footer>
<script>{js}</script>
</body></html>'''
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(htmlout)
    print(f"[build] {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")


CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1420;--panel:#161c2b;--card:#1b2334;--line:#28324a;--tx:#e8edf7;--mut:#8b97b0;
--g:#22c55e;--a:#f59e0b;--r:#ef4444;--acc:#3B82F6}
body{background:var(--bg);color:var(--tx);font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
header{position:sticky;top:0;z-index:10;background:var(--bg);border-bottom:1px solid var(--line)}
.hwrap{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:16px 22px 10px;flex-wrap:wrap;max-width:1180px;margin:0 auto}
.brand{font-size:17px;font-weight:800;letter-spacing:.2px}
.sub{color:var(--mut);font-size:13px;margin-top:2px}
.upd{color:var(--tx);font-size:12px;text-align:right;max-width:420px}
.muted{color:var(--mut);font-weight:400}
.tabs{display:flex;gap:6px;padding:0 22px;max-width:1180px;margin:0 auto;overflow-x:auto}
.tab{background:transparent;color:var(--mut);border:none;border-bottom:2px solid transparent;
padding:10px 14px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap}
.tab:hover{color:var(--tx)}
.tab.active{color:var(--tx);border-bottom-color:var(--acc)}
main{max-width:1180px;margin:0 auto;padding:22px}
.panel h2{font-size:20px;margin-bottom:14px}
.panel h3{font-size:14px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut);
margin:26px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px}
.hnote{text-transform:none;letter-spacing:0;font-size:12px;color:var(--mut);font-weight:400}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile .tl{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.tile .tv{font-size:22px;font-weight:800;margin:3px 0}
.tile .ts{color:var(--mut);font-size:11px}
.tile.c-g .tv{color:var(--g)} .tile.c-a .tv{color:var(--a)} .tile.c-r .tv{color:var(--r)}
.badge-live{background:var(--r);color:#fff;font-size:11px;padding:2px 8px;border-radius:20px;vertical-align:middle;font-weight:600}
/* funil steps */
.funnel-steps{display:flex;align-items:stretch;gap:0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;overflow-x:auto}
.fstep{flex:1;min-width:96px;text-align:center;padding:0 8px}
.fstep-v{font-size:20px;font-weight:800}
.fstep-l{color:var(--mut);font-size:12px}
.fstep-c{margin-top:6px;font-size:11px;color:var(--acc);font-weight:600}
.fsep{display:flex;align-items:center;color:var(--line);font-size:22px}
/* funnel cards */
.fcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.fcard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.fhead{display:flex;justify-content:space-between;align-items:baseline}
.fname{font-size:16px;font-weight:800}
.fshare{color:var(--mut);font-size:12px}
.fdesc{color:var(--mut);font-size:12px;margin:4px 0 8px}
.fbar{height:6px;background:var(--line);border-radius:6px;overflow:hidden;margin-bottom:10px}
.fbar span{display:block;height:100%}
.fmini{width:100%;border-collapse:collapse}
.fmini td{padding:5px 0;border-top:1px solid var(--line);font-size:13px}
.fmini td:last-child{text-align:right;font-weight:700}
/* tables */
.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;background:var(--card)}
th,td{padding:9px 12px;font-size:13px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.5px;background:var(--panel);position:sticky;top:0}
td.r,th.r{text-align:right}
td.l,th.l{text-align:left}
tr.cur{background:#1d2740}
.c-g{color:var(--g)} .c-a{color:var(--a)} .c-r{color:var(--r)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:middle}
.mixbar{display:flex;height:12px;width:150px;border-radius:6px;overflow:hidden;background:var(--line)}
.mixbar span{display:block;height:100%}
.legend{display:flex;gap:16px;margin-top:8px;color:var(--mut);font-size:12px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:middle}
/* acoes */
.acards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.acard{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--mut);border-radius:8px;padding:13px 15px}
.acard.conf-alta{border-left-color:var(--r)}
.acard.conf-media{border-left-color:var(--a)}
.acard.conf-baixa{border-left-color:var(--mut)}
.atop{display:flex;gap:8px;align-items:center;margin-bottom:5px}
.atag{background:var(--panel);color:var(--tx);font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px;letter-spacing:.5px}
.aconf{font-size:10px;color:var(--mut);font-weight:700}
.adono{margin-left:auto;font-size:11px;color:var(--mut)}
.atitle{font-weight:700;font-size:14px;margin-bottom:4px}
.atext{color:var(--mut);font-size:13px}
/* ads table */
.afilter{display:flex;gap:6px;align-items:center;margin-bottom:8px;color:var(--mut);font-size:12px;flex-wrap:wrap}
.fbtn{background:var(--card);color:var(--mut);border:1px solid var(--line);border-radius:20px;padding:4px 12px;font-size:12px;cursor:pointer}
.fbtn.active{background:var(--acc);color:#fff;border-color:var(--acc)}
.ads .adcell{display:flex;gap:10px;align-items:center;min-width:230px}
.thumb{width:46px;height:46px;border-radius:6px;object-fit:cover;flex-shrink:0;background:var(--line)}
.thumb.noimg{border:1px dashed var(--line)}
.adcode{font-weight:700;font-size:13px}
.fchip{font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px;margin-left:6px}
.stdot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-left:6px}
.stdot.on{background:var(--g)} .stdot.off{background:var(--mut)}
.adname{color:var(--mut);font-size:11px;margin-top:2px}
footer{max-width:1180px;margin:0 auto;padding:20px 22px 40px;color:var(--mut);font-size:12px;border-top:1px solid var(--line)}
@media(max-width:640px){.hwrap{flex-direction:column}.upd{text-align:left;max-width:100%}}
'''

JS = '''
document.querySelectorAll('.tab').forEach(function(b){
  b.onclick=function(){
    document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active')});
    b.classList.add('active');
    var t=b.dataset.t;
    document.getElementById('panel-overview').style.display=(t==='overview')?'block':'none';
    document.querySelectorAll('[id^=turma-]').forEach(function(p){
      p.style.display=(p.id===t)?'block':'none';});
    window.scrollTo(0,0);
  };
});
document.querySelectorAll('.afilter').forEach(function(bar){
  var tbl=bar.parentElement.querySelector('table.ads');
  bar.querySelectorAll('.fbtn').forEach(function(btn){
    btn.onclick=function(){
      bar.querySelectorAll('.fbtn').forEach(function(x){x.classList.remove('active')});
      btn.classList.add('active');
      var f=btn.dataset.f;
      tbl.querySelectorAll('tbody tr').forEach(function(tr){
        tr.style.display=(f==='all'||tr.dataset.funnel===f)?'':'none';});
    };
  });
});
'''


if __name__ == '__main__':
    build()
