from pathlib import Path
import io
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="RED Benchmark Dashboard", layout="wide")
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PORTFOLIO_FILE = DATA_DIR / "Perfomance Portafoglio YTD.xlsx"
BENCHMARK_PATTERN = "*_RED_Performance Benchmark.xlsx"
TOLERANCE = 0.0001

st.title("RED | Portafoglio vs Benchmark")
st.caption("Lettura automatica dei file Excel presenti nella cartella data/")

@st.cache_data(show_spinner=False)
def read_portfolio(path: str) -> pd.DataFrame:
    xls = pd.ExcelFile(path, engine="openpyxl")
    for sheet in xls.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
        cols = {str(c).strip().upper(): c for c in df.columns}
        date_col = next((v for k, v in cols.items() if "PERIODO" in k or "DATA" in k), None)
        ret_col = next((v for k, v in cols.items() if "REND" in k and "YTD" in k), None)
        if date_col is not None and ret_col is not None:
            out = df[[date_col, ret_col]].copy()
            out.columns = ["Data", "Portafoglio_YTD"]
            out["Data"] = pd.to_datetime(out["Data"], errors="coerce")
            out["Portafoglio_YTD"] = pd.to_numeric(out["Portafoglio_YTD"], errors="coerce")
            return out.dropna().drop_duplicates("Data").sort_values("Data")
    raise ValueError("Colonne PERIODO/DATA e RENDIMENTI YTD non riconosciute nel file portafoglio.")

@st.cache_data(show_spinner=False)
def read_benchmark_summary(path: str) -> tuple[pd.Timestamp, pd.DataFrame, float]:
    raw = pd.read_excel(path, sheet_name="Riepilogo Proposta", header=None, engine="openpyxl")
    asof = pd.NaT
    for value in raw.to_numpy().ravel():
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.notna(parsed) and 2020 <= parsed.year <= 2100:
            asof = parsed
            break
    rows = []
    for i in range(len(raw)):
        ac = raw.iloc[i, 0] if raw.shape[1] > 0 else None
        component = raw.iloc[i, 1] if raw.shape[1] > 1 else None
        sub_weight = raw.iloc[i, 2] if raw.shape[1] > 2 else None
        aa_target = raw.iloc[i, 3] if raw.shape[1] > 3 else None
        total_weight = raw.iloc[i, 4] if raw.shape[1] > 4 else None
        component_ytd = raw.iloc[i, 5] if raw.shape[1] > 5 else None
        if isinstance(component, str) and ("Index" in component or "ETF" in component):
            rows.append([ac, component, sub_weight, aa_target, total_weight, component_ytd])
    comp = pd.DataFrame(rows, columns=["Asset Class", "Componente", "Peso interno", "AA target", "Peso", "Rendimento YTD"])
    for c in ["Peso interno", "AA target", "Peso", "Rendimento YTD"]:
        comp[c] = pd.to_numeric(comp[c], errors="coerce")
    comp["Asset Class"] = comp["Asset Class"].ffill()
    comp["AA target"] = comp["AA target"].ffill()
    comp["Peso"] = comp["Peso"].where(comp["Peso"].notna(), comp["Peso interno"] * comp["AA target"])
    comp["Contributo"] = comp["Peso"] * comp["Rendimento YTD"]
    benchmark_ytd = float(comp["Contributo"].sum())
    return asof, comp, benchmark_ytd

if not DATA_DIR.exists():
    st.error("Cartella data/ non trovata nel repository.")
    st.stop()

benchmark_files = sorted(DATA_DIR.glob(BENCHMARK_PATTERN))
missing = []
if not PORTFOLIO_FILE.exists():
    missing.append(PORTFOLIO_FILE.name)
if not benchmark_files:
    missing.append(BENCHMARK_PATTERN)
if missing:
    st.error("File mancanti in data/: " + ", ".join(missing))
    st.stop()

try:
    portfolio = read_portfolio(str(PORTFOLIO_FILE))
    bm_rows, all_components = [], []
    for file in benchmark_files:
        date, components, benchmark_ytd = read_benchmark_summary(str(file))
        bm_rows.append({"Data": date, "Benchmark_YTD": benchmark_ytd, "File": file.name, "Somma_pesi": components["Peso"].sum()})
        components["Data"] = date
        components["File"] = file.name
        all_components.append(components)
    benchmark = pd.DataFrame(bm_rows).dropna(subset=["Data"]).sort_values("Data")
    components = pd.concat(all_components, ignore_index=True)
