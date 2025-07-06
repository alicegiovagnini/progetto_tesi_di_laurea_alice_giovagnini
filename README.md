Piattaforma sperimentale per lo studio dell'interazione ad iniziativa mista tra persone e intelligenza artificiale nei processi decisionali di gruppo.

## Descrizione

Questa piattaforma implementa il "Moon Survival Problem" per analizzare come l'intelligenza artificiale possa migliorare i processi decisionali collaborativi attraverso interventi strategici durante le discussioni di gruppo.

## Tecnologie utilizzate

- **Python 3.9**
- **Streamlit** - Framework per l'interfaccia web
- **WebSocket** - Comunicazione real-time
- **SQLite** - Database per memorizzazione dati
- **OpenAI API** - Integrazione con Large Language Models

## Struttura del progetto

- `tesi_italiano_merged.py` - Applicazione principale Streamlit
- `backend.py` - Logica di backend e gestione dati
- `database.py` - Gestione database SQLite
- `apikey.py` - Configurazione API keys
- `lobby_functions.py` - Funzioni per gestione gruppi
- `error_handler.py` - Gestione errori
- `requirements.txt` - Dipendenze Python

## Come eseguire

1. Installare le dipendenze:
   ```bash
   pip install -r requirements.txt

2. Avviare lo script di backend sulla porta 8000 con il comando:
   ```bash
   uvicorn backend:app --reload --host 127.0.0.1 --port 8000

   oppure

   uvicorn backend:app --reload --host 127.0.0.1 --port 8000 --log-level warning

3. Avviare la parte frontend di Streamlit con il comando:
   ```bash
   streamlit run tesi_italiano_merged.py --theme.base dark
