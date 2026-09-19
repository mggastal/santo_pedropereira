#!/usr/bin/env python3
"""
Dashboard Político — Alcance & Engajamento (+ Funil de Vídeo)
Gera index.html standalone a partir do Google Sheets (aba meta-ads).
"""

import pandas as pd, json, re, hashlib, requests
from datetime import date
from pathlib import Path

# ══════════════════════════════════════════════════════
# CONFIG DO CLIENTE — edite apenas esta seção
# ══════════════════════════════════════════════════════
SHEET_ID       = "1J56B-E0ZQArppohGl8D0OYjxpTliNqSkPx4vBhc3V68"
TEMPLATE_FILE  = "dashboard.html"
OUTPUT_FILE    = "index.html"

NOME_CLIENTE   = "Pedro Pereira"
LOGO_LETRA     = "P"
LOGO_URL       = "logo.png"  # arquivo de imagem (coloque junto do index.html); deixe "" para usar só a letra
COR_ACENTO     = "#0064e0"

AGENCY_NOME      = ""  # preencha se quiser mostrar o nome em texto quando não houver logo
AGENCY_LOGO_URL  = "logo.png"  # logo da agência no rodapé; deixe "" para mostrar só o nome

MOEDA          = "BRL"     # BRL | USD | EUR | ARS
_MOEDA_MAP = {
    "BRL": {"simbolo": "R$", "locale": "pt-BR"},
    "USD": {"simbolo": "$",  "locale": "en-US"},
    "EUR": {"simbolo": "€",  "locale": "de-DE"},
    "ARS": {"simbolo": "$",  "locale": "es-AR"},
}
_moeda_cfg    = _MOEDA_MAP.get(MOEDA, _MOEDA_MAP["BRL"])
MOEDA_SIMBOLO = _moeda_cfg["simbolo"]

# ══════════════════════════════════════════════════════
def sheet_url(t): return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={t}"
URL_META = sheet_url("meta-ads")
URL_BD_AGE_GENDER = sheet_url("breakdown-gender-age")
URL_BD_PLATFORM = sheet_url("breakdown-platform")