except Exception as exc:
    st.exception(exc)
    st.stop()

portfolio["Mese"] = pd.to_datetime(
    portfolio["Data"],
    dayfirst=True,
    errors="coerce"
).dt.strftime("%Y-%m")

benchmark["Mese"] = pd.to_datetime(
    benchmark["Data"],
    dayfirst=True,
    errors="coerce"
).dt.strftime("%Y-%m")
comparison = portfolio.merge(benchmark, on="Mese", suffixes=("_Portafoglio", "_Benchmark"), how="inner")
comparison["Differenza_pp"] = comparison["Portafoglio_YTD"] - comparison["Benchmark_YTD"]
comparison["Differenza_bp"] = comparison["Differenza_pp"] * 10000
comparison["Esito"] = np.where(comparison["Differenza_pp"] >= 0, "Sovraperformance", "Sottoperformance")
comparison["Periodo"] = comparison["Mese"].astype(str)

st.write("Portfolio righe:", len(portfolio))
st.write("Benchmark righe:", len(benchmark))

st.write("Date portafoglio")
st.dataframe(portfolio[["Data","Mese"]])

st.write("Date benchmark")
st.dataframe(benchmark[["Data","Mese"]])

if comparison.empty:
    st.error("Nessun mese comune tra portafoglio e benchmark.")
    st.stop()

latest = comparison.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Portafoglio YTD", f"{latest['Portafoglio_YTD']:.2%}")
c2.metric("Benchmark YTD", f"{latest['Benchmark_YTD']:.2%}")
c3.metric("Differenza", f"{latest['Differenza_pp']:.2%}")
c4.metric("Differenza (bp)", f"{latest['Differenza_bp']:.0f}")

quality = benchmark.assign(Esito_pesi=lambda x: np.where((x["Somma_pesi"] - 1).abs() <= TOLERANCE, "OK", "Fuori tolleranza"))
if (quality["Esito_pesi"] != "OK").any():
    st.warning("Almeno un file benchmark ha pesi che non sommano al 100% entro la tolleranza dello 0,01%.")
else:
    st.success(f"{len(benchmark_files)} file benchmark letti automaticamente da data/. Controllo pesi superato.")

chart_data = comparison[["Periodo", "Portafoglio_YTD", "Benchmark_YTD"]].melt(
    "Periodo", var_name="Serie", value_name="Rendimento YTD"
)
fig = px.line(chart_data, x="Periodo", y="Rendimento YTD", color="Serie", markers=True,
              title="Andamento YTD: Portafoglio vs Benchmark")
fig.update_yaxes(tickformat=".1%")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Tabella di confronto")
show = comparison[["Periodo", "Portafoglio_YTD", "Benchmark_YTD", "Differenza_pp", "Differenza_bp", "Esito"]].copy()
st.dataframe(show.style.format({
    "Portafoglio_YTD": "{:.2%}", "Benchmark_YTD": "{:.2%}",
    "Differenza_pp": "{:.2%}", "Differenza_bp": "{:.0f}"
}), use_container_width=True, hide_index=True)

st.subheader("Controllo file e pesi")
st.dataframe(quality[["File", "Data", "Somma_pesi", "Esito_pesi"]].style.format({"Somma_pesi": "{:.2%}"}),
             use_container_width=True, hide_index=True)

latest_date = benchmark["Data"].max()
st.subheader(f"Contributi benchmark al {latest_date:%d/%m/%Y}")
latest_components = components[components["Data"] == latest_date][["Asset Class", "Componente", "Peso", "Rendimento YTD", "Contributo"]]
st.dataframe(latest_components.style.format({"Peso": "{:.2%}", "Rendimento YTD": "{:.2%}", "Contributo": "{:.2%}"}),
             use_container_width=True, hide_index=True)

csv = show.to_csv(index=False).encode("utf-8")
st.download_button("Esporta confronto CSV", csv, "confronto_portafoglio_benchmark.csv", "text/csv")

with st.expander("File rilevati"):
    st.write("Portafoglio:", PORTFOLIO_FILE.name)
    st.write("Benchmark:")
    for f in benchmark_files:
        st.write("-", f.name)
