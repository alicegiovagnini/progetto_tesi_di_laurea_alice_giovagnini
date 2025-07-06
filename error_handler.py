import streamlit as st
import requests
from requests.exceptions import ConnectionError
import functools
import time


class BackendMonitor:
    def __init__(self):
        self.backend_down = False
        self.last_error_time = 0
        self.message_shown = False

    def check_and_show_error(self):
        """Mostra il messaggio di errore se il backend è down"""
        current_time = time.time()

        if self.backend_down and not self.message_shown:
            st.error("""
             **Il server backend è stato chiuso**

            Per continuare, riavvia il backend con il comando:
            ```
            uvicorn backend:app --reload --host 127.0.0.1 --port 8000
            ```

            Poi aggiorna questa pagina.
            """)
            self.message_shown = True
            # Disabilita autorefresh per evitare spam
            if 'autorefresh_disabled' not in st.session_state:
                st.session_state.autorefresh_disabled = True

    def handle_connection_error(self):
        """Gestisce un errore di connessione"""
        current_time = time.time()

        # Evita di loggare troppo spesso
        if not self.backend_down or (current_time - self.last_error_time) > 30:
            if not self.backend_down:
                print("\n" + "=" * 50)
                print(" BACKEND DISCONNESSO")
                print("Il server backend non è più raggiungibile.")
                print("=" * 50 + "\n")

            self.backend_down = True
            self.last_error_time = current_time

    def handle_success(self):
        """Chiamata quando una connessione riesce"""
        if self.backend_down:
            print("\n" + "=" * 50)
            print(" BACKEND RICONNESSO")
            print("Il server backend è di nuovo online.")
            print("=" * 50 + "\n")

            self.backend_down = False
            self.message_shown = False

            # Riabilita autorefresh
            if 'autorefresh_disabled' in st.session_state:
                del st.session_state.autorefresh_disabled

            st.success(" Connessione ristabilita!")
            time.sleep(1)
            st.rerun()

# Istanza globale
monitor = BackendMonitor()


def catch_connection_errors(func):
    """Decorator per catturare automaticamente gli errori di connessione"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            # Se arriva qui, la connessione è riuscita
            monitor.handle_success()
            return result
        except ConnectionError:
            monitor.handle_connection_error()
            return None
        except Exception as e:
            # Se è un errore di connessione nascosto
            if "Connection refused" in str(e) or "Max retries exceeded" in str(e):
                monitor.handle_connection_error()
                return None
            else:
                # Altri errori vengono ri-lanciati
                raise e

    return wrapper


# Patching automatico di requests
if not hasattr(requests, '_patched_for_backend_monitor'):
    # Salva le funzioni originali
    requests._original_get = requests.get
    requests._original_post = requests.post
    requests._original_put = requests.put
    requests._original_delete = requests.delete

    # Applica il decorator
    requests.get = catch_connection_errors(requests.get)
    requests.post = catch_connection_errors(requests.post)
    requests.put = catch_connection_errors(requests.put)
    requests.delete = catch_connection_errors(requests.delete)

    # Marca come già patchato
    requests._patched_for_backend_monitor = True

    print(" Gestore errori di connessione attivato")


def show_backend_status():
    """Funzione da chiamare in ogni pagina per mostrare lo stato del backend"""
    monitor.check_and_show_error()

    # Disabilita autorefresh se backend down
    return not monitor.backend_down


def backend_is_available():
    """Verifica se il backend è disponibile"""
    return not monitor.backend_down