def to_num(s):
    if pd.api.types.is_numeric_dtype(s): return s.fillna(0)
    clean = s.astype(str).str.strip().str.replace("R$", "", regex=False).str.strip()
    # Decimal BR: "215,12" -> remove "." (milhar) e troca "," por "." (215.12)
    has_comma_decimal = clean.str.contains(r"\d,\d", regex=True)
    clean = clean.where(~has_comma_decimal, clean.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    # Inteiro com separador de milhar em "." e SEM vírgula: "1.593" / "16.565" / "136.208" -> "1593" / "16565" / "136208"
    # (sem isso, "1.593" era lido como o número 1,593 — praticamente zero. Foi o bug do funil de vídeo.)
    only_thousands = clean.str.match(r"^-?\d{1,3}(\.\d{3})+$", na=False) & ~has_comma_decimal
    clean = clean.where(~only_thousands, clean.str.replace(".", "", regex=False))
    return pd.to_numeric(clean, errors="coerce").fillna(0)

def download_thumb(url, d):
    if not url or str(url) == "nan": return ""
    try:
        ext = ".png" if ".png" in url.lower() else ".jpg"
        fname = hashlib.md5(url.encode()).hexdigest()[:16] + ext
        fp = d / fname
        if not fp.exists():
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200: fp.write_bytes(r.content)
            else: return ""
        return "imgs/" + fname
    except Exception:
        return ""

VIDEO_COLS = {
    "Video 15 Sec Watched Actions": "v15",
    "Video 25 Percent Watched Actions": "v25",
    "Video 50 Percent Watched Actions": "v50",
    "Video 75 Percent Watched Actions": "v75",
    "Video 95 Percent Watched Actions": "v95",
    "Video 100 Percent Watched Actions": "v100",
    "Video Thruplay Watched Actions": "thruplay",
}

import re as _re

def _sum_dupe_cols(raw, label):
    """Soma TODAS as colunas com esse nome. Se a planilha tiver a mesma coluna
    duplicada (ex: 'Video 25 Percent Watched Actions' 2x), o pandas já
    renomeia a segunda para 'Video 25 Percent Watched Actions.1' ao ler o CSV
    — sem tratar isso, um rename() simples ignora essa segunda coluna e
    subconta o total. Aqui pegamos o nome exato e também as variantes .1/.2/…"""
    pattern = _re.compile(rf"^{_re.escape(label)}(\.\d+)?$")
    cols = [c for c in raw.columns if pattern.match(c)]
    if len(cols) > 1:
        print(f"  ⚠ AVISO: coluna '{label}' aparece {len(cols)}x na planilha — somando todas para não subcontar.")
    if not cols:
        return pd.Series(0, index=raw.index)
    return sum(to_num(raw[c]) for c in cols)

def load_meta():
    print("  Lendo meta-ads...")
    raw = pd.read_csv(URL_META)

    df = pd.DataFrame(index=raw.index)
    df["date"] = pd.to_datetime(raw["Date"], errors="coerce") if "Date" in raw.columns else pd.NaT
    df["campaign"] = raw["Campaign Name"] if "Campaign Name" in raw.columns else ""
    df["adset"] = raw["Adset Name"] if "Adset Name" in raw.columns else ""
    df["ad"] = raw["Ad Name"] if "Ad Name" in raw.columns else ""
    df["thumb"] = raw["Thumbnail URL"] if "Thumbnail URL" in raw.columns else ""
    df["status"] = (raw["Status"] if "Status" in raw.columns else "").astype(str).str.strip().str.upper()

    field_map = {
        "spend": "Spend (Cost, Amount Spent)", "impressions": "Impressions",
        "reach": "Reach (Estimated)", "reactions": "Action Post Reactions",
        "shares": "Action Post Shares", "comments": "Action Post Comments",
        "saves": "Action Post Save (Onsite Conversion)", "profile_visits": "Instagram Profile Visits",
        "clicks": "Clicks",
    }
    field_map.update({v: k for k, v in VIDEO_COLS.items()})
    for field, label in field_map.items():
        df[field] = _sum_dupe_cols(raw, label)

    df["engajamento"] = df["reactions"] + df["shares"] + df["comments"] + df["saves"]
    df = df.dropna(subset=["date"])
    print(f"     {len(df)} linhas | {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"     Alcance total: {df['reach'].sum():.0f} | Engajamento total: {df['engajamento'].sum():.0f}")
    print(f"     Vídeo — 15s: {df['v15'].sum():.0f} | 25%: {df['v25'].sum():.0f} | 50%: {df['v50'].sum():.0f} | "
          f"75%: {df['v75'].sum():.0f} | 95%: {df['v95'].sum():.0f} | 100%: {df['v100'].sum():.0f}")
    return df

def calc_kpis(p):
    sp = float(p["spend"].sum()); imp = float(p["impressions"].sum())
    rch = float(p["reach"].sum())
    reac = float(p["reactions"].sum()); sha = float(p["shares"].sum())
    com = float(p["comments"].sum()); sav = float(p["saves"].sum())
    pv = float(p["profile_visits"].sum())
    eng = reac + sha + com + sav
    return {
        "spend": round(sp, 2), "impressions": int(imp), "reach": int(rch),
        "reactions": int(reac), "shares": int(sha), "comments": int(com), "saves": int(sav),
        "profile_visits": int(pv),
        "engajamento": int(eng),
        "cpm": round(sp / imp * 1000, 2) if imp > 0 else None,
        "cpe": round(sp / eng, 2) if eng > 0 else None,
        "taxa_eng": round(eng / rch * 100, 2) if rch > 0 else None,
        "video": {
            "v15": int(p["v15"].sum()), "v25": int(p["v25"].sum()), "v50": int(p["v50"].sum()),
            "v75": int(p["v75"].sum()), "v95": int(p["v95"].sum()), "v100": int(p["v100"].sum()),
            "thruplay": int(p["thruplay"].sum()),
            "video_impressions": video_impressions(p),
        },
    }

def build_daily(p):
    agg = p.groupby("date").agg(
        spend=("spend", "sum"), impressions=("impressions", "sum"), reach=("reach", "sum"),
        reactions=("reactions", "sum"), shares=("shares", "sum"),
        comments=("comments", "sum"), saves=("saves", "sum"), engajamento=("engajamento", "sum"),
    ).reset_index().sort_values("date")
    out = {k: [] for k in ["days", "spend", "impressions", "reach", "engajamento",
                            "reactions", "shares", "comments", "saves", "cpm", "cpe"]}
    for _, r in agg.iterrows():
        sp = float(r["spend"]); imp = float(r["impressions"]); eg = float(r["engajamento"])
        out["days"].append(r["date"].strftime("%d/%m/%Y"))
        out["spend"].append(round(sp, 2))
        out["impressions"].append(int(imp))
        out["reach"].append(int(r["reach"]))
        out["engajamento"].append(int(eg))
        out["reactions"].append(int(r["reactions"]))
        out["shares"].append(int(r["shares"]))
        out["comments"].append(int(r["comments"]))
        out["saves"].append(int(r["saves"]))
        out["cpm"].append(round(sp / imp * 1000, 2) if imp > 0 else None)
        out["cpe"].append(round(sp / eg, 2) if eg > 0 else None)
    return out

def video_impressions(p):
    """Soma impressões somente dos anúncios que são vídeo (tiveram ao menos
    1 VV15s no recorte). Anúncios de imagem (sem nenhum VV15s) são excluídos
    da base do funil, senão o % fica artificialmente baixo."""
    g = p.groupby(["campaign", "adset", "ad"]).agg(v15=("v15", "sum"), imp=("impressions", "sum")).reset_index()
    return int(g[g["v15"] > 0]["imp"].sum())

def load_breakdown(url, dim_cols):
    try:
        df = pd.read_csv(url)
        rename = {
            "Date": "date", "Spend (Cost, Amount Spent)": "spend",
            "Reach (Estimated)": "reach", "Impressions": "impressions",
            "Action Post Engagement": "engagement",
        }
        rename.update(dim_cols)
        df = df.rename(columns=rename)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for c in ["spend", "reach", "impressions", "engagement"]:
            if c in df.columns: df[c] = to_num(df[c])
            else: df[c] = 0
        df = df.dropna(subset=["date"])
        return df
    except Exception as e:
        print(f"  Aviso breakdown ({url}): {e}")
        return pd.DataFrame()

def build_bd_age_gender():
    print("  Lendo breakdown-gender-age...")
    df = load_breakdown(URL_BD_AGE_GENDER, {"Age (Breakdown)": "age", "Gender (Breakdown)": "gender"})
    if df.empty: return []
    rows = []
    for _, r in df.iterrows():
        rows.append({"d": r["date"].strftime("%d/%m/%Y"), "age": str(r.get("age", "")), "gen": str(r.get("gender", "")),
                     "sp": round(float(r["spend"]), 2), "imp": int(r["impressions"]), "rch": int(r["reach"]),
                     "eng": int(r["engagement"])})
    return rows

def build_bd_platform():
    print("  Lendo breakdown-platform...")
    df = load_breakdown(URL_BD_PLATFORM, {"Platform Position (Breakdown)": "platform"})
    if df.empty: return []
    rows = []
    for _, r in df.iterrows():
        rows.append({"d": r["date"].strftime("%d/%m/%Y"), "plat": str(r.get("platform", "")),
                     "sp": round(float(r["spend"]), 2), "imp": int(r["impressions"]), "rch": int(r["reach"]),
                     "eng": int(r["engagement"])})
    return rows


    hoje = pd.Timestamp(date.today())
    ranges = {"7": (hoje - pd.Timedelta(days=6), hoje), "14": (hoje - pd.Timedelta(days=13), hoje),
              "30": (hoje - pd.Timedelta(days=29), hoje), "all": (None, None)}
    out = {}
    for pname, (start, end) in ranges.items():
        p = df if start is None else df[(df["date"] >= start) & (df["date"] <= end)]
        out[pname] = calc_kpis(p)
    return out

def periods_kpis(df):
    hoje = pd.Timestamp(date.today())
    ranges = {"7": (hoje - pd.Timedelta(days=6), hoje), "14": (hoje - pd.Timedelta(days=13), hoje),
              "30": (hoje - pd.Timedelta(days=29), hoje), "all": (None, None)}
    out = {}
    for pname, (start, end) in ranges.items():
        p = df if start is None else df[(df["date"] >= start) & (df["date"] <= end)]
        out[pname] = calc_kpis(p)
    return out

def build_raw(df, img_dir):
    """Uma linha por (data, campanha, conjunto, anúncio) — usada para montar a
    lista de campanhas/conjuntos/criativos e o funil de vídeo no cliente (JS),
    respeitando o filtro de período escolhido pelo usuário."""
    df_thumb = df[df["thumb"].notna() & (df["thumb"].astype(str) != "nan")] if "thumb" in df.columns else pd.DataFrame()
    thumb_map = {}
    for _, r in df_thumb.iterrows():
        k = (str(r["ad"]), str(r["adset"]), str(r["campaign"]))
        if k not in thumb_map:
            thumb_map[k] = download_thumb(str(r["thumb"]), img_dir)
    agg = df.groupby(["date", "campaign", "adset", "ad"]).agg(
        spend=("spend", "sum"), impressions=("impressions", "sum"), reach=("reach", "sum"),
        reactions=("reactions", "sum"), shares=("shares", "sum"), comments=("comments", "sum"),
        saves=("saves", "sum"), clicks=("clicks", "sum"), profile_visits=("profile_visits", "sum"),
        v15=("v15", "sum"), v25=("v25", "sum"), v50=("v50", "sum"),
        v75=("v75", "sum"), v95=("v95", "sum"), v100=("v100", "sum"), thruplay=("thruplay", "sum"),
        status=("status", "last"),
    ).reset_index()
    rows = []
    for _, r in agg.iterrows():
        k = (str(r["ad"]), str(r["adset"]), str(r["campaign"]))
        rows.append({
            "d": r["date"].strftime("%d/%m/%Y"), "c": str(r["campaign"]), "a": str(r["adset"]),
            "ad": str(r["ad"]), "th": thumb_map.get(k, ""), "st": str(r["status"]),
            "sp": round(float(r["spend"]), 2), "imp": int(r["impressions"]), "rch": int(r["reach"]),
            "rc": int(r["reactions"]), "sh": int(r["shares"]), "cm": int(r["comments"]), "sv": int(r["saves"]),
            "pv": int(r["profile_visits"]),
            "cl": int(r["clicks"]),
            "v15": int(r["v15"]), "v25": int(r["v25"]), "v50": int(r["v50"]),
            "v75": int(r["v75"]), "v95": int(r["v95"]), "v100": int(r["v100"]), "tp": int(r["thruplay"]),
        })
    return rows

def replace_js_const(html, name, value):
    replacement = f"const {name} = {json.dumps(value, ensure_ascii=False)};"
    pattern_start = re.compile(rf"const {name}\s*=\s*")
    m = pattern_start.search(html)
    if not m:
        print(f"  AVISO: não encontrou const {name}")
        return html
    start = m.start(); val_start = m.end()
    i = val_start; depth = 0; in_str = False; str_char = None
    while i < len(html):
        ch = html[i]
        if in_str:
            if ch == '\\': i += 2; continue
            if ch == str_char: in_str = False
        else:
            if ch in ('"', "'", '`'): in_str = True; str_char = ch
            elif ch in ('{', '['): depth += 1
            elif ch in ('}', ']'): depth -= 1
            elif ch == ';' and depth == 0: break
        i += 1
    html = html[:start] + replacement + html[i+1:]
    return html

def main():
    print("=" * 60)
    print(f"Dashboard Político — {NOME_CLIENTE}")
    print("=" * 60)
    img_dir = Path("imgs"); img_dir.mkdir(exist_ok=True)

    df = load_meta()
    kpis_all = calc_kpis(df)
    kpis_periods = periods_kpis(df)
    daily = build_daily(df)
    raw = build_raw(df, img_dir)
    bd_age_gender = build_bd_age_gender()
    bd_platform = build_bd_platform()

    print("\n[HTML]")
    if not Path(TEMPLATE_FILE).exists():
        print(f"  ERRO: {TEMPLATE_FILE} não encontrado"); return

    html = Path(TEMPLATE_FILE).read_text(encoding="utf-8")
    html = replace_js_const(html, "KPIS_ALL",      kpis_all)
    html = replace_js_const(html, "KPIS_PERIODS",  kpis_periods)
    html = replace_js_const(html, "DAILY",         daily)
    html = replace_js_const(html, "RAW",           raw)
    html = replace_js_const(html, "BD_AGE_GENDER", bd_age_gender)
    html = replace_js_const(html, "BD_PLATFORM",   bd_platform)
    html = replace_js_const(html, "DATA_GERACAO",  date.today().strftime("%Y-%m-%d"))
    html = replace_js_const(html, "MOEDA_SIMBOLO", MOEDA_SIMBOLO)
    html = replace_js_const(html, "NOME_CLIENTE",  NOME_CLIENTE)
    html = replace_js_const(html, "LOGO_LETRA",    LOGO_LETRA)
    html = replace_js_const(html, "LOGO_URL",      LOGO_URL)
    html = replace_js_const(html, "AGENCY_NOME",     AGENCY_NOME)
    html = replace_js_const(html, "AGENCY_LOGO_URL", AGENCY_LOGO_URL)
    html = replace_js_const(html, "COR_ACENTO",    COR_ACENTO)

    Path(OUTPUT_FILE).write_text(html, encoding="utf-8")
    print(f"  ✓ {OUTPUT_FILE} ({len(html)//1024}KB)")
    print("=" * 60)

if __name__ == "__main__":
    main()
