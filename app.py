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
            
            # Estrazione sicura della data dal nome del file (es. 2026.01 -> fine mese)
            filename = os.path.basename(f)
            parts = filename.split("_")[0].split(".")
            year = int(parts[0])
            month = int(parts[1])
            # Data di fine mese calcolata programmaticamente
            date_val = pd.to_datetime(f"{year}-{month:02d}-01") + pd.offsets.MonthEnd(0)
            
            # Parsing componenti dalla tabella riepilogativa (righe da 4 a 12)
            rows_idx = range(4, 13)
            for r in rows_idx:
                if r >= len(df_riep):
                    continue
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
        sim_bmk_ytd = 0.0
        for _, row in sub_bmk.iterrows():
            comp_name = row["Component"]
            w_sim = custom_weights.get(comp_name, 0.0)
            sim_bmk_ytd += w_sim * row["ReturnYTD"]
            
        calc_rows.append({
            "Date": d,
            "Port_YTD": port_ytd,
            "Official_Bmk_YTD": off_bmk_ytd,
            "Simulated_Bmk_YTD": sim_bmk_ytd,
            "Excess_Off_YTD": port_ytd - off_bmk_ytd if pd.notna(port_ytd) else np.nan,
            "Excess_Sim_YTD": port_ytd - sim_bmk_ytd if pd.notna(port_ytd) else np.nan
        })

    df_calc = pd.DataFrame(calc_rows)
else:
    df_calc = pd.DataFrame()

# ---------------------------------------------------------
# DASHBOARD INTERATTIVA STREAMLIT
# ---------------------------------------------------------
st.title("📈 Quantitative Performance Attribution & Benchmark Dashboard")
st.caption("Sistema dinamico per l'analisi di portafoglio, benchmark compositi e backtesting interattivo.")

if not df_calc.empty:
    latest_row = df_calc.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rendimento Portafoglio YTD", f"{latest_row['Port_YTD']*100:.2f}%" if pd.notna(latest_row['Port_YTD']) else "N/A")
    col2.metric("Rendimento Benchmark Ufficiale", f"{latest_row['Official_Bmk_YTD']*100:.2f}%")
    col3.metric("Sovra/Sotto-performance", f"{latest_row['Excess_Off_YTD']*10000:.0f} bps" if pd.notna(latest_row['Excess_Off_YTD']) else "N/A", 
                delta=f"{latest_row['Excess_Off_YTD']*100:.2f}%" if pd.notna(latest_row['Excess_Off_YTD']) else None)
    col4.metric("Benchmark Simulato YTD", f"{latest_row['Simulated_Bmk_YTD']*100:.2f}%",
                delta=f"{(latest_row['Port_YTD'] - latest_row['Simulated_Bmk_YTD'])*10000:.0f} bps vs Port" if pd.notna(latest_row['Port_YTD']) else None)

    st.markdown("---")

    # GRAFICO PERFORMANCE CUMULATA YTD
    st.subheader("📊 Confronto Traiettoria Cumulata YTD")
    fig_perf = bg.Figure()
    fig_perf.add_trace(bg.Scatter(x=df_calc["Date"], y=df_calc["Port_YTD"]*100, name="Portafoglio", line=dict(color="blue", width=3)))
    fig_perf.add_trace(bg.Scatter(x=df_calc["Date"], y=df_calc["Official_Bmk_YTD"]*100, name="Bmk Ufficiale", line=dict(color="green", dash="dash")))
    fig_perf.add_trace(bg.Scatter(x=df_calc["Date"], y=df_calc["Simulated_Bmk_YTD"]*100, name="Bmk Simulato", line=dict(color="orange", dash="dot")))

    fig_perf.update_layout(yaxis_title="Rendimento YTD (%)", xaxis_title="Data", hovermode="x unified")
    st.plotly_chart(fig_perf, use_container_width=True)

    # CONTRIBUTO COMPONENTI
    st.subheader("🧩 Contributo delle Componenti al Benchmark (Ultimo Mese)")
    sub_latest = df_bmk_comp[df_bmk_comp["Date"] == last_date].copy()
    sub_latest["Contributo_Ufficiale"] = sub_latest["OfficialWeight"] * sub_latest["ReturnYTD"] * 100
    sub_latest["Contributo_Simulato"] = sub_latest["Component"].map(custom_weights) * sub_latest["ReturnYTD"] * 100

    fig_contrib = px.bar(sub_latest, x="Component", y=["Contributo_Ufficiale", "Contributo_Simulato"],
                         barmode="group", labels={"value": "Contributo %", "variable": "Scenario"},
                         title=f"Contributo al Rendimento YTD al {last_date.strftime('%Y-%m-%d')}")
    st.plotly_chart(fig_contrib, use_container_width=True)

    # TABELLA METRICHE
    st.subheader("📋 Tabella Dettagliata Periodica")
    st.dataframe(df_calc.style.format({
        "Port_YTD": "{:.2%}",
        "Official_Bmk_YTD": "{:.2%}",
        "Simulated_Bmk_YTD": "{:.2%}",
        "Excess_Off_YTD": "{:.2%}",
        "Excess_Sim_YTD": "{:.2%}"
    }), use_container_width=True)
else:
    st.warning("Nessun dato trovato nella cartella `data/`. Assicurati di aver inserito correttamente i file Excel.")