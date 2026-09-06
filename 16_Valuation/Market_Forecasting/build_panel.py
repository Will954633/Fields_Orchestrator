#!/usr/bin/env python3
import io, json, sys, time, urllib.request, urllib.error
import pandas as pd

BASE = "https://data.api.abs.gov.au/rest/data"
OUT = __import__("os").path.dirname(__import__("os").path.abspath(__file__))

CITIES = [
    ("Sydney","NSW","1","1GSYD"),
    ("Melbourne","VIC","2","2GMEL"),
    ("Brisbane","QLD","3","3GBRI"),
    ("Adelaide","SA","4","4GADE"),
    ("Perth","WA","5","5GPER"),
    ("Hobart","TAS","6","6GHOB"),
    ("Darwin","NT","7","7GDAR"),
    ("Canberra","ACT","8","8ACTE"),
]
STATE_BY_CODE = {c[2]: c[1] for c in CITIES}   # numeric state code -> abbrev
RPPI_REGION_STATE = {c[3]: c[1] for c in CITIES}

def fetch_csv(dataflow, key, start):
    url = f"{BASE}/{dataflow}/{key}?startPeriod={start}&format=csv"
    req = urllib.request.Request(url, headers={"accept":"text/csv","User-Agent":"fields-abs/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode("utf-8")
            df = pd.read_csv(io.StringIO(raw), dtype=str)
            return df, url
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8","ignore")[:300]
            if attempt == 2:
                raise RuntimeError(f"HTTP {e.code} for {url}\n{body}")
            time.sleep(3)
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(3)

def q_from_month(ym):
    # ym like '2003-01'
    y, m = ym.split("-")
    q = (int(m)-1)//3 + 1
    return f"{y}-Q{q}"

meta = {}

# ---------------- 1. RPPI (quarterly, index, established houses) ----------------
rppi_regions = "+".join(c[3] for c in CITIES)
rkey = f"1.2.{rppi_regions}.Q"          # MEASURE=1 index . PROPERTY_TYPE=2 established houses . REGION . FREQ=Q
df, url = fetch_csv("RPPI", rkey, "2003-Q1")
# find columns
def col(df, *names):
    for n in names:
        if n in df.columns: return n
    raise KeyError(f"{names} not in {list(df.columns)}")
rc = col(df,"REGION"); tc = col(df,"TIME_PERIOD"); vc = col(df,"OBS_VALUE")
df["city"] = df[rc].map(lambda x: next((c[0] for c in CITIES if c[3]==x), None))
df = df[df["city"].notna()].copy()
df["quarter"] = df[tc]
df["price_index"] = pd.to_numeric(df[vc], errors="coerce")
rppi = df[["city","quarter","price_index"]].dropna(subset=["price_index"])
meta["RPPI"] = {"dataflow":"RPPI","url":url,"key":rkey,
    "codes":{"MEASURE":"1 (Index Numbers)","PROPERTY_TYPE":"2 (Established houses)",
             "REGION":"8 capital-city GCCSA codes","FREQ":"Q"},
    "min":rppi["quarter"].min(),"max":rppi["quarter"].max(),
    "rows":int(len(rppi)),"nonnull":int(rppi["price_index"].notna().sum())}
print("RPPI rows", len(rppi), rppi["quarter"].min(), rppi["quarter"].max())

# ---------------- 2. LEND_HOUSING (quarterly value of new commitments, state) ----------------
lend_states = "+".join(c[2] for c in CITIES)
# MEASURE.DATA_ITEM.LOAN_TYPE.LOAN_PURPOSE.LENDER_TYPE.HOUSING_PURPOSE.TSEST.REGION.FREQ
# NEWCOMMITS value is published quarterly (FREQ=Q) in this dataflow.
# State-level data has no HOUSING_PURPOSE=TOT, so sum owner-occupier (DV5167) + investor (DV5168).
lkey = f"FIN_VAL.NEWCOMMITS.DV8368.TOTDWELL.TOT.DV5167+DV5168.20.{lend_states}.Q"
df, url = fetch_csv("LEND_HOUSING", lkey, "2003-Q1")
rc=col(df,"REGION"); tc=col(df,"TIME_PERIOD"); vc=col(df,"OBS_VALUE")
df = df[df[rc].isin(STATE_BY_CODE)].copy()
df["state"]=df[rc].map(STATE_BY_CODE)
df["quarter"]=df[tc]
df["val"]=pd.to_numeric(df[vc],errors="coerce")
# sum owner-occ + investor per state/quarter
lend = df.groupby(["state","quarter"],as_index=False)["val"].sum().rename(columns={"val":"lending"})
meta["LEND_HOUSING"]={"dataflow":"LEND_HOUSING","url":url,"key":lkey,
    "codes":{"MEASURE":"FIN_VAL (Value)","DATA_ITEM":"NEWCOMMITS (New loan commitments)",
             "LOAN_TYPE":"DV8368 (Total fixed term loans and revolving credit)",
             "LOAN_PURPOSE":"TOTDWELL (Total dwellings excl refinancing)",
             "LENDER_TYPE":"TOT","HOUSING_PURPOSE":"DV5167+DV5168 (owner-occupier + investor, summed)",
             "TSEST":"20 (Seas Adj)","REGION":"states 1-8","FREQ":"Q (natively quarterly)"},
    "min":lend["quarter"].min(),"max":lend["quarter"].max(),
    "rows":int(len(lend)),"nonnull":int(lend["lending"].notna().sum())}
print("LEND rows", len(lend), lend["quarter"].min(), lend["quarter"].max())

# ---------------- 3. RT retail turnover (monthly, current prices, total, state) ----------------
rt_states="+".join(c[2] for c in CITIES)
tkey=f"M1.20.20.{rt_states}.M"   # MEASURE=M1 current prices . INDUSTRY=20 total . TSEST=20 SA . REGION . FREQ=M
df,url=fetch_csv("RT",tkey,"2002-01")
rc=col(df,"REGION"); tc=col(df,"TIME_PERIOD"); vc=col(df,"OBS_VALUE")
df=df[df[rc].isin(STATE_BY_CODE)].copy()
df["state"]=df[rc].map(STATE_BY_CODE)
df["quarter"]=df[tc].map(q_from_month)
df["val"]=pd.to_numeric(df[vc],errors="coerce")
retail=df.groupby(["state","quarter"],as_index=False)["val"].sum().rename(columns={"val":"retail"})
meta["RT"]={"dataflow":"RT","url":url,"key":tkey,
    "codes":{"MEASURE":"M1 (Current Prices)","INDUSTRY":"20 (Total)","TSEST":"20 (Seas Adj)",
             "REGION":"states 1-8","FREQ":"M -> summed to quarter"},
    "min":retail["quarter"].min(),"max":retail["quarter"].max(),
    "rows":int(len(retail)),"nonnull":int(retail["retail"].notna().sum())}
print("RETAIL rows", len(retail), retail["quarter"].min(), retail["quarter"].max())

# ---------------- 4. LF unemployment rate (monthly, state, quarter avg) ----------------
lf_states="+".join(c[2] for c in CITIES)
# TSEST=10 (Original) — ACT & NT have no seasonally-adjusted labour-force series, so Original is
# used uniformly across all 8 states for a consistent methodology; quarter-averaging smooths seasonality.
ukey=f"M13.3.1599.10.{lf_states}.M"  # MEASURE=M13 unemp rate . SEX=3 persons . AGE=1599 total . TSEST=10 Orig . REGION . FREQ=M
df,url=fetch_csv("LF",ukey,"2002-01")
rc=col(df,"REGION"); tc=col(df,"TIME_PERIOD"); vc=col(df,"OBS_VALUE")
df=df[df[rc].isin(STATE_BY_CODE)].copy()
df["state"]=df[rc].map(STATE_BY_CODE)
df["quarter"]=df[tc].map(q_from_month)
df["val"]=pd.to_numeric(df[vc],errors="coerce")
unemp=df.groupby(["state","quarter"],as_index=False)["val"].mean().rename(columns={"val":"unemployment"})
meta["LF"]={"dataflow":"LF","url":url,"key":ukey,
    "codes":{"MEASURE":"M13 (Unemployment rate)","SEX":"3 (Persons)","AGE":"1599 (Total)",
             "TSEST":"10 (Original — ACT/NT lack a seas-adj series; Original used for all 8 for consistency)",
             "REGION":"states 1-8","FREQ":"M -> quarter average"},
    "min":unemp["quarter"].min(),"max":unemp["quarter"].max(),
    "rows":int(len(unemp)),"nonnull":int(unemp["unemployment"].notna().sum())}
print("UNEMP rows", len(unemp), unemp["quarter"].min(), unemp["quarter"].max())

# ---------------- 5. CPI_Q national All groups (quarterly) ----------------
# INDEX=999901 = "All groups CPI, seasonally adjusted" (the codelist's 10001 does not exist in CPI_Q data;
# region 50 = weighted avg of 8 capital cities carries only the SA all-groups series).
ckey="1.999901.20.50.Q"  # MEASURE=1 index . INDEX=999901 all-groups SA . TSEST=20 SA . REGION=50 8-cap avg . FREQ=Q
df,url=fetch_csv("CPI_Q",ckey,"2003-Q1")
tc=col(df,"TIME_PERIOD"); vc=col(df,"OBS_VALUE")
df["quarter"]=df[tc]
df["cpi"]=pd.to_numeric(df[vc],errors="coerce")
cpi=df[["quarter","cpi"]].dropna(subset=["cpi"]).drop_duplicates("quarter")
meta["CPI_Q"]={"dataflow":"CPI_Q","url":url,"key":ckey,
    "codes":{"MEASURE":"1 (Index Numbers)","INDEX":"999901 (All groups CPI, seasonally adjusted)","TSEST":"20 (Seas Adj)",
             "REGION":"50 (Weighted avg 8 capital cities)","FREQ":"Q"},
    "min":cpi["quarter"].min(),"max":cpi["quarter"].max(),
    "rows":int(len(cpi)),"nonnull":int(cpi["cpi"].notna().sum())}
print("CPI rows", len(cpi), cpi["quarter"].min(), cpi["quarter"].max())

# ---------------- JOIN ----------------
base = rppi.copy()
base["state"]=base["city"].map({c[0]:c[1] for c in CITIES})
panel = base.merge(lend,on=["state","quarter"],how="left") \
            .merge(retail,on=["state","quarter"],how="left") \
            .merge(unemp,on=["state","quarter"],how="left") \
            .merge(cpi,on="quarter",how="left")
panel = panel[["city","state","quarter","price_index","lending","retail","unemployment","cpi"]]
panel = panel.sort_values(["city","quarter"]).reset_index(drop=True)
panel.to_csv(f"{OUT}/abs_panel.csv",index=False)

# ---------------- VERIFY / SANITY ----------------
verify={}
verify["n_cities"]=int(panel["city"].nunique())
qcounts=panel.groupby("city")["quarter"].nunique().to_dict()
verify["quarters_per_city"]={k:int(v) for k,v in qcounts.items()}
verify["min_quarters_per_city"]=int(min(qcounts.values()))
# price non-null bulk 2004-2025
mask=(panel["quarter"]>="2004")&(panel["quarter"]<="2025-Q4")
verify["price_nonnull_pct_2004_2025"]=round(float(panel.loc[mask,"price_index"].notna().mean())*100,1)
verify["nonnull_by_col"]={c:int(panel[c].notna().sum()) for c in ["price_index","lending","retail","unemployment","cpi"]}

# Perth plateau/decline 2014-2019 ; Sydney dip 2018-19 & 2022
def series(city):
    s=panel[panel["city"]==city].set_index("quarter")["price_index"]
    return s
per=series("Perth"); syd=series("Sydney")
def val(s,q): return float(s[q]) if q in s.index and pd.notna(s[q]) else None
verify["perth_2014Q1"]=val(per,"2014-Q1"); verify["perth_2019Q4"]=val(per,"2019-Q4")
verify["perth_peak_2014_2019"]=None
try:
    seg=per.loc["2014-Q1":"2019-Q4"]; verify["perth_decline_pct_2014_2019"]=round((seg.iloc[-1]-seg.max())/seg.max()*100,1)
except Exception as e: verify["perth_decline_pct_2014_2019"]=str(e)
verify["sydney_2017Q4"]=val(syd,"2017-Q4"); verify["sydney_2019Q2"]=val(syd,"2019-Q2")
verify["sydney_2022Q1"]=val(syd,"2022-Q1"); verify["sydney_2023Q1"]=val(syd,"2023-Q1")

meta["_panel"]={"shape":list(panel.shape),"cities":sorted(panel["city"].unique().tolist()),
    "quarter_min":panel["quarter"].min(),"quarter_max":panel["quarter"].max()}
meta["_verify"]=verify

with open(f"{OUT}/abs_panel_meta.json","w") as f:
    json.dump(meta,f,indent=2)

print("\n=== PANEL", panel.shape, "===")
print(json.dumps(verify,indent=2))

# assertions
assert verify["n_cities"]>=6, "fewer than 6 cities"
assert verify["min_quarters_per_city"]>=60, f"min quarters {verify['min_quarters_per_city']} < 60"
assert verify["price_nonnull_pct_2004_2025"]>=90, "price_index sparse 2004-2025"
print("\nASSERTIONS PASSED")
