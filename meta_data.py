"""Camada Meta Ads — puxa TUDO da turma atual (janela [since, until]).

camps, topline, ads (com status), breakdowns, fatigue, previews, copies,
thumbnails em base64 e serie diaria. So a turma atual paga esse custo.
"""
import sys
import base64
import io
import time
import urllib.request
from collections import defaultdict

import config as C
from gauth import init_meta


def _acts(d, kind):
    for a in d.get("actions", []) or []:
        if a.get("action_type") == kind:
            return float(a.get("value", 0))
    return 0.0


def _campaigns():
    from facebook_business.adobjects.adaccount import AdAccount
    acct = AdAccount(C.ACCOUNT)
    camp_list = list(acct.get_campaigns(
        params={"limit": 500, "effective_status": ["ACTIVE", "PAUSED", "ARCHIVED"]},
        fields=["id", "name", "status", "objective", "daily_budget", "lifetime_budget"]))
    camps = [c for c in camp_list
             if C.CAMP_MATCH in c.get('name', '') and C.CAMP_EXCLUDE not in c.get('name', '').upper()]
    print(f"[meta] campanhas {C.CAMP_MATCH}: {len(camps)}", file=sys.stderr)
    return camps


def pull(since, until, days):
    from facebook_business.adobjects.campaign import Campaign
    from facebook_business.adobjects.ad import Ad
    from facebook_business.adobjects.adcreative import AdCreative

    init_meta()
    TIME_RANGE = {"since": since, "until": until}
    CAMPS = _campaigns()
    CAMP_IDS = [c['id'] for c in CAMPS]
    QUIZ_IDS = {c['id'] for c in CAMPS if C.QUIZ_KEYWORD in c.get('name', '').upper()}

    # 1) campaign-level
    camps_out = []
    for c in CAMPS:
        cid, cname = c['id'], c.get('name', '')
        try:
            ins = Campaign(cid).get_insights(params={
                "time_range": TIME_RANGE, "level": "campaign",
                "fields": ["spend", "impressions", "clicks", "inline_link_clicks",
                           "actions", "reach", "frequency", "ctr", "cpm", "cpc"]})
            if not ins:
                camps_out.append({"id": cid, "name": cname, "spend": 0, "impr": 0, "clicks": 0,
                                  "link_clicks": 0, "lpv": 0, "ic": 0, "atc": 0, "purch": 0,
                                  "status": c.get('status'), "objective": c.get('objective')})
                continue
            for r in ins:
                d = dict(r)
                camps_out.append({
                    "id": cid, "name": cname, "status": c.get('status'), "objective": c.get('objective'),
                    "spend": float(d.get("spend", 0)), "impr": int(d.get("impressions", 0)),
                    "clicks": int(d.get("clicks", 0)), "link_clicks": int(d.get("inline_link_clicks", 0) or 0),
                    "reach": int(d.get("reach", 0) or 0), "freq": float(d.get("frequency", 0) or 0),
                    "lpv": _acts(d, "landing_page_view"), "ic": _acts(d, "initiate_checkout"),
                    "atc": _acts(d, "add_to_cart"), "purch": _acts(d, "purchase")})
        except Exception as e:
            print(f"[meta] ERR camp {cid}: {str(e)[:140]}", file=sys.stderr)
    camps_out.sort(key=lambda x: -x["spend"])

    # topline
    tl = dict(spend=0, impr=0, clicks=0, link_clicks=0, lpv=0, ic=0, atc=0, purch=0, reach=0)
    for r in camps_out:
        for k in tl:
            tl[k] += r.get(k, 0)
    tl["ctr"] = tl["clicks"] / tl["impr"] * 100 if tl["impr"] else 0
    tl["link_ctr"] = tl["link_clicks"] / tl["impr"] * 100 if tl["impr"] else 0
    tl["cpc"] = tl["spend"] / tl["clicks"] if tl["clicks"] else 0
    tl["cpm"] = tl["spend"] / tl["impr"] * 1000 if tl["impr"] else 0
    tl["cpa"] = tl["spend"] / tl["purch"] if tl["purch"] else 0
    tl["lpv_ic"] = tl["ic"] / tl["lpv"] * 100 if tl["lpv"] else 0
    tl["ic_v"] = tl["purch"] / tl["ic"] * 100 if tl["ic"] else 0

    # 2) ad-level
    ads_out = []
    for c in CAMPS:
        cid, cname = c['id'], c.get('name', '')
        try:
            ins = Campaign(cid).get_insights(params={
                "time_range": TIME_RANGE, "level": "ad",
                "fields": ["ad_id", "ad_name", "adset_id", "adset_name", "campaign_id", "campaign_name",
                           "spend", "impressions", "clicks", "inline_link_clicks", "inline_link_click_ctr",
                           "actions", "reach", "frequency", "ctr", "cpc"], "limit": 500})
            for r in ins:
                d = dict(r)
                ads_out.append({
                    "ad_id": d.get("ad_id"), "name": d.get("ad_name", ""),
                    "adset_id": d.get("adset_id"), "adset_name": d.get("adset_name", ""),
                    "campaign_id": d.get("campaign_id"), "campaign_name": d.get("campaign_name", ""),
                    "camp": cname, "spend": float(d.get("spend", 0)), "impr": int(d.get("impressions", 0)),
                    "clicks": int(d.get("clicks", 0)), "link_clicks": int(d.get("inline_link_clicks", 0) or 0),
                    "reach": int(d.get("reach", 0) or 0), "lpv": int(_acts(d, "landing_page_view")),
                    "ic": int(_acts(d, "initiate_checkout")), "atc": int(_acts(d, "add_to_cart")),
                    "purch": int(_acts(d, "purchase")), "ctr": float(d.get("ctr", 0) or 0),
                    "link_ctr": float(d.get("inline_link_click_ctr", 0) or 0),
                    "cpc": float(d.get("cpc", 0) or 0), "frequency": float(d.get("frequency", 0) or 0)})
        except Exception as e:
            print(f"[meta] ERR ads {cid}: {str(e)[:140]}", file=sys.stderr)

    print(f"[meta] enriquecendo status de {len(ads_out)} ads...", file=sys.stderr)
    for a in ads_out:
        try:
            info = Ad(a["ad_id"]).api_get(fields=["status", "effective_status"])
            a["status"] = info.get("status")
            a["effective_status"] = info.get("effective_status")
        except Exception:
            a["status"] = a["effective_status"] = "?"
    ads_out.sort(key=lambda x: -x["spend"])

    # 3) breakdowns
    BREAKDOWNS = {"placement": ["publisher_platform", "platform_position"],
                  "device": ["device_platform"], "age_gender": ["age", "gender"],
                  "region": ["region"]}
    results = {}
    for name, bds in BREAKDOWNS.items():
        agg = {}
        for cid in CAMP_IDS:
            try:
                for r in Campaign(cid).get_insights(params={
                        "time_range": TIME_RANGE, "level": "campaign", "breakdowns": bds,
                        "fields": ["spend", "impressions", "clicks", "inline_link_clicks", "actions"]}):
                    d = dict(r)
                    key = "|".join(str(d.get(b, "")) for b in bds)
                    if key not in agg:
                        agg[key] = {b: d.get(b, "") for b in bds}
                        agg[key].update({"spend": 0, "impr": 0, "clicks": 0, "link_clicks": 0, "v": 0, "ic": 0, "lpv": 0})
                    agg[key]["spend"] += float(d.get("spend", 0))
                    agg[key]["impr"] += int(d.get("impressions", 0))
                    agg[key]["clicks"] += int(d.get("clicks", 0))
                    agg[key]["link_clicks"] += int(d.get("inline_link_clicks", 0) or 0)
                    for a in d.get("actions", []) or []:
                        t, v = a.get("action_type"), float(a.get("value", 0))
                        if t == "purchase":
                            agg[key]["v"] += v
                        elif t == "initiate_checkout":
                            agg[key]["ic"] += v
                        elif t == "landing_page_view":
                            agg[key]["lpv"] += v
            except Exception as e:
                print(f"[meta] ERR bd {name} {cid}: {str(e)[:120]}", file=sys.stderr)
        results[name] = list(agg.values())

    # 4) fatigue (serie diaria por ad sobre a janela)
    ads_freq = {}
    for cid in CAMP_IDS:
        try:
            for r in Campaign(cid).get_insights(params={
                    "time_range": TIME_RANGE, "level": "ad",
                    "fields": ["ad_id", "ad_name", "frequency", "reach", "impressions", "spend"], "limit": 500}):
                d = dict(r)
                ads_freq[d.get("ad_id")] = {
                    "ad_name": d.get("ad_name"), "frequency": float(d.get("frequency", 0) or 0),
                    "reach": int(d.get("reach", 0) or 0), "impressions": int(d.get("impressions", 0) or 0),
                    "spend": float(d.get("spend", 0) or 0)}
        except Exception:
            pass
    daily_ad = {}
    for cid in CAMP_IDS:
        try:
            for r in Campaign(cid).get_insights(params={
                    "time_range": TIME_RANGE, "level": "ad", "time_increment": 1,
                    "fields": ["ad_id", "ad_name", "impressions", "clicks", "spend", "ctr", "cpm", "actions", "date_start"],
                    "limit": 1000}):
                d = dict(r)
                aid = d.get("ad_id")
                daily_ad.setdefault(aid, []).append({
                    "date": d.get("date_start"), "impr": int(d.get("impressions", 0)),
                    "clicks": int(d.get("clicks", 0)), "spend": float(d.get("spend", 0)),
                    "ctr": float(d.get("ctr", 0)), "cpm": float(d.get("cpm", 0)),
                    "purch": sum(float(a.get("value", 0)) for a in (d.get("actions", []) or []) if a.get("action_type") == "purchase")})
        except Exception:
            pass
    fatigue = {}
    for aid, dd in daily_ad.items():
        dd.sort(key=lambda x: x["date"])
        active = [x for x in dd if x["impr"] > 0]
        first_impr = next((i for i, x in enumerate(dd) if x["impr"] > 0), None)
        first_purch = next((i for i, x in enumerate(dd) if x["purch"] > 0), None)
        dtfp = (first_purch - first_impr) if (first_impr is not None and first_purch is not None) else None
        if len(active) >= 4:
            half = len(active) // 2
            sa = sum(x["impr"] for x in active[:half])
            sb = sum(x["impr"] for x in active[-half:])
            fctr = sum(x["ctr"] * x["impr"] for x in active[:half]) / sa if sa else 0
            lctr = sum(x["ctr"] * x["impr"] for x in active[-half:]) / sb if sb else 0
            ctr_change = (lctr - fctr) / fctr * 100 if fctr else 0
            fcpm = sum(x["cpm"] * x["impr"] for x in active[:half]) / sa if sa else 0
            lcpm = sum(x["cpm"] * x["impr"] for x in active[-half:]) / sb if sb else 0
            cpm_change = (lcpm - fcpm) / fcpm * 100 if fcpm else 0
        else:
            ctr_change = cpm_change = None
        fatigue[aid] = {"days_active": len(active), "days_to_first_purchase": dtfp,
                        "ctr_change_pct": ctr_change, "cpm_change_pct": cpm_change, "daily_series": dd}
    fat_out = {}
    for aid in set(list(ads_freq.keys()) + list(fatigue.keys())):
        fat_out[aid] = {**ads_freq.get(aid, {}), **fatigue.get(aid, {})}

    # 5) serie diaria overall + quiz (spend/lpv/ic/purch por dia)
    def blank():
        return {d: dict(spend=0, impr=0, clicks=0, lpv=0, ic=0, purch=0) for d in days}
    overall, quiz = blank(), blank()
    for c in CAMPS:
        cid = c['id']
        try:
            for r in Campaign(cid).get_insights(params={
                    "time_range": TIME_RANGE, "level": "campaign", "time_increment": 1,
                    "fields": ["spend", "impressions", "clicks", "inline_link_clicks", "actions", "date_start"],
                    "limit": 500}):
                d = dict(r)
                day = d.get("date_start")
                if day not in overall:
                    continue
                row = dict(spend=float(d.get("spend", 0)), impr=int(d.get("impressions", 0)),
                           clicks=int(d.get("clicks", 0)), lpv=int(_acts(d, "landing_page_view")),
                           ic=int(_acts(d, "initiate_checkout")), purch=int(_acts(d, "purchase")))
                for k in row:
                    overall[day][k] += row[k]
                    if cid in QUIZ_IDS:
                        quiz[day][k] += row[k]
        except Exception:
            pass

    # 6) previews + copies + thumbs (so ads com spend)
    active_ads = [a for a in ads_out if a.get("spend", 0) > 0]
    previews, copies, thumb_urls = {}, {}, {}
    print(f"[meta] previews/copies/thumbs de {len(active_ads)} ads com spend...", file=sys.stderr)
    for a in active_ads:
        aid = a['ad_id']
        # preview
        try:
            ad = Ad(aid)
            prev = list(ad.get_previews(params={"ad_format": "INSTAGRAM_STORY"}))
            if not prev:
                prev = list(ad.get_previews(params={"ad_format": "MOBILE_FEED_STANDARD"}))
            previews[aid] = prev[0].get('body', '') if prev else ''
        except Exception:
            previews[aid] = ''
        # copy + thumb (mesma leitura de creative)
        try:
            ad_obj = Ad(aid).api_get(fields=["creative"])
            cr_id = ad_obj.get('creative', {}).get('id') if ad_obj.get('creative') else None
            if cr_id:
                cr = AdCreative(cr_id).api_get(
                    fields=["object_story_spec", "asset_feed_spec", "body", "title", "link_url", "thumbnail_url", "image_url"],
                    params={"thumbnail_width": 640, "thumbnail_height": 640})
                d = dict(cr)
                message = headline = description = ""
                oss = d.get('object_story_spec') or {}
                if 'link_data' in oss:
                    ld = oss['link_data']
                    message = ld.get('message', '') or message
                    headline = ld.get('name', '') or headline
                    description = ld.get('description', '') or description
                if 'video_data' in oss:
                    vd = oss['video_data']
                    message = vd.get('message', '') or message
                    headline = vd.get('title', '') or headline
                    description = vd.get('description', '') or description
                afs = d.get('asset_feed_spec') or {}
                if afs:
                    if afs.get('bodies') and not message:
                        message = afs['bodies'][0].get('text', '')
                    if afs.get('titles') and not headline:
                        headline = afs['titles'][0].get('text', '')
                    if afs.get('descriptions') and not description:
                        description = afs['descriptions'][0].get('text', '')
                if not message:
                    message = d.get('body', '') or ''
                if not headline:
                    headline = d.get('title', '') or ''
                copies[aid] = {"message": message, "headline": headline, "description": description}
                thumb_urls[aid] = d.get('image_url') or d.get('thumbnail_url') or ''
            else:
                copies[aid] = {"message": "", "headline": "", "description": ""}
                thumb_urls[aid] = ''
        except Exception as e:
            copies[aid] = {"message": "", "headline": "", "description": ""}
            thumb_urls[aid] = ''
        time.sleep(0.1)

    thumbs_b64 = _embed_thumbs(thumb_urls)

    return {
        "camps": camps_out, "topline": tl, "ads": ads_out,
        "breakdowns": results, "fatigue": fat_out,
        "daily": {"window": TIME_RANGE, "days": days, "overall": overall, "quiz": quiz,
                  "quiz_ids": list(QUIZ_IDS)},
        "previews": previews, "copies": copies, "thumbs_b64": thumbs_b64,
    }


def _embed_thumbs(thumb_urls):
    """Baixa thumbs do CDN, redimensiona (max 520px) e devolve data-URIs base64."""
    try:
        from PIL import Image
    except Exception:
        print("[meta] PIL indisponivel — thumbs sem embed", file=sys.stderr)
        return {}
    out = {}
    ok = 0
    tot = 0
    for aid, url in thumb_urls.items():
        if not url:
            out[aid] = ''
            continue
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            raw = urllib.request.urlopen(req, timeout=30).read()
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            w, h = im.size
            if max(w, h) > 520:
                sc = 520 / max(w, h)
                im = im.resize((int(w * sc), int(h * sc)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=82, optimize=True)
            b = buf.getvalue()
            tot += len(b)
            out[aid] = 'data:image/jpeg;base64,' + base64.b64encode(b).decode()
            ok += 1
        except Exception as e:
            out[aid] = ''
    print(f"[meta] thumbs embutidas: {ok}/{len(thumb_urls)} (~{tot/1024/1024:.1f} MB)", file=sys.stderr)
    return out
