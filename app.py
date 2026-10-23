import os
import glob
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as bg
import streamlit as st

st.set_page_config(page_title="Quantitative Portfolio & Benchmark Dashboard", layout="wide")

# ---------------------------------------------------------
# FUNZIONI DI CARICAMENTO E PROCESSING DATI
# ---------------------------------------------------------
@st.cache_data
def load_benchmark_data(data_dir="data"):
    files = sorted(glob.glob(os.path.join(data_dir, "*_RED_Performance Benchmark.xlsx")))
    records = []
    
    for f in files:
        try:
            xls = pd.ExcelFile(f)
            df_riep = pd.read_excel(xls, sheet_name="Riepilogo Proposta")
            date_val = pd.to_datetime(df_riep.iloc[0, 1])
            
            # Parsing componenti dalla tabella riepilogativa
            rows_idx = range(4, 13)
            for r in rows_idx:
                comp_name = df_riep.iloc[r, 2]
                asset_cls = df_riep.iloc[r, 1]
                if pd.isna(comp_name):
                    continue
                
                weight_bmk = float(df_riep.iloc[r, 6])
                ret_ytd = float(df_riep.iloc[r, 7])
                
                records.append({
                    "Date": date_val,
                    "Component": str(comp_name).strip(),
                    "AssetClass": str(asset_cls).strip() if pd.notna(asset_cls) else "Other",
                    "OfficialWeight": weight_bmk,
                    "ReturnYTD": ret_ytd
                })
        except Exception as e:
            st.warning(f"Errore nella lettura del file {f}: {e}")
            
    df_bmk_comp = pd.DataFrame(records)
    return df_bmk_comp

@st.cache_data
def load_portfolio_data(port_file="data/Perfomance Portafoglio YTD.xlsx"):
    if not os.path.exists(port_file):
        return pd.DataFrame()
    df_port = pd.read_excel(port_file, sheet_name="2026")
    df_port.columns = [c.upper().strip() for c in df_port.columns]
    df_port["PERIODO"] = pd.to_datetime(df_port["PERIODO"])
    df_port = df_port.rename(columns={"PERIODO": "Date", "RENDIMENTI YTD": "Port_ReturnYTD"})
    return df_port

# Caricamento dati da cartella data/
df_bmk_comp = load_benchmark_data("data")
df_port = load_portfolio_data("data/Perfomance Portafoglio YTD.xlsx")

# ---------------------------------------------------------
# SIDEBAR & INTERFACCIA UTENTE
# ---------------------------------------------------------
st.sidebar.title("⚙️ Configurazione & Backtest")

st.sidebar.subheader("1. Inserimento Dati Mancanti (es. Settembre)")
enable_sept = st.sidebar.checkbox("Aggiungi Dati Settembre 2026", value=False)
if enable_sept:
    sept_date = pd.to_datetime("2026-09-30")
    sept_port_ret = st.sidebar.number_input("Rendimento YTD Portafoglio Settembre (%)", value=6.0) / 100.0
    
    if not df_port.empty and sept_date not in df_port["Date"].values:
        new_row_port = pd.DataFrame([{"Date": sept_date, "Port_ReturnYTD": sept_port_ret}])
        df_port = pd.concat([df_port, new_row_port], ignore_index=True)

# Selezione Componenti e Modifica Pesi
st.sidebar.subheader("2. Modifica Pesi Benchmark (Backtest)")
if not df_bmk_comp.empty:
    components = df_bmk_comp["Component"].unique().tolist()
    last_date = df_bmk_comp["Date"].max()
    df_last_weights = df_bmk_comp[df_bmk_comp["Date"] == last_date].set_index("Component")["OfficialWeight"].to_dict()
else:
    components = []
    df_last_weights = {}

custom_weights = {}
st.sidebar.write("Imposta i pesi personalizzati:")
sum_weights = 0.0
for c in components:
    default_w = df_last_weights.get(c, 0.0)
    w_val = st.sidebar.number_input(f"{c[:25]}...", min_value=0.0, max_value=1.0, value=float(default_w), step=0.01)
    custom_weights[c] = w_val
    sum_weights += w_val

st.sidebar.markdown(f"**Somma Pesi Selezionati:** `{sum_weights*100:.2f}%`")
auto_normalize = st.sidebar.checkbox("Normalizza automaticamente pesi a 100%", value=True)

if abs(sum_weights - 1.0) > 0.0001:
    if auto_normalize and sum_weights > 0:
        custom_weights = {k: v / sum_weights for k, v in custom_weights.items()}
        st.sidebar.info("Pesi normalizzati al 100%.")
    else:
        st.sidebar.error("⚠️ La somma dei pesi differisce da 100%!")

# Scenari Predefiniti
scenario_option = st.sidebar.selectbox("Seleziona Scenario Predefinito", [
    "Personalizzato", 
    "Benchmark Ufficiale", 
    "Equiponderato (Equal Weight)", 
    "Solo Equity (100% MSCI World)",
    "Conservativo (80% Bond / 20% Cash)"
])

if scenario_option == "Benchmark Ufficiale":
    custom_weights = df_last_weights
elif scenario_option == "Equiponderato (Equal Weight)" and components:
    eq_w = 1.0 / len(components)
    custom_weights = {c: eq_w for c in components}

# ---------------------------------------------------------
# CALCOLO SERIE STORICHE E PERFORMANCE ATTRIBUTION
# ---------------------------------------------------------
if not df_bmk_comp.empty:
    dates = sorted(df_bmk_comp["Date"].unique())
    calc_rows = []

    for d in dates:
        sub_bmk = df_bmk_comp[df_bmk_comp["Date"] == d]
        p_row = df_port[df_port["Date"] == d] if not df_port.empty else pd.DataFrame()
        
        port_ytd = p_row["Port_ReturnYTD"].values[0] if not p_row.empty and len(p_row) > 0 else np.nan
        
        # Calcolo Bmk Ufficiale YTD
        off_bmk_ytd = (sub_bmk["OfficialWeight"] * sub_bmk["ReturnYTD"]).sum()
        
        # Calcolo Bmk Simulato YTD
        sim_bmk