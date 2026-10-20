# RED Benchmark Dashboard

Dashboard Streamlit che legge automaticamente i file Excel dalla cartella `data/`.

## Struttura

```text
RED_Benchmark_GitHub/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/config.toml
├── data/
│   ├── Perfomance Portafoglio YTD.xlsx
│   └── YYYY.MM_RED_Performance Benchmark.xlsx
└── output/
```

## Aggiornamento mensile

1. Aggiorna `data/Perfomance Portafoglio YTD.xlsx` aggiungendo il nuovo mese.
2. Aggiungi il nuovo file benchmark, per esempio `data/2026.09_RED_Performance Benchmark.xlsx`.
3. Esegui commit e push su GitHub.
4. Streamlit rileggerà automaticamente tutti i file che rispettano il modello `*_RED_Performance Benchmark.xlsx`.

Non è necessario modificare `app.py`.

## Test in GitHub Codespaces

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy su Streamlit Community Cloud

- Repository: il repository GitHub che contiene questi file
- Branch: `main`
- Main file path: `app.py`

## Controlli inclusi

- presenza dei file richiesti;
- riconoscimento dei mesi comuni;
- somma dei pesi benchmark con tolleranza 0,01%;
- rendimento YTD portafoglio e benchmark;
- differenza in punti percentuali e basis point;
- tabella dei contributi;
- grafico e download CSV.

## Nota sulla riservatezza

Se i file contengono dati riservati, usa un repository privato e verifica che la modalità di distribuzione Streamlit scelta sia compatibile con le policy aziendali.
