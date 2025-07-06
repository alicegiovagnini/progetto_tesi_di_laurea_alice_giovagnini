import os, time, random, re, threading
import streamlit as st  # type: ignore
import json
import copy
import requests
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from gpt4all import GPT4All  # type: ignore
from st_draggable_list import DraggableList  # type: ignore
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import scipy.stats as stats  # type: ignore
from fuzzywuzzy import process  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
from database import get_engine_alone, get_engine, get_session, insert_user_results_to_db, insert_user_info_to_db, \
    UserResults, UserInfo, insert_user_questions_to_db, insert_user_results_alone, insert_user_post_questions_to_db;
from groq import Groq
from apikey import GROQ_API_KEY
from lobby_functions import get_modalita, send_previous_list_to_backend, send_message, chatroom, fetch_messages, \
    fetch_connected_users, next_page, prev_page, \
    generate_unique_key, send_continua_message, register_user_rest, unregister_user_rest, check_group_status, send_group_invitation, accept_group_invitation, send_multiple_group_invitations, respond_to_group_invitation, fetch_messages_from_websocket
from error_handler import show_backend_status, backend_is_available

if 'reset_page' not in st.session_state:
    st.session_state.page = 1
    st.session_state.reset_page = True

# Garantisce ID di sessione univoci
if "session_id" not in st.session_state:
    st.session_state.session_id = str(time.time())

if 'force_rerun' not in st.session_state:
    st.session_state.force_rerun = False

if 'list_locked' not in st.session_state:
    st.session_state.list_locked = False
if 'locked_by_user' not in st.session_state:
    st.session_state.locked_by_user = ""
if 'user_is_editing' not in st.session_state:
    st.session_state.user_is_editing = False

if 'previous_list_text_saved' not in st.session_state:
    st.session_state.previous_list_text_saved = ""

if 'group_members' not in st.session_state:
    st.session_state.group_members = []  # Lista degli utenti nel gruppo in formazione
if 'pending_invites' not in st.session_state:
    st.session_state.pending_invites = []  # Lista degli utenti a cui è stata inviata una richiesta
elif isinstance(st.session_state.pending_invites, list):
    # Assicura che tutti gli elementi siano stringhe
    temp_invites = []
    for invite in st.session_state.pending_invites:
        if isinstance(invite, list):
            temp_invites.extend([str(item) for item in invite])
        else:
            temp_invites.append(str(invite))
    st.session_state.pending_invites = temp_invites
if 'creating_group' not in st.session_state:
    st.session_state.creating_group = False  # Flag per indicare se l'utente sta creando un gruppo

#Verifica che la pagina sia inizializzata a 1 al primo avvio
if 'page' not in st.session_state:
    st.session_state.page = 1

items = [
    {"id": 1, "name": "Scatola di Fiammiferi"},
    {"id": 2, "name": "Concentrato Alimentare"},
    {"id": 3, "name": "Corda in nylon di 15 metri"},
    {"id": 4, "name": "Paracadute di seta"},
    {"id": 5, "name": "Unità di Riscaldamento Portatile"},
    {"id": 6, "name": "Due pistole calibro .45"},
    {"id": 7, "name": "Latte disidratato"},
    {"id": 8, "name": "Bombole di ossigeno di 45kg"},
    {"id": 9, "name": "Mappa delle stelle"},
    {"id": 10, "name": "Zattera di salvataggio autogonfiabile"},
    {"id": 11, "name": "Bussola Magnetica"},
    {"id": 12, "name": "20 litri d'acqua"},
    {"id": 13, "name": "Razzo di segnalazione"},
    {"id": 14, "name": "Cassa di pronto soccorso"},
    {"id": 15, "name": "Radiolina alimentata con energia solare"}
]

if 'previous_list' not in st.session_state or st.session_state.previous_list is None:
    st.session_state.previous_list = items.copy()  # Usa una copia della lista predefinita

# Variabili di stato
if 'alone' not in st.session_state:
    st.session_state.alone = False
if 'modalita' not in st.session_state:
    st.session_state.modalita = ""
if 'user_input' not in st.session_state:
    st.session_state.user_input = ""
if "user_list" not in st.session_state:
    st.session_state.user_list = []
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'previous_list_text' not in st.session_state:
    st.session_state.previous_list_text = ""
if 'page' not in st.session_state:
    st.session_state.page = 1
if 'llm_response_generated' not in st.session_state:
    st.session_state.llm_response_generated = False
if 'llm_response' not in st.session_state:
    st.session_state.llm_response = ""
if 'updated_list' not in st.session_state:
    st.session_state.updated_list = []
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'previous_list' not in st.session_state:
    st.session_state.previous_list = items
if 'partner' not in st.session_state:
    st.session_state.partner = ""
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'valid' not in st.session_state:
    st.session_state.valid = "not valid"


def request_editing_lock(group_id, username):
    """Richiede il lock per iniziare a modificare"""
    try:
        response = requests.post(
            "http://127.0.0.1:8000/editing_lock",
            json={
                "group_id": group_id,
                "username": username,
                "action": "start"
            },
            timeout=3
        )

        if response.status_code == 200:
            data = response.json()
            if data["status"] == "lock_acquired":
                st.session_state.user_is_editing = True
                return True
            elif data["status"] == "locked":
                st.warning(f" {data['message']}")
                return False
        return False
    except Exception as e:
        print(f"Errore richiesta lock: {e}")
        return False


def release_editing_lock(group_id, username):
    """Rilascia il lock dopo aver terminato la modifica"""
    try:
        response = requests.post(
            "http://127.0.0.1:8000/editing_lock",
            json={
                "group_id": group_id,
                "username": username,
                "action": "end"
            },
            timeout=3
        )

        if response.status_code == 200:
            st.session_state.user_is_editing = False
            return True
        return False
    except Exception as e:
        print(f"Errore rilascio lock: {e}")
        return False



BASE_URL = "http://127.0.0.1:8000"

hide_streamlit_style = """
                <style>
                div[data-testid="stToolbar"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
                }
                div[data-testid="stDecoration"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
                }
                div[data-testid="stStatusWidget"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
                }
                #MainMenu {
                visibility: hidden;
                height: 0%;
                }
                header {
                visibility: hidden;
                height: 0%;
                }
                footer {
                visibility: hidden;
                height: 0%;
                }
                </style>
                """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.markdown(
    """
    <style>
        /* Custom CSS for the wide page layout */
        .stApp > div[data-testid="stVerticalBlock"] {
            max-width: 90%;
            margin: auto;
            padding: 20px;
        }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown("""
<style>
    .stApp {
        text-align: justify;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
    <style>
    .big-button {
        font-size: 20px !important;  /* Change font size */
        padding: 15px 25px !important;  /* Change padding */
        background-color: #4CAF50 !important;  /* Custom background color */
        color: white !important;  /* Custom text color */
        border-radius: 10px !important;  /* Rounded edges */
        border: none !important;
    }
    </style>
""", unsafe_allow_html=True)


def fetch_updated_list(group_id):
    """
    Funzione per recuperare la lista aggiornata dal server senza manipolarla
    """
    try:
        notification_area = st.empty()
        notification_area.info("Sincronizzazione in corso...")

        # Aggiunge parametri per evitare la cache
        timestamp = int(time.time() * 1000)
        random_param = random.randint(1, 10000)
        cache_buster = f"&_={timestamp}&r={random_param}"

        # Richiede esplicitamente la lista aggiornata dal server tramite GET
        response = requests.get(
            f"http://127.0.0.1:8000/get_shared_list/{group_id}?nocache={cache_buster}",
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            server_list = data.get("lista", [])

            if server_list and len(server_list) > 0:
                # Stampa i dati completi della risposta per debug
                print(f"RISPOSTA SERVER COMPLETA: {data}")

                # Verifica se la lista è diversa da quella attuale
                current_list = st.session_state.previous_list if 'previous_list' in st.session_state else []

                # Usa la funzione di debug per confrontare dettagliatamente
                debug_compare_lists(server_list, current_list)

                st.session_state.previous_list = copy.deepcopy(server_list)
                notification_area.success("Lista aggiornata dal server!")
                print("Lista sostituita con quella del server SENZA MANIPOLAZIONI")
                return True
            else:
                notification_area.warning("Nessuna lista valida ricevuta dal server")
                return False
        else:
            notification_area.error(f"Errore nella sincronizzazione: {response.status_code}")
            return False
    except Exception as e:
        print(f"Errore di connessione durante fetch_updated_list: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def highlight_closeness(row):
    initial_diff = abs(row['La tua lista iniziale'] - row['Lista ufficiale NASA'])
    final_diff = abs(row['La lista collaborativa'] - row['Lista ufficiale NASA'])
    styles = [''] * len(row)
    # Dà una colorazione in base al miglioramento o al peggioramento
    if final_diff < initial_diff:
        styles[2] = 'background-color: lightgreen'
    elif final_diff > initial_diff:
        styles[2] = 'background-color: lightcoral'

    return styles


def debug_compare_lists(server_list, current_list):
    """
    Funzione di debug per confrontare dettagliatamente le liste
    """
    print(f"Lista server: {len(server_list)} elementi")
    print(f"Lista locale: {len(current_list)} elementi")

    print("\nPrimi 5 elementi LISTA SERVER:")
    for i, item in enumerate(server_list[:5]):
        print(f"  {i}: id={item['id']}, name={item['name']}")

    print("\nPrimi 5 elementi LISTA LOCALE:")
    for i, item in enumerate(current_list[:5]):
        print(f"  {i}: id={item['id']}, name={item['name']}")

    print("\nConfrontando ID in ordine:")
    server_ids = [item['id'] for item in server_list]
    local_ids = [item['id'] for item in current_list]
    print(f"  Server IDs: {server_ids}")
    print(f"  Local IDs: {local_ids}")

    print("\nSono identiche?", server_ids == local_ids)
    print("==================================")


def submit_list_update(group_id, updated_list):
    """
    Funzione per inviare una lista aggiornata al server
    """
    try:
        # Verifica che updated_list non sia None
        if updated_list is None:
            print("Errore: lista da sincronizzare è None")
            return False

        # Aggiunge timestamp per evitare problemi di cache
        timestamp = int(time.time() * 1000)

        for i, item in enumerate(updated_list):
            item['order'] = i
            item['last_modified'] = timestamp

        # Prepara i dati da inviare
        payload = {
            "group_id": group_id,
            "username": st.session_state.username,
            "list": updated_list,
            "timestamp": timestamp,
            "changed": True
        }

        # Effettua una singola richiesta POST al backend
        response = requests.post(
            "http://127.0.0.1:8000/sync_list",
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )

        if response.status_code == 200:
            # Aggiorna la lista locale
            st.session_state.previous_list = copy.deepcopy(updated_list)
            st.session_state.force_rerun = True
            return True
        else:
            print(f"Errore nell'aggiornamento della lista: {response.status_code}")
            print(f"  Risposta: {response.text}")
            return False
    except Exception as e:
        print(f"Errore di connessione durante submit_list_update: {e}")
        import traceback
        print(traceback.format_exc())
        return False


# Page 1: inizio ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
if st.session_state.page == 1:

    # Titolo in CSS
    st.markdown("""
        <style>
        .big-title {
            font-size: 50px;
            font-weight: bold;
            color: #ffffff;
            text-align: left;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div id='top'></div>", unsafe_allow_html=True)
    st.title("Ranking Interattivo con LLM")

    st.write(
        "L'esperimento è composto da 5 passaggi e si basa sull'interazione con un Large Language Model (LLM), che è un modello di intelligenza artificiale basato su testo. Un esempio di LLM è ChatGPT.")
    st.write("---------")
    st.markdown("I passaggi sono i seguenti:")

    st.write("### 1) Compilare un questionario iniziale")
    st.write("")

    st.write("### 2) Stilare una classifica individualmente")
    st.write("_Dovrai ordinare 15 oggetti in base alle istruzioni che ti verranno fornite._")
    st.write("")

    st.write("### 3) Modificare la classifica in base al suggerimento del LLM")
    st.write("_L’operazione avviene in collaborazione con altri partecipanti._")
    st.write("")

    st.write("### 4) Compilare un questionario post-esperimento")
    st.write("_Dovrai condividere la tua esperienza e valutare diversi aspetti dell'interazione con l'LLM._")
    st.write("")

    st.write("### 5) Visualizzare i risultati")
    st.write(
        "_Le due classifiche verranno confrontate con la classifica fornita dalla NASA e verranno mostrati anche altri dati._")
    st.write("")

    st.write("------------")
    if st.button("Avanti"):
        st.session_state.page += 1
        st.rerun()


# Page 2 : Questionario-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
elif st.session_state.page == 2:

    st.markdown("<div id='top'></div>", unsafe_allow_html=True)

    domande_iniziali = ["Età", "Sesso", "Professione", "Esperienza con i LLM (ex. ChatGPT)"]

    st.title("Questionario iniziale")
    st.write("------------------")
    domande = [
        "Riconosco e ricompenso chi raggiunge i propri obiettivi.",
        "Aiuto le persone a migliorare e sviluppare il loro potenziale.",
        "Fornisco feedback chiari su come stanno andando le cose.",
        "Presto attenzione a chi rischia di sentirsi escluso.",
        "Faccio sentire le persone apprezzate e a proprio agio.",
        "Trasmetto una visione chiara e coinvolgente su ciò che posso realizzare.",
        "Aiuto gli altri a trovare significato nel loro lavoro.",
        "Chiedo agli altri solo ciò che è assolutamente essenziale.",
        "Ascolto attivamente prima di prendere decisioni importanti.",
        "Mi adatto rapidamente ai cambiamenti senza perdere di vista gli obiettivi."
    ]
    risposte_personali = {}
    risposte_questionario = {}

    with st.container(border=True):
        st.subheader("Informazioni personali")
        age = st.number_input("Età", min_value=10, max_value=90, value=18)
        st.caption("Età richiesta: tra 10 e 90 anni")
        gender = st.selectbox(
            "Sesso",
            ["Donna", "Uomo", "Preferisco non rispondere", "Altro"],
            index = None,  # Nessuna selezione iniziale
            placeholder = "Seleziona il tuo sesso"
        )

        # Spazio extra
        st.write("")

        # Professione
        profession_options = [
            "Lavoratore/Lavoratrice",
            "Disoccupato/a",
            "Casalingo/a",
            "Studente/studentessa",
            "Pensionato/a",
            "Altro"
        ]

        profession = st.selectbox(
            "Professione",
            profession_options,
            index=None,  # Nessuna selezione iniziale
            placeholder="Seleziona la tua professione"
        )

        if profession == "Altro":
            profession_other = st.text_input("Specifica la professione:", placeholder="Inserisci la tua professione")
            if profession_other.strip():
                profession = f"Altro: {profession_other.strip()}"
                st.success(f"Professione registrata: {profession_other.strip()}")

        st.write("")  # Spazio prima della prossima sezione

        st.markdown("""
        <style>
        div[data-testid="stRadio"] {
            margin-top: -25px !important;
        }
        div[data-testid="stRadio"] > div {
            margin-top: 5px !important;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown("""
        **Quanto frequentemente utilizzi i Large Language Models (LLM)?**  
        *Esempio di LLM : ChatGPT*
        """)

        llm_experience = st.radio(
            "Esperienza con LLM",
            ["Mai usati", "Raramente", "Qualche volta", "Spesso", "Molto Spesso"],
            index=None,
            horizontal=False,
            label_visibility="collapsed"
        )

    st.write("--------------")
    risposte_personali["eta"] = age
    risposte_personali["sesso"] = gender
    risposte_personali["professione"] = profession
    risposte_personali["esperienzaLLM"] = llm_experience

    # Form per le risposte
    with st.form("questionnaire_form"):

        st.subheader("Questionario sulla leadership")
        st.write(
            "Di seguito sono riportate 10 affermazioni. Per ciascuna, indica con quale frequenza ti riconosci in essa. ")
        st.write("""
            **Legenda:**
            - **0** : Mai
            - **1** : Raramente
            - **2** : Qualche volta
            - **3** : Spesso
            - **4** : Molto spesso
            """)

        st.write("")

        for i, question in enumerate(domande):
            st.write(f"{i + 1}. {question}")
            score = st.radio(f"Risposta domanda {i + 1}", [0, 1, 2, 3, 4], index=None, horizontal=True, key=f"q{i + 1}",
                             label_visibility="collapsed")
            risposte_questionario[i + 1] = score
            st.write("---")

        submitted = st.form_submit_button("Conferma e prosegui")

        if submitted:
            # Verifica che tutti i campi siano compilati
            if not all([age, gender and gender != "Seleziona il tuo sesso", profession and profession != "Seleziona la tua professione", llm_experience]):
                st.error("Compila tutti i campi delle informazioni personali prima di procedere.")
            elif None in risposte_questionario.values():
                st.error("Rispondi a tutte le domande del questionario prima di procedere.")
            else:
                st.session_state.risposte_personali = risposte_personali
                st.session_state.risposte_questionario = risposte_questionario

                # Calcola la media dei punteggi del questionario
                punteggi = list(risposte_questionario.values())
                media_punteggi = sum(punteggi) / len(punteggi) if punteggi else 0
                st.session_state.media_questionario = media_punteggi

                # Invia i punteggi del questionario al backend
                try:
                    # Invia al backend
                        response = requests.post(
                            "http://127.0.0.1:8000/submit_questionnaire_scores",
                            json={
                                "username": st.session_state.username,
                                "media_punteggi": media_punteggi
                            },
                            timeout=5
                        )
                        print(f"Media punteggi questionario: {media_punteggi}")
                        print(f"Modalità di intervento: {'accordo' if media_punteggi > 2 else 'disaccordo'}")

                        print(f"Età: {risposte_personali.get('eta', 'N/A')}")
                        print(f"Sesso: {risposte_personali.get('sesso', 'N/A')}")
                        print(f"Professione: {risposte_personali.get('professione', 'N/A')}")
                        print(f"Esperienza LLM: {risposte_personali.get('esperienzaLLM', 'N/A')}")

                except Exception as e:
                    print(f"Errore nell'invio dei punteggi del questionario: {e}")

                # Dopo aver inviato i punteggi, imposta anche la modalità
                try:
                    mode_response = requests.post(
                        "http://127.0.0.1:8000/set_intervention_mode",
                        json={
                            "username": st.session_state.username,
                            "media_punteggi": media_punteggi
                        },
                        timeout=5
                    )
                    if mode_response.status_code == 200:
                        mode_data = mode_response.json()
                except Exception as e:
                    print(f"Errore nell'impostazione della modalità: {e}")

                st.session_state.page += 1
                st.rerun()


    st.components.v1.html("""
            <script>
                window.parent.document.getElementById('top').scrollIntoView({behavior: 'instant'});
            </script>
            """, height=0)

# Page 2: Draggable List ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
elif st.session_state.page == 3:
    if st.session_state.get('force_refresh', False):
        st.session_state.force_refresh = False
        st.rerun()
    st.markdown("<div id='top'></div>", unsafe_allow_html=True)
    st.title("Classifica individuale")
    st.write("-----------------")
    st.subheader("Scenario iniziale:")
    st.write("Sei un membro di un equipaggio spaziale messo inizialmente in orbita per un rendez-vous"
             " con la navicella madre sulla superficie luminosa della luna. Tuttavia, a causa di un "
             "guasto meccanico, la tua navicella è stata costretta ad effettuare un atterraggio d'emergenza"
             " a 320 km circa dal punto prestabilito per l'incontro. Durante l'atterraggio le apparecchiature"
             " di bordo sono state danneggiate e, dal momento che la sopravvivenza dell’equipaggio dipende"
             " dal raggiungere la navicella madre, dovrai scegliere, tra le attrezzature disponibili, "
             "quelle essenziali per superare i 320 km che ti separano da essa. Qui sotto sono elencati "
             "15 oggetti rimasti intatti e non danneggiati durante l'atterraggio. Il tuo compito è "
             "di ordinarli in base alla loro importanza al fine di raggiungere con il tuo equipaggio"
             " il luogo del rendez-vous. Più collocherai un oggetto in alto, maggiore sarà la sua importanza.")
    st.write("----------------")
    st.write("Tieni premuto un oggetto e trascinalo per ordinarlo.")

    items = []

    if (st.session_state.user_list == []):
        items = [
            {"id": 1, "name": "Scatola di Fiammiferi"},
            {"id": 2, "name": "Concentrato Alimentare"},
            {"id": 3, "name": "Corda in nylon di 15 metri"},
            {"id": 4, "name": "Paracadute di seta"},
            {"id": 5, "name": "Unità di Riscaldamento Portatile"},
            {"id": 6, "name": "Due pistole calibro .45"},
            {"id": 7, "name": "Latte disidratato"},
            {"id": 8, "name": "Bombole di ossigeno di 45kg"},
            {"id": 9, "name": "Mappa delle stelle"},
            {"id": 10, "name": "Zattera di salvataggio autogonfiabile"},
            {"id": 11, "name": "Bussola Magnetica"},
            {"id": 12, "name": "20 litri d'acqua"},
            {"id": 13, "name": "Razzo di segnalazione"},
            {"id": 14, "name": "Cassa di pronto soccorso"},
            {"id": 15, "name": "Radiolina alimentata con energia solare"}
        ]
    elif (st.session_state.user_list != []):
        items = st.session_state.user_list

    # lista con interazione
    draggable_list = DraggableList(items, key="draggable_list")
    st.write("-----------")
    st.write(
        "Se hai terminato la classifica, clicca su 'Entra nella lobby' per continuare l'esperimento con altri partecipanti.")
    st.write("----------------")

    if st.button("Entra nella lobby", key="enter_lobby_button"):
        st.session_state.user_list = draggable_list
        st.session_state.previous_list_text = "\n \n ".join([item['name'] for item in st.session_state.user_list])
        st.session_state.page = 20
        st.rerun()
    st.components.v1.html("""
            <script>
                window.parent.document.getElementById('top').scrollIntoView({behavior: 'instant'});
            </script>
            """, height=0)
# -------------------------------------------------------------------------------------------------------------------------------------------------------------

# Lobby Utenti--------------------------------------------------------------------------------------------
elif (st.session_state.page == 20):
    st.title("Lobby utenti")

    show_backend_status()
    if not backend_is_available():
        st.stop()

    st_autorefresh(interval=1500, key="lobby_autorefresh")

    # Inizializza i placeholder per le informazioni
    connected_users_placeholder = st.empty()
    chat_status_placeholder = st.empty()
    debug_placeholder = st.empty()

    # Verifica dell'username
    if "valid" not in st.session_state or st.session_state.valid == "not valid":
        username = st.text_input("Inserire un username:", key="username_input")

        if username:  # Solo se l'utente ha inserito qualcosa
            clean_username = username.strip().replace(" ", "_").lower()
            # Verifica che non sia vuoto dopo la pulizia
            if not clean_username:
                st.warning("L'username non può essere vuoto o contenere solo spazi.")
            else:
                utenti_collegati = fetch_connected_users()
            utenti_collegati_lower = [u.lower() for u in utenti_collegati]

            if clean_username in utenti_collegati_lower:
                st.warning(f"Il nome utente '{clean_username}' è già utilizzato. Scegli un altro nome.")

            else:
                # Registra l'utente via REST API
                if register_user_rest(clean_username):
                    st.session_state.valid = "valid"
                    st.session_state.username = clean_username
                    st.success(f"Benvenuto, {clean_username}! Sei stato registrato nella lobby.")

                    if 'risposte_personali' in st.session_state:
                        try:
                            response = requests.post(
                                "http://127.0.0.1:8000/submit_demographics",
                                json={
                                    "username": clean_username,
                                    "demographics": st.session_state.risposte_personali
                                },
                                timeout=5
                            )
                        except Exception as e:
                            print(f"Errore nell'invio dei dati demografici: {e}")

                    # Inizializza le liste per le richieste di gruppo
                    st.session_state.group_members = []
                    st.session_state.pending_invites = []
                    st.session_state.creating_group = False


                    st.rerun()  # Ricarica solo dopo una registrazione riuscita
                else:
                    st.error("Errore durante la registrazione. Riprova.")

        # Pulsante per tornare indietro
        if st.button("Indietro"):
            st.session_state.page = 3
            st.rerun()

        # Ferma l'esecuzione qui fino a quando l'utente non è validato
        if "valid" not in st.session_state or st.session_state.valid == "not valid":
            st.stop()

    if "valid" in st.session_state and st.session_state.valid == "valid":

        from lobby_functions import setup_websocket_connection


        # Gestisce errori nella connessione WebSocket
        try:
            # Inizializza il WebSocket solo se non è già stato fatto
            if "ws_connected" not in st.session_state or not st.session_state.ws_connected:
                setup_websocket_connection(st.session_state.username)

        except Exception as e:
            print(f"Errore nell'inizializzazione WebSocket: {e}")


        # Gestione delle notifiche
        if "notifications" in st.session_state and st.session_state.notifications:
            for notification in st.session_state.notifications:
                if notification["type"] == "success":
                    st.success(notification["message"])
                elif notification["type"] == "info":
                    st.info(notification["message"])
                elif notification["type"] == "warning":
                    st.warning(notification["message"])
                elif notification["type"] == "error":
                    st.error(notification["message"])

            # Svuota le notifiche dopo averle mostrate
            st.session_state.notifications = []

        # Verifica se serve un refresh forzato della lista utenti
        if st.session_state.get("force_user_list_refresh", False):
            st.session_state.force_user_list_refresh = False
            st.rerun()

        # Se dovremmo passare alla pagina di chat
        if "go_to_chat" in st.session_state and st.session_state.go_to_chat:
            st.session_state.go_to_chat = False
            # Invia la lista precedente dell'utente al backend
            send_previous_list_to_backend()
            st.session_state.page = 21  # Pagina della chat
            st.rerun()


    # Codice per utente già registrato
    username = st.session_state.username

    # Ottiene gli utenti collegati
    utenti_collegati = fetch_connected_users()
    altri_utenti = [u for u in utenti_collegati if u != username]

    # Mostra gli utenti disponibili
    if altri_utenti:
        connected_users_placeholder.success(f"Utenti disponibili: {', '.join(altri_utenti)}")
    else:
        connected_users_placeholder.warning("Nessun altro utente connesso al momento. Attendi che qualcuno si colleghi.")

    # Verifica se l'utente è già in un gruppo
    group_id, members = check_group_status(username)
    if group_id:
        st.success(f"Sei già in un gruppo con: {', '.join([m for m in members if m != username])}")

        # Se il gruppo ha almeno 2 membri, può iniziare la chat
        if len(members) >= 2:
            if st.button("Vai alla chat di gruppo"):
                # Invia la lista precedente dell'utente al backend
                send_previous_list_to_backend()
                st.session_state.group_id = group_id
                st.session_state.group_members = members
                st.session_state.page = 21  # Pagina della chat
                st.rerun()
        else:
            st.info("In attesa che altri membri si uniscano al gruppo...")
    else:
        st.write("### Creazione gruppo di lavoro")

        # Mostra gruppo in formazione
        if st.session_state.group_members:
            st.write(f"**Membri del gruppo attuali:** {', '.join(st.session_state.group_members)}")

            # Mostra i membri in attesa di risposta
            if st.session_state.pending_invites:
                flat_pending_invites = []
                for invite in st.session_state.pending_invites:
                    if isinstance(invite, list):
                        flat_pending_invites.extend(invite)  # Se è una lista, estendila
                    else:
                        flat_pending_invites.append(str(invite))  # Assicura che sia una stringa

                st.write(f"**In attesa di risposta da:** {', '.join(flat_pending_invites)}")

            # Se il gruppo ha già il numero massimo di partecipanti o almeno 2 membri
            if len(st.session_state.group_members) >= 2:
                st.success(f"Il gruppo ha {len(st.session_state.group_members)} partecipanti.")

                # Pulsante per iniziare la chat
                if st.button("Inizia chat di gruppo"):
                    try:
                        # Crea un gruppo con i membri attuali
                        payload = {
                            "creator": username,
                            "members": st.session_state.group_members
                        }
                        response = requests.post(f"{BASE_URL}/create_group", json=payload)
                        if response.status_code == 200:
                            group_data = response.json()
                            st.session_state.group_id = group_data.get("group_id")
                            st.session_state.page = 21  # Pagina della chat
                            st.rerun()
                        else:
                            st.error(f"Errore nella creazione del gruppo: {response.status_code}")
                    except Exception as e:
                        st.error(f"Errore: {e}")

        # Selettore di utenti
        if altri_utenti and len(st.session_state.group_members) < 5:
            # Filtra gli utenti che non sono già nel gruppo o in attesa
            utenti_disponibili = [u for u in altri_utenti
                                if u not in st.session_state.group_members
                                and u not in st.session_state.pending_invites]

            if not utenti_disponibili:
                st.info("Non ci sono altri utenti disponibili da invitare.")
            else:
                selected_users = st.multiselect(
                    "Seleziona utenti da invitare al gruppo",
                    options=utenti_disponibili,
                    placeholder="Seleziona gli utenti..."
                )

                if selected_users:
                    # Mostra chiaramente chi è stato selezionato
                    st.success(f" Utenti selezionati: {', '.join(selected_users)}")
                    st.write("---")  # Separatore visivo

                    if st.button(f"Invita {len(selected_users)} utenti al gruppo", type="primary"):
                        success_count = 0
                        group_id = None

                        try:
                            # Invia singoli inviti a ciascun utente ma con lo stesso group_id
                            import time
                            import requests

                            # Genera un ID univoco per il gruppo
                            group_id = f"group_{username}_{int(time.time())}"

                            for to_user in selected_users:
                                response = requests.post(
                                    "http://127.0.0.1:8000/send_request",
                                    json={
                                        "from_user": username,
                                        "to_user": to_user,
                                        "is_group": True,
                                        "group_id": group_id
                                    },
                                    timeout=5
                                )

                                if response.status_code == 200:
                                    success_count += 1
                                else:
                                    print(f"Errore nell'invio dell'invito a {to_user}: {response.status_code}")

                            if success_count > 0:
                                st.success(f"Inviti inviati a {success_count}/{len(selected_users)} utenti!")
                                # Aggiorna la lista dei pending invites con stringhe individuali
                                for user in selected_users:
                                    st.session_state.pending_invites.append(str(user))
                                st.rerun()
                            else:
                                st.error("Nessun invito inviato con successo")
                        except Exception as e:
                            st.error(f"Errore nell'invio degli inviti: {str(e)}")
                else:
                    if not altri_utenti:
                        st.info("Nessun utente disponibile al momento per creare un gruppo.")
                    elif len(st.session_state.group_members) >= 5:
                        st.warning("Hai raggiunto il numero massimo di membri nel gruppo.")

    # Contenitore per visualizzare le richieste ricevute
    st.write("### Richieste ricevute")
    try:
        response = requests.get(f"http://127.0.0.1:8000/check_pending_requests/{username}", timeout=3)
        if response is None:
            st.warning("Backend non disponibile per verificare le richieste")
        elif response and response.status_code == 200:
            data = response.json() if response.text else {}
            pending_requests = data.get("pending_requests", []) if data else []


            if pending_requests:
                st.success(f"Hai {len(pending_requests)} richieste in attesa")
                for req in pending_requests:
                    if req:
                        from_user = req.get("from_user")
                        req_id = req.get("request_id")
                        is_group = req.get("is_group", False)  # Verifica se è una richiesta di gruppo
                        group_id = req.get("group_id")  # Per richieste di gruppo

                        if is_group:
                            st.write(f"Richiesta per unirti a un gruppo creato da: **{from_user}**")
                        else:
                            st.write(f"Richiesta di chat da: **{from_user}**")

                        if st.button("Accetta", key=f"accept_{req_id}"):
                            try:
                                # Visualizza un messaggio di attesa
                                accept_placeholder = st.empty()
                                accept_placeholder.info("Accettazione in corso...")

                                # Ottiene il group_id se presente
                                group_id = req.get("group_id")

                                response = requests.post(
                                    f"http://127.0.0.1:8000/response_request",
                                    json={
                                        "request_id": req_id,
                                        "from_user": from_user,
                                        "to_user": st.session_state.username,
                                        "response": "accept",
                                        "group_id": group_id  # Include il group_id se presente
                                    },
                                    timeout=10  # Aumenta il timeout per dare tempo al server di processare
                                )

                                if response is None:
                                    accept_placeholder.error("Backend non disponibile per accettare la richiesta")
                                elif response.status_code == 200:
                                    data = response.json()
                                    accept_placeholder.success(
                                        f"Hai accettato {'invito al gruppo' if is_group else 'la richiesta di chat'} da {from_user}")

                                    # Se è un gruppo e il gruppo è stato creato completamente
                                    if is_group and data.get("all_accepted", False):
                                        st.session_state.group_id = data.get("group_id")

                                        # Carica i membri del gruppo
                                        group_response = requests.get(
                                            f"http://127.0.0.1:8000/get_group/{st.session_state.username}")
                                        if group_response.status_code == 200:
                                            group_data = group_response.json()
                                            st.session_state.group_members = group_data.get("members", [])

                                        # Aspetta un momento per mostrare il messaggio
                                        time.sleep(1)
                                        st.session_state.page = 21  # Pagina della chat

                                    # Per chat 1:1
                                    elif not is_group:
                                        st.session_state.partner = from_user
                                        time.sleep(1)
                                        st.session_state.page = 21  # Pagina della chat

                                    st.rerun()
                                else:
                                    # Gestione migliorata degli errori
                                    error_message = "Errore sconosciuto"
                                    try:
                                        error_data = response.json()
                                        if isinstance(error_data, dict) and "message" in error_data:
                                            error_message = error_data["message"]
                                        elif isinstance(error_data, dict) and "detail" in error_data:
                                            error_message = error_data["detail"]
                                        else:
                                            error_message = str(error_data)
                                    except:
                                        # Se non è JSON, usa il testo della risposta
                                        error_message = response.text if response.text else f"Codice errore: {response.status_code}"

                                    accept_placeholder.error(f"Errore nell'accettazione: {error_message}")
                                    print(f"Dettagli errore completi: {response.text}")
                            except Exception as e:
                                st.error(f"Errore: {str(e)}")
                                print(f"Eccezione durante l'accettazione: {str(e)}")
                                import traceback

                                print(traceback.format_exc())

            else:
                st.info("Nessuna richiesta in attesa.")
        else:
            status_code = response.status_code if response else "N/A"
            st.warning(f"Errore nel controllo delle richieste: status code {status_code}")
    except Exception as e:
        st.error(f"Errore nel controllo delle richieste: {str(e)}")


    # Pulsante per aggiornare manualmente
    if st.button("Aggiorna", key="refresh_button"):
        st.rerun()

    st.markdown("""
    <script>
    function refreshPage() {
        setTimeout(function () {
            window.parent.document.querySelector('[data-testid="stRefreshButton"]').click();
        }, 5000);  // Aggiorna ogni 5 secondi
    }
    refreshPage();
    </script>
    """, unsafe_allow_html=True)


# Pagina di ranking collaborativo-----------------------------------------------------------------------------------
elif st.session_state.page == 21:
    st.markdown("<div id='top'></div>", unsafe_allow_html=True)
    st.title("Ranking collaborativo con LLM")

    if not show_backend_status():
        st.stop()

    st.markdown("""
    <style>
        /* Forza l'allineamento verticale delle colonne */
        .stColumn > div {
            padding-top: 0rem !important;
            margin-top: 0rem !important;
        }

        /* Assicura che gli header abbiano la stessa altezza */
        .stColumn h2 {
            margin-top: 0rem !important;
            margin-bottom: 1rem !important;
            height: 2.5rem;
            line-height: 2.5rem;
        }

        /* Rimuovi spazi extra dai componenti */
        .stColumn .element-container {
            margin-bottom: 0.5rem !important;
        }
    </style>
    """, unsafe_allow_html=True)


    if 'force_rerun' in st.session_state and st.session_state.force_rerun:
        st.session_state.force_rerun = False
        time.sleep(0.1)  # Piccola pausa per dare tempo alle operazioni di completarsi
        st.rerun()

    from lobby_functions import setup_websocket_connection

    current_time = time.time()
    if 'last_ws_check' not in st.session_state:
        st.session_state.last_ws_check = current_time

    # Forza una nuova connessione WebSocket se non attiva
    if "ws_connection_active" not in st.session_state or not st.session_state.ws_connection_active:
        print("Inizializzazione WebSocket all'avvio della pagina")
        setup_websocket_connection(st.session_state.username)

    if not st.session_state.get('dragging_active', False):
        st_autorefresh(interval=3000, key="page_autorefresh")


    # Controllo periodico per sincronizzazione
    if 'last_sync_check' not in st.session_state:
        st.session_state.last_sync_check = time.time()

    # Esegue sincronizzazione ogni 10 secondi
    current_time = time.time()
    if current_time - st.session_state.last_sync_check > 2:
        # Utilizza l'ID del gruppo dalla session_state
        current_group_id = None
        if 'group_id' in st.session_state:
            current_group_id = st.session_state.group_id
        elif 'partner' in st.session_state:
            # Retrocompatibilità con il sistema a 2 utenti
            user1, user2 = sorted([st.session_state.username, st.session_state.partner])
            current_group_id = f"{user1}-{user2}"

        if current_group_id:

            try:
                # Richiede la lista aggiornata dal server
                response = requests.get(f"{BASE_URL}/get_shared_list/{current_group_id}?t={int(current_time)}",
                                        timeout=3)

                if response.status_code == 200:
                    server_data = response.json()
                    server_list = server_data.get("lista", [])

                    if server_list and len(server_list) > 0:
                        # Controlla se la lista del server è più recente
                        server_timestamp = 0
                        for item in server_list:
                            if 'last_modified' in item and item['last_modified'] > server_timestamp:
                                server_timestamp = item['last_modified']

                        # Trova il timestamp più recente nella lista locale
                        local_timestamp = 0
                        if 'previous_list' in st.session_state and st.session_state.previous_list:
                            for item in st.session_state.previous_list:
                                if 'last_modified' in item and item['last_modified'] > local_timestamp:
                                    local_timestamp = item['last_modified']

                        if server_timestamp > local_timestamp:
                            st.session_state.previous_list = server_list
                            st.session_state.force_rerun = True
            except Exception as e:
                print(f"Errore nel controllo periodico: {e}")
        else:
            print("Impossibile eseguire il controllo periodico: ID gruppo non disponibile")

        # Aggiorna il timestamp di ultimo controllo
        st.session_state.last_sync_check = current_time

    username = st.session_state.username

    # Determina l'ID del gruppo e i membri
    group_id = None
    group_members = []

    if 'group_id' in st.session_state:
        # Se si ha già un ID gruppo salvato, lo usa
        group_id = st.session_state.group_id
        try:
            response = requests.get(f"{BASE_URL}/get_group/{username}", timeout=3)
            if response is None:
                # Usa i dati dalla sessione
                if 'group_members' in st.session_state:
                    group_members = st.session_state.group_members
            elif response.status_code == 200:
                data = response.json()
                group_members = data.get('members', [])
                # Assicura che siano tutti stringhe e unici
                group_members = [str(m) for m in group_members if m]
                group_members = list(set(group_members))
                st.session_state.group_members = group_members
            else:
                # Fallback all'altro endpoint
                response = requests.get(f"{BASE_URL}/get_group/{username}", timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('group_id') == group_id:
                        group_members = data.get('members', [])
                        st.session_state.group_members = group_members
        except Exception as e:
            print(f"Errore nel recupero dei membri del gruppo: {e}")
            # Fallback alla sessione
            if 'group_members' in st.session_state:
                group_members = st.session_state.group_members

    elif 'partner' in st.session_state:
        # Retrocompatibilità con il sistema a 2 utenti
        user1, user2 = sorted([username, st.session_state.partner])
        group_id = f"{user1}-{user2}"
        group_members = [user1, user2]
        st.session_state.group_id = group_id
        st.session_state.group_members = group_members
    else:
        # Se non si hanno informazioni sul gruppo, le recupera
        group_id, members = check_group_status(username)
        if group_id and members:
            st.session_state.group_id = group_id
            st.session_state.group_members = members
            group_members = members

    # Se non si ha ancora un gruppo, mostra un messaggio e torna alla lobby
    if not group_id or not group_members:
        st.error("Non sei connesso a nessun gruppo. Tornando alla lobby...")
        st.session_state.page = 20
        st.rerun()

    group_members = [str(m) for m in group_members if m]
    group_members = list(set(group_members))  # Rimuove duplicati

    # Filtra l'utente corrente dai membri del gruppo
    other_members = [m for m in group_members if m != username]
    members_str = ", ".join(other_members)

    # Ottiene la modalità se non è già impostata
    if st.session_state.modalita == "":
        modalita = get_modalita(group_id, username)
        st.session_state.modalita = modalita

    # Messaggio iniziale con informazioni sul gruppo
    st.write(
        f"In questo momento sei collegato con gli utenti {members_str}. "
        f"Qui sotto troverai una nuova lista (a sinistra) e la classifica "
        f"che hai stilato individualmente (a destra). La lista di sinistra è "
        f"condivisa con tutti gli utenti del gruppo e le modifiche saranno visibili"
        f" a tutti. L'obiettivo è quello di collaborare per creare la classifica migliore"
        f" (lo scenario è sempre quello del passo precedente: fate parte di un equipaggio"
        f" sulla luna e dovete raggiungere l'astronave madre a 320km di distanza). "
        f"Dovrai comunicare con gli altri utilizzando la chat. Durante la conversazione "
        f"nella chat, interverrà il Large Language Model per dare la propria opinione, "
        f"potete usare le risposte che fornirà come aiuto.")
    st.write("-----------")

    # Controlla se la lista è bloccata per mostrare l'avviso appropriato
    list_is_locked_for_button = False
    if 'group_id' in st.session_state:
        try:
            response = requests.get(f"{BASE_URL}/check_list_locked/{st.session_state.group_id}")
            if response.status_code == 200:
                lock_status = response.json()
                list_is_locked_for_button = lock_status.get("locked", False)
        except Exception as e:
            print(f"Errore nel controllo dello stato di blocco per pulsante: {e}")

    # Barra di stato globale per il lock
    lock_status_container = st.container()
    with lock_status_container:
        if st.session_state.list_locked and not st.session_state.user_is_editing and not list_is_locked_for_button:
            st.error(f" **{st.session_state.locked_by_user}** sta modificando la lista. Attendi il tuo turno.")
        elif st.session_state.user_is_editing:
            col_status1, col_status2 = st.columns([3, 1])
            with col_status1:
                st.success("️ **Stai modificando la lista.** Trascina gli elementi per riordinarli.")
            with col_status2:
                if st.button(" Salva modifiche", key="save_changes_btn"):
                    # Salva e rilascia lock
                    if group_id:
                        success = submit_list_update(group_id, st.session_state.previous_list)
                        if success:
                            release_editing_lock(group_id, st.session_state.username)
                            st.success("Modifiche salvate!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Errore nel salvataggio")
        elif not list_is_locked_for_button:
            col_info1, col_info2 = st.columns([3, 1])
            with col_info1:
                st.info(" Clicca 'Inizia modifica' per modificare la lista collaborativa")
            with col_info2:
                if st.button("️ Inizia modifica", key="start_edit_btn"):
                    if request_editing_lock(group_id, st.session_state.username):
                        st.rerun()

    st.write("---")

    # Layout della pagina con due colonne
    colonna_sx, spazio, colonna_dx = st.columns([30, 10, 30])

    # Mostra la chatroom
    chatroom()

    # Usa la lista già presente in sessione se disponibile
    if 'previous_list' in st.session_state:
        new_list = st.session_state.previous_list
    else:
        # Inizializza con la lista predefinita se non c'è niente in sessione
        new_list = items.copy()  # Assicura che 'items' sia definito all'inizio del file
        # Opzionalmente, sincronizza con il server
        try:
            # Prepara il payload per inviare la lista iniziale
            timestamp = int(time.time() * 1000)
            for i, item in enumerate(new_list):
                item['order'] = i
                item['last_modified'] = timestamp

            # Invia la lista predefinita al server
            payload = {
                "group_id": group_id,
                "username": st.session_state.username,
                "list": new_list,
                "timestamp": timestamp,
                "changed": True
            }

            response = requests.post(
                "http://127.0.0.1:8000/sync_list",
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=5
            )

            if response.status_code == 200:
                print(f"Lista predefinita inviata al server per il gruppo {group_id}")
                st.session_state.previous_list = new_list
            else:
                print(f"Errore nell'invio della lista predefinita: {response.status_code}")
                # Comunque imposta la lista localmente
                st.session_state.previous_list = new_list
        except Exception as e:
            print(f"Errore di connessione: {e}")
            # In caso di errore, imposta comunque la lista localmente
            st.session_state.previous_list = new_list

    # Aggiorna la lista in session_state solo se ha ricevuto una lista valida
    if new_list:
        if 'previous_list' not in st.session_state or new_list != st.session_state.previous_list:
            print(f"Aggiornamento della lista nella sessione con {len(new_list)} elementi")
            st.session_state.previous_list = new_list
    elif 'previous_list' not in st.session_state or st.session_state.previous_list is None:
        # Fallback alla lista predefinita se necessario
        st.session_state.previous_list = items.copy()

    # Controllo per lista bloccata
    if 'list_locked' not in st.session_state:
        st.session_state.list_locked = False

    # Controlla se la lista è bloccata
    if 'group_id' in st.session_state:
        try:
            response = requests.get(f"{BASE_URL}/check_list_locked/{st.session_state.group_id}")
            if response.status_code == 200:
                lock_status = response.json()
                if lock_status["locked"]:
                    st.session_state.list_locked = True
                    st.session_state.locked_by = lock_status["locked_by"]
        except Exception as e:
            print(f"Errore nel controllo dello stato di blocco: {e}")

    with colonna_sx:
        st.header("Lista collaborativa")

        # Placeholder per notifiche
        notification_area = st.empty()

        # Controllo dello stato di blocco della lista (sia dal server che dallo stato locale)
        list_is_locked = False
        locked_by_user = ""

        # Prima controlla lo stato locale (per aggiornamenti WebSocket)
        if ('group_id' in st.session_state and
                hasattr(st.session_state, 'list_locked') and
                isinstance(st.session_state.list_locked, dict) and
                st.session_state.group_id in st.session_state.list_locked):

            local_lock = st.session_state.list_locked[st.session_state.group_id]
            if local_lock.get("locked", False):
                list_is_locked = True
                locked_by_user = local_lock.get("locked_by", "Sconosciuto")
                st.write("**DEBUG - Blocco rilevato dallo stato locale WebSocket**")

        # Se non bloccato localmente, controlla il server
        if not list_is_locked and 'group_id' in st.session_state:
            try:
                check_url = f"{BASE_URL}/check_list_locked/{st.session_state.group_id}"

                response = requests.get(check_url)

                if response.status_code == 200:
                    lock_status = response.json()

                    if lock_status.get("locked", False):
                        list_is_locked = True
                        locked_by_user = lock_status.get("locked_by", "Sconosciuto")
                else:
                    st.warning(f"Errore nel controllo blocco: {response.status_code}")
                    st.write(f"**DEBUG - Risposta errore:** {response.text}")
            except Exception as e:
                st.error(f"Errore nella verifica blocco: {e}")
                print(f"Errore nel controllo dello stato di blocco: {e}")


        # Controlla se la lista è bloccata
        if st.session_state.list_locked and not st.session_state.user_is_editing and not list_is_locked_for_button:
            # Lista bloccata - mostra interfaccia disabilitata
            st.warning(f" {st.session_state.locked_by_user} sta modificando la lista...")

            # Mostra la lista in modalità read-only
            for i, item in enumerate(st.session_state.previous_list):
                st.text(f"{i + 1}. {item['name']}")

        # Verifica e inizializza la lista
        if 'previous_list' not in st.session_state or not st.session_state.previous_list:
            print("DEBUG - Inizializzo lista predefinita")
            default_items = [
                {"id": 1, "name": "Scatola di Fiammiferi"},
                {"id": 2, "name": "Concentrato Alimentare"},
                {"id": 3, "name": "Corda in nylon di 15 metri"},
                {"id": 4, "name": "Paracadute di seta"},
                {"id": 5, "name": "Unità di Riscaldamento Portatile"},
                {"id": 6, "name": "Due pistole calibro .45"},
                {"id": 7, "name": "Latte disidratato"},
                {"id": 8, "name": "Bombole di ossigeno di 45kg"},
                {"id": 9, "name": "Mappa delle stelle"},
                {"id": 10, "name": "Zattera di salvataggio autogonfiabile"},
                {"id": 11, "name": "Bussola Magnetica"},
                {"id": 12, "name": "20 litri d'acqua"},
                {"id": 13, "name": "Razzo di segnalazione"},
                {"id": 14, "name": "Cassa di pronto soccorso"},
                {"id": 15, "name": "Radiolina alimentata con energia solare"}
            ]
            st.session_state.previous_list = default_items
            st.success(" Lista inizializzata con valori predefiniti")

        # Se la lista è bloccata, mostra solo la visualizzazione read-only
        if list_is_locked:
            # Crea il testo della lista bloccata nello stesso formato di quella individuale
            lista_bloccata_text = "\n \n ".join([item['name'] for item in st.session_state.previous_list])

            # Mostra la lista
            st.text_area("Lista collaborativa (bloccata)", value=lista_bloccata_text, height=680,
                         key="collaborative_list_locked", label_visibility="collapsed")

            # Messaggio di stato
            st.info(f" LISTA BLOCCATA DA: {locked_by_user}")
            st.markdown("*Questa classifica è stata finalizzata e non può più essere modificata.*")


        else:
            # Lista non bloccata - permette modifiche tramite DraggableList
            try:
                # Genera una chiave unica che include l'hash della lista corrente
                import hashlib

                list_hash = hashlib.md5(
                    str([item['id'] for item in st.session_state.previous_list]).encode()).hexdigest()[
                            :8]
                dynamic_key = f"drag_{group_id}_{list_hash}" if group_id else f"drag_no_group_{list_hash}"

                current_list = st.session_state.previous_list

                # Disabilita temporaneamente l'autorefresh durante l'interazione
                if 'dragging_active' not in st.session_state:
                    st.session_state.dragging_active = False

                # Mostra la lista, ma con interattività condizionale
                if st.session_state.list_locked and not st.session_state.user_is_editing:
                    locked_list_text = "\n \n ".join([item['name'] for item in current_list])

                    # Styling per la lista bloccata
                    st.markdown("""
                                <style>
                                div[data-testid="stTextArea"] textarea[aria-label="Lista bloccata"][disabled] {
                                    background-color: #ffe6e6 !important;
                                    border: 2px solid #ff9999 !important;
                                    border-radius: 8px !important;
                                    opacity: 1 !important;
                                }
                                </style>
                                """, unsafe_allow_html=True)

                    st.text_area(
                        "Lista bloccata",
                        value=f" {st.session_state.locked_by_user} sta modificando...\n\n{locked_list_text}",
                        height=680,
                        key="locked_list_display",
                        label_visibility="collapsed",
                        disabled=True
                    )


                elif st.session_state.user_is_editing:

                    # DraggableList con chiave dinamica
                    reordered_list = DraggableList(current_list, key=dynamic_key)

                    if reordered_list and len(reordered_list) > 0:

                        reordered_ids = [item['id'] for item in reordered_list]

                        # Verifica se c'è stata una modifica
                        original_ids = [item['id'] for item in current_list]
                        if reordered_ids != original_ids:
                            st.info(f"**Modifica rilevata usa 'Salva modifiche' per confermare!**")

                            # Aggiorna immediatamente la session_state
                            st.session_state.previous_list = copy.deepcopy(reordered_list)
                            st.session_state.dragging_active = True  # Segnala che è in corso un'operazione di drag

                            # Salva al server con debouncing
                            if group_id:
                                st.info(" Salvando modifiche...")
                                success = submit_list_update(group_id, reordered_list)
                                if success:
                                    st.success(" Modifiche salvate!")
                                    st.session_state.dragging_active = False
                                    # Forza un piccolo delay prima del prossimo refresh
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error(" Errore nel salvataggio")
                else:
                    # Mostra la lista collaborativa nello stesso stile di quella individuale
                    lista_collaborativa_text = "\n \n ".join([item['name'] for item in current_list])

                    if st.session_state.user_is_editing:
                        # Quando l'utente sta modificando, mostra comunque in text_area ma con nota
                        st.text_area("Lista collaborativa (in modifica)", value=lista_collaborativa_text, height=680,
                                     key="collaborative_list_editing", label_visibility="collapsed")
                        st.warning(" **Modalità editing attiva** - Le modifiche ora avvengono tramite chat con l'IA")
                    else:
                        # Vista normale - stesso stile della lista individuale
                        st.text_area("Lista collaborativa", value=lista_collaborativa_text, height=680,
                                     key="collaborative_list_display", label_visibility="collapsed")


            except Exception as e:
                st.error(f" Errore nel DraggableList: {str(e)}")
                import traceback

                st.code(traceback.format_exc())

    # Continua con la sezione del pulsante
    st.components.v1.html("""
                    <script>
                        window.parent.document.getElementById('top').scrollIntoView({behavior: 'instant'});
                    </script>
                    """, height=0)

    with colonna_dx:
        st.header("Lista individuale:")
        if 'previous_list_text_saved' not in st.session_state:
            st.session_state.previous_list_text_saved = st.session_state.previous_list_text

        st.text_area("Lista individuale", value=st.session_state.previous_list_text, height=680,
                     key="individual_list_display", label_visibility="collapsed")


    st.info(
        "**Nota importante:** Quando tutti gli utenti del gruppo si trovano d'accordo sulla classifica collaborativa, è possibile cliccare il pulsante 'Conferma e prosegui' per continuare con l'esperimento.")

    if not list_is_locked_for_button:
        st.warning(
            " **Attenzione:** Cliccando 'Conferma e prosegui' la lista verrà bloccata per tutti i membri del gruppo e non sarà più possibile modificarla.")

    st.write("")
    st.write("----------------------------")

    # Pulsante per confermare e procedere
    if st.button("Conferma e prosegui"):

        # Se la lista non è ancora bloccata
        if not list_is_locked_for_button and 'group_id' in st.session_state:
            try:
                lock_payload = {
                    "group_id": st.session_state.group_id,
                    "username": st.session_state.username
                }

                lock_response = requests.post(f"{BASE_URL}/lock_shared_list", json=lock_payload)

                if lock_response.status_code == 200:
                    response_data = lock_response.json()
                    st.success(" Lista bloccata con successo per tutti i membri del gruppo!")
                    time.sleep(2)  # Pausa per mostrare il messaggio
                else:
                    st.error(f" Errore nel blocco della lista: {lock_response.status_code}")
                    st.write(f"**DEBUG - Errore completo:** {lock_response.text}")
            except Exception as e:
                st.error(f" Errore nel blocco della lista: {e}")
                st.write(f"**DEBUG - Eccezione:** {str(e)}")
                import traceback

                st.code(traceback.format_exc())
        else:
            st.write("**DEBUG - Lista già bloccata o group_id mancante**")

        # Notifica tutti i membri del gruppo che questo utente ha confermato
        send_continua_message(st.session_state.group_id, st.session_state.username)

        st.session_state.updated_list = st.session_state.previous_list

        st.session_state.page = 5
        st.rerun()

    # autorefresh
    st_autorefresh(interval=2000, key="list_autorefresh")

    # JavaScript per forzare il refresh
    st.markdown("""
    <script>
    function forceRefresh() {
        setTimeout(function() {
            window.parent.document.querySelector('[data-testid="stRefreshButton"]').click();
        }, 3000);  // Riprova ogni 3 secondi
    }
    forceRefresh();
    </script>
    """, unsafe_allow_html=True)

# Page 3: risposta ai ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
elif st.session_state.page == 4:

    # Reindirizza alla lobby se qualcuno tenta di accedere a questa pagina
    st.session_state.page = 20
    st.rerun()


# Nuova pagina 5: Questionario post-esperimento
elif st.session_state.page == 5:
    st.markdown("<div id='top'></div>", unsafe_allow_html=True)

    st.title("Valutazione post-esperimento")
    show_backend_status()
    st.write("------------------")

    domande_post = [
        "Mi sono sentito/a coinvolto/a attivamente nella conversazione durante l'esperimento.",
        "Il gruppo ha collaborato in modo efficace per raggiungere un obiettivo comune.",
        "L'intelligenza artificiale ha contribuito in modo utile alla discussione.",
        "Le interazioni con l'IA sono state chiare e comprensibili.",
        "Mi sono sentito/a ascoltato/a e rispettato/a dagli altri partecipanti.",
        "Le istruzioni e gli obiettivi dell'esperimento erano chiari.",
        "Rifarei volentieri un'esperienza simile in futuro.",
        "L'esperimento mi ha fatto riflettere su come si può collaborare con un'IA.",
        "Ho trovato l'esperienza interessante e stimolante.",
        "In generale, valuto l'esperienza come positiva."
    ]

    risposte_post_questionario = {}

    # Form per le risposte
    with st.form("post_questionnaire_form"):
        st.subheader("Valutazione post-esperimento")
        st.write(
            "Di seguito sono riportate 10 affermazioni sulla tua esperienza. Per ciascuna, indica il tuo livello di accordo.")
        st.write("""
            **Legenda:**
            - **0**: Per niente d'accordo
            - **1**: Poco d'accordo
            - **2**: Né d'accordo né in disaccordo
            - **3**: Abbastanza d'accordo
            - **4**: Completamente d'accordo
            """)

        st.write("")

        for i, question in enumerate(domande_post):
            st.write(f"{i + 1}. {question}")
            score = st.radio(f"Risposta post-domanda {i + 1}", [0, 1, 2, 3, 4], index=None, horizontal=True,
                             key=f"post_q{i + 1}",
                             label_visibility="collapsed")
            risposte_post_questionario[i + 1] = score
            st.write("---")

        submitted = st.form_submit_button("Conferma e visualizza risultati")

        if submitted:
            # Verifica che tutte le domande abbiano una risposta
            if None in risposte_post_questionario.values():
                st.error("Rispondi a tutte le domande prima di procedere.")
            else:
                st.session_state.risposte_post_questionario = risposte_post_questionario

                # Calcola la media del feedback individuale
                post_scores = list(risposte_post_questionario.values())
                individual_average_feedback = sum(post_scores) / len(post_scores) if post_scores else 0

                username = st.session_state.username
                print(f"[{username}] Media feedback individuale: {individual_average_feedback:.1f}")

                # Salva le risposte nel database
                if st.session_state.alone == True:
                    engine = get_engine_alone()
                else:
                    engine = get_engine()

                session = get_session(engine)
                insert_user_post_questions_to_db(session, risposte_post_questionario)

                # Notifica il backend che questo utente ha completato il questionario
                if not st.session_state.alone and 'group_id' in st.session_state:
                    try:
                        # Prepara i dati del feedback per inviarli al backend
                        short_keys = [
                            "Coinvolgimento personale",
                            "Collaborazione di gruppo",
                            "Utilità dell'IA",
                            "Chiarezza interazioni IA",
                            "Rispetto tra partecipanti",
                            "Chiarezza obiettivi",
                            "Ripeterei l'esperienza",
                            "Riflessione su IA-persona",
                            "Esperienza stimolante",
                            "Valutazione generale"
                        ]

                        # Invia anche i dati del feedback
                        feedback_data = {}
                        for i, _ in enumerate(short_keys):
                                feedback_data[short_keys[i]] = risposte_post_questionario[i + 1]

                        # Calcola la media del feedback
                        feedback_values = list(risposte_post_questionario.values())
                        average_feedback = sum(feedback_values) / len(feedback_values) if feedback_values else 0

                        # Notifica al backend che l'utente ha completato il questionario
                        response = requests.post(
                            f"{BASE_URL}/update_questionnaire_status",
                            json={
                                "group_id": st.session_state.group_id,
                                "username": st.session_state.username,
                                "feedback_data": feedback_data,
                                "average_feedback": average_feedback
                            },
                            timeout=5
                        )

                        if response.status_code == 200:
                            st.success("Questionario completato con successo")

                            # Invia anche il feedback completo separatamente
                            feedback_response = requests.post(
                                f"{BASE_URL}/submit_user_feedback",
                                json={
                                    "group_id": st.session_state.group_id,
                                    "username": st.session_state.username,
                                    "feedback": feedback_data,
                                    "average_feedback": average_feedback
                                },
                                timeout=5
                            )

                            if feedback_response.status_code != 200:
                                st.warning(f"Avviso: il feedback potrebbe non essere stato registrato correttamente")
                        else:
                            st.warning(f"Avviso: stato di completamento potrebbe non essere stato registrato correttamente")

                    except Exception as e:
                        st.error(f"Errore nell'aggiornamento dello stato del questionario: {e}")
                        import traceback
                        st.error(traceback.format_exc())

                # Passa alla pagina di analisi risultati
                st.session_state.page = 6
                st.rerun()

    st.components.v1.html("""
        <script>
            window.parent.document.getElementById('top').scrollIntoView({behavior: 'instant'});
        </script>
        """, height=0)

# Page 5: Analisi Risultati ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
elif st.session_state.page == 6:
    show_backend_status()

    # Verifica se tutti hanno completato il questionario
    if not st.session_state.alone and 'group_id' in st.session_state:
        try:
            # Controlla se tutti hanno completato
            group_id = st.session_state.group_id
            username = st.session_state.username

            response = requests.get(f"{BASE_URL}/check_questionnaire_status/{group_id}", timeout=5)

            if response.status_code == 200:
                data = response.json()
                completed_users = data.get("completed_users", [])
                all_users = data.get("all_users", [])
                all_completed = data.get("all_completed", False)

                # Se non tutti hanno completato, mostra schermata di attesa
                if not all_completed:
                    st.title("In attesa che tutti completino il questionario")

                    st.write("Stato completamento:")
                    for user in all_users:
                        if user in completed_users:
                            st.success(f"✅ {user} ha completato il questionario")
                        else:
                            st.warning(f"⏳ {user} non ha ancora completato il questionario")

                    st.info(
                        "Stiamo aspettando che tutti i membri del gruppo completino il questionario post-esperimento. "
                        "Questa pagina si aggiornerà automaticamente quando tutti avranno terminato.")

                    # Aggiunge un pulsante di aggiornamento manuale
                    if st.button("Aggiorna stato"):
                        st.rerun()

                    # Aggiorna automaticamente la pagina
                    st_autorefresh(interval=5000, key="waiting_refresh")
                    st.stop()  # Interrompe l'esecuzione fino a quando tutti non hanno completato

                # Controlla se tutti hanno completato
                feedback_response = requests.get(f"{BASE_URL}/get_group_feedback/{group_id}", timeout=5)

                if feedback_response.status_code == 200:
                    feedback_data_response = feedback_response.json()

                    if feedback_data_response.get("status") == "success":
                        # Usa i dati aggregati dal server
                        feedback_data = feedback_data_response.get("feedback", {})
                        average_feedback = feedback_data_response.get("average_feedback", 0)
                    else:
                        print(f"Errore nei dati di feedback: {feedback_data_response.get('message', 'Nessun messaggio')}")

                        # Fallback ai dati individuali se non ci sono dati aggregati
                        st.warning(
                            "Dati aggregati non disponibili. Verranno mostrati solo i tuoi risultati individuali.")
                        if 'risposte_post_questionario' in st.session_state:
                            post_scores = list(st.session_state.risposte_post_questionario.values())
                            average_feedback = sum(post_scores) / len(post_scores) if post_scores else 0
                            # Crea un dizionario per mappare le domande alle risposte
                            short_keys = [
                                "Coinvolgimento personale",
                                "Collaborazione di gruppo",
                                "Utilità dell'IA",
                                "Chiarezza interazioni IA",
                                "Rispetto tra partecipanti",
                                "Chiarezza obiettivi",
                                "Ripeterei l'esperienza",
                                "Riflessione su IA-persona",
                                "Esperienza stimolante",
                                "Valutazione generale"
                            ]
                            feedback_data = {}
                            for i, _ in enumerate(short_keys):
                                # i+1 perché le chiavi del dizionario partono da 1
                                feedback_data[short_keys[i]] = st.session_state.risposte_post_questionario.get(i + 1, 0)
                else:
                    st.warning(f"Errore nella verifica del completamento: {feedback_response.status_code}")
                    # Usa i dati individuali
                    if 'risposte_post_questionario' in st.session_state:
                        post_scores = list(st.session_state.risposte_post_questionario.values())
                        average_feedback = sum(post_scores) / len(post_scores) if post_scores else 0

                        # Crea un dizionario per mappare le domande alle risposte
                        short_keys = [
                            "Coinvolgimento personale",
                            "Collaborazione di gruppo",
                            "Utilità dell'IA",
                            "Chiarezza interazioni IA",
                            "Rispetto tra partecipanti",
                            "Chiarezza obiettivi",
                            "Ripeterei l'esperienza",
                            "Riflessione su IA-persona",
                            "Esperienza stimolante",
                            "Valutazione generale"
                        ]
                        feedback_data = {}
                        for i, _ in enumerate(short_keys):
                            # i+1 perché le chiavi del dizionario partono da 1
                            feedback_data[short_keys[i]] = st.session_state.risposte_post_questionario.get(i + 1, 0)
        except Exception as e:
            st.warning(f"Impossibile verificare lo stato di completamento del gruppo: {e}")
            import traceback

            st.error(traceback.format_exc())

            # Calcolo medie e statistiche del questionario post-esperimento
            if 'risposte_post_questionario' in st.session_state:
                # Converte il dizionario in una lista di valori
                post_scores = list(st.session_state.risposte_post_questionario.values())

                # Calcola la media generale
                average_feedback = sum(post_scores) / len(post_scores) if post_scores else 0

                # Crea un dizionario per mappare le domande alle risposte
                short_keys = [
                    "Mi sono sentito/a coinvolto/a attivamente nella conversazione durante l'esperimento.",
                    "Il gruppo ha collaborato in modo efficace per raggiungere un obiettivo comune.",
                    "L'intelligenza artificiale ha contribuito in modo utile alla discussione.",
                    "Le interazioni con l'IA sono state chiare e comprensibili.",
                    "Mi sono sentito/a ascoltato/a e rispettato/a dagli altri partecipanti.",
                    "Le istruzioni e gli obiettivi dell'esperimento erano chiari.",
                    "Rifarei volentieri un'esperienza simile in futuro.",
                    "L'esperimento mi ha fatto riflettere su come si può collaborare con un'IA.",
                    "Ho trovato l'esperienza interessante e stimolante.",
                    "In generale, valuto l'esperienza come positiva."
                ]

                feedback_data = {}
                for i, _ in enumerate(short_keys):
                    # i+1 perché le chiavi del dizionario partono da 1
                    feedback_data[short_keys[i]] = st.session_state.risposte_post_questionario.get(i + 1, 0)
    else:
        # Per utente singolo, usa direttamente i dati individuali
        if 'risposte_post_questionario' in st.session_state:
            post_scores = list(st.session_state.risposte_post_questionario.values())
            average_feedback = sum(post_scores) / len(post_scores) if post_scores else 0

            # Crea un dizionario per mappare le domande alle risposte
            short_keys = [
                "Coinvolgimento personale",
                "Collaborazione di gruppo",
                "Utilità dell'IA",
                "Chiarezza interazioni IA",
                "Rispetto tra partecipanti",
                "Chiarezza obiettivi",
                "Ripeterei l'esperienza",
                "Riflessione su IA-persona",
                "Esperienza stimolante",
                "Valutazione generale"
            ]
            feedback_data = {}
            for i, _ in enumerate(short_keys):
                # i+1 perché le chiavi del dizionario partono da 1
                feedback_data[short_keys[i]] = st.session_state.risposte_post_questionario.get(i + 1, 0)
        else:
            # Valori di default nel caso non ci sia ancora il questionario post-esperimento
            average_feedback = 0
            feedback_data = {
                "Coinvolgimento personale": 0,
                "Collaborazione di gruppo": 0,
                "Utilità dell'IA": 0,
                "Chiarezza interazioni IA": 0,
                "Rispetto tra partecipanti": 0,
                "Chiarezza obiettivi": 0,
                "Ripeterei l'esperienza": 0,
                "Riflessione su IA-persona": 0,
                "Esperienza stimolante": 0,
                "Valutazione generale": 0
            }

    # ranking NASA
    nasa_ranking = {
        "Scatola di Fiammiferi": 15,
        "Concentrato Alimentare": 4,
        "Corda in nylon di 15 metri": 6,
        "Paracadute di seta": 8,
        "Unità di Riscaldamento Portatile": 13,
        "Due pistole calibro .45": 11,
        "Latte disidratato": 12,
        "Bombole di ossigeno di 45kg": 1,
        "Mappa delle stelle": 3,
        "Zattera di salvataggio autogonfiabile": 9,
        "Bussola Magnetica": 14,
        "20 litri d'acqua": 2,
        "Razzo di segnalazione": 10,
        "Cassa di pronto soccorso": 7,
        "Radiolina alimentata con energia solare": 5
    }

    # Dizionari dei vari ranking
    user_ranking = {item['name']: idx + 1 for idx, item in enumerate(st.session_state.user_list)}
    user_ranking_afterai = {item['name']: idx + 1 for idx, item in enumerate(st.session_state.updated_list)}

    # Converte i ranking in una lista
    nasa_ranks = []
    user_ranks = []
    user_ranks_afterai = []

    # Aggiunge i rank ordinati nelle liste
    for item in nasa_ranking.keys():
        nasa_ranks.append(nasa_ranking[item])
        user_ranks.append(user_ranking[item])
        user_ranks_afterai.append(user_ranking_afterai[item])

    # spearman rank correlation
    spearman_corr, _ = stats.spearmanr(user_ranks, nasa_ranks)
    spearman_corr_afterai, _ = stats.spearmanr(user_ranks_afterai, nasa_ranks)

    st.title("Risultati")
    st.write("---")
    st.write(
        "IMPORTANTE: per completare la consegna dei risultati e concludere l'esperimento, è necessario scorrere fino in fondo alla pagina e cliccare sul pulsante 'Conferma e Termina'")
    st.write("---")
    st.subheader("Metriche importanti:")
    initial_precision_percent = ((spearman_corr + 1) / 2) * 100
    final_precision_percent = ((spearman_corr_afterai + 1) / 2) * 100
    st.write(f"Precisione classifica iniziale: {initial_precision_percent:.1f}%")
    st.write(f"Precisione classifica finale: {final_precision_percent:.1f}%")

    print(f"[{username}]Precisione classifica iniziale: {initial_precision_percent:.1f}%")
    print(f"[{username}]Precisione classifica finale: {final_precision_percent:.1f}%")


    improvement_percentage = round(((spearman_corr_afterai - spearman_corr) / (1 - spearman_corr)) * 100, 1)

    print(f"[{username}]Percentuale di miglioramento : {improvement_percentage}%")

    st.write("-------")
    if (improvement_percentage >= 0):
        st.subheader(f"Percentuale di miglioramento : {improvement_percentage}%")
        st.progress(improvement_percentage / 100)
    else:
        st.subheader(f"Percentuale di miglioramento : {improvement_percentage}%")
        st.progress(0)
    st.write("--------")

    # Dati della tabella NASA
    st.subheader("Soluzione ufficiale della NASA")
    st.write("La tabella seguente mostra la classifica corretta degli oggetti secondo la NASA, con le relative spiegazioni:")

    nasa_official_data = {
        1: {
            "oggetto": "Bombole di ossigeno di 45kg",
            "commento": "Il bisogno più immediato per la sopravvivenza"
        },
        2: {
            "oggetto": "20 litri d'acqua",
            "commento": "Essenziale per la sopravvivenza"
        },
        3: {
            "oggetto": "Mappa delle stelle",
            "commento": "Metodo di orientamento molto importante"
        },
        4: {
            "oggetto": "Concentrato Alimentare",
            "commento": "Un modo efficace per fornire energia all'organismo"
        },
        5: {
            "oggetto": "Radiolina alimentata con energia solare",
            "commento": "Utili per la comunicazione con la base, ma le onde FM\n hanno un piccolo intervallo di ricezione e richiedono un'antenna ricevente in vista"
        },
        6: {
            "oggetto": "Corda in nylon di 15 metri",
            "commento": "Utile per scalare i pendii, per eventuali ferite e per\n trasportare materiale"
        },
        7: {
            "oggetto": "Cassa di pronto soccorso",
            "commento": "Vitamine e medicine si possono usare per mantenersi\n in salute"
        },
        8: {
            "oggetto": "Paracadute di seta",
            "commento": "Utile come protezione dai raggi solari, come trasporto\n e per avvolgersi dentro nelle fasi del sonno"
        },
        9: {
            "oggetto": "Zattera di salvataggio autogonfiabile",
            "commento": "La bombola di CO₂ può essere utilizzata come mezzo\n di propulsione e la zattera può essere utile per trasportare gli oggetti"
        },
        10: {
            "oggetto": "Razzo di segnalazione",
            "commento": "Possono essere usati come segnale di pericolo o di\n comunicazione con la base o per meglio vedere la mappa"
        },
        11: {
            "oggetto": "Due pistole calibro .45",
            "commento": "Possibili mezzi di propulsione"
        },
        12: {
            "oggetto": "Latte disidratato",
            "commento": "Importante come cibo ma meno comodo del cibo\n concentrato"
        },
        13: {
            "oggetto": "Unità di Riscaldamento Portatile",
            "commento": "Non necessaria sulla faccia della Luna illuminata dal sole"
        },
        14: {
            "oggetto": "Bussola Magnetica",
            "commento": "Il campo magnetico lunare non è polarizzato: la bussola\n non serve all'orientamento"
        },
        15: {
            "oggetto": "Scatola di Fiammiferi",
            "commento": "Inutili: l'esigua concentrazione di ossigeno nell'atmosfera\n lunare rende i fiammiferi non utilizzabili"
        }
    }
    st.markdown("""
    <style>
    /* CSS più aggressivo e specifico */
    div[data-testid="stTable"] table {
        font-size: 14px !important;
        table-layout: fixed !important;
        width: 100% !important;
         border-collapse: collapse !important;        
        border: 2px solid #000000 !important; 
    }

    div[data-testid="stTable"] table td {
        white-space: normal !important;
        word-wrap: break-word !important;
        vertical-align: top !important;
        padding: 4px !important;
        line-height: 1.2 !important;
        overflow-wrap: break-word !important;
        background-color: #ffffff !important;
        color: #000000 !important;                  
        border: 1px solid #000000 !important; 
    }

    div[data-testid="stTable"] table th {
        background-color: #f8f9fa !important;
        color: #000000 !important;
        font-weight: bold !important;
        padding: 6px !important;
        white-space: nowrap !important;
        text-align: center !important;
        border: 1px solid #000000 !important;
        line-height: 1.1 !important;
    }

    /* Larghezze specifiche con selettori più precisi */
    div[data-testid="stTable"] table thead tr th:first-child,
    div[data-testid="stTable"] table tbody tr td:first-child {
        background-color: #f8f9fa !important;
        color: #000000 !important; 
        width: 20% !important;
        min-width: 150px !important;
        text-align: center !important;
        font-weight: bold !important;
        border: 1px solid #000000 !important;
        padding: 4px !important;                 
        line-height: 1.1 !important; 
    }

    div[data-testid="stTable"] table thead tr th:nth-child(2),
    div[data-testid="stTable"] table tbody tr td:nth-child(2) {
        width: 30% !important;
        font-weight: 500 !important;
        color: #000000 !important;
    }

    div[data-testid="stTable"] table thead tr th:nth-child(3),
    div[data-testid="stTable"] table tbody tr td:nth-child(3) {
        width: 50% !important;
        color: #000000 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Usa il DataFrame con l'indice come prima
    nasa_df = pd.DataFrame([
        {
            "Oggetto": data["oggetto"],
            "Commento": data["commento"]
        }
        for pos, data in nasa_official_data.items()
    ])

    # Imposta l'indice per iniziare da 1
    nasa_df.index = nasa_df.index + 1
    nasa_df.index.name = "Ordine"

    st.table(nasa_df)

    st.write("--------")

    df_ranking_comparison = pd.DataFrame({
        'Oggetti': list(nasa_ranking.keys()),  # colonne con i nomi degli item
        'La tua lista iniziale': [user_ranking.get(item, None) for item in nasa_ranking.keys()],
        'La lista collaborativa': [user_ranking_afterai.get(item, None) for item in nasa_ranking.keys()],
        # mette il ranking utente nella stessa linea del ranking nasa
        'Lista ufficiale NASA': [nasa_ranking.get(item, None) for item in nasa_ranking.keys()]
        # stessa cosa per la precisione dopo intervento IA
    })

    styled_df = df_ranking_comparison.style.apply(highlight_closeness, axis=1)

    st.markdown("""
    <style>
    .stDataFrame {
        font-size: 13px;
    }
    .stDataFrame th {
        text-align: center !important;
        font-weight: bold !important;
        background-color: #f8f9fa !important;
    }
    .stDataFrame td {
        text-align: center !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # mostra la tabella dei risultati
    st.subheader("Tabella di confronto dei risultati")
    st.write(
        "La tabella riporta, per ciascun oggetto, la posizione in classifica prima e dopo il consiglio fornito dal LLM, nonché la posizione ritenuta corretta secondo la classifica ufficiale della NASA. Gli oggetti, la cui precisione è migliorata dopo il consiglio, sono evidenziati in verde, mentre quelli per cui si è osservato un peggioramento sono evidenziati in rosso.")
    num_rows = len(df_ranking_comparison)
    exact_height = 40 + (num_rows * 35)

    st.dataframe(
        styled_df,
        use_container_width=True,
        height=exact_height,
        hide_index= True
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(df_ranking_comparison['Oggetti']))
    ax.bar(x - 0.3, df_ranking_comparison['La tua lista iniziale'], width=0.2, label='La tua lista iniziale')
    ax.bar(x - 0.1, df_ranking_comparison['La lista collaborativa'], width=0.2, label='La lista collaborativa')
    ax.bar(x + 0.1, df_ranking_comparison['Lista ufficiale NASA'], width=0.2, label='Lista ufficiale NASA')
    ax.set_xticks(x)
    ax.set_xticklabels(df_ranking_comparison['Oggetti'], rotation=45, ha='right')
    ax.set_ylabel('Ranking')
    ax.set_title('Comparison of User, AI, and NASA Rankings')
    ax.legend()

    # -------------------------------------------

    # Calcolo della precisione per ogni item
    max_rank_difference = 14

    # Accuracy per ogni item
    df_ranking_comparison['Accuracy_Iniziale'] = 1 - (abs(
        df_ranking_comparison['La tua lista iniziale'] - df_ranking_comparison[
            'Lista ufficiale NASA']) / max_rank_difference)
    df_ranking_comparison['Accuracy_Finale'] = 1 - (abs(
        df_ranking_comparison['La lista collaborativa'] - df_ranking_comparison[
            'Lista ufficiale NASA']) / max_rank_difference)
    # Mostra l'accuracy per ogni item
    st.write("--------------------")
    st.subheader("Precisione di ogni oggetto, prima e dopo l'esperimento")
    st.write(
        "Il grafico mostra, per ogni oggetto, la precisione nella classifica svolta individualmente e la precisione nella classifica dopo aver svolto l'esperimento")
    # bar chart per confronto di precisione
    fig2, ax2 = plt.subplots(figsize=(12, 14))
    x = np.arange(len(df_ranking_comparison['Oggetti']))
    ax2.bar(x - 0.2, df_ranking_comparison['Accuracy_Iniziale'], width=0.4, label='Precisione prima ',
            color='royalblue')
    ax2.bar(x + 0.2, df_ranking_comparison['Accuracy_Finale'], width=0.4, label='Precisione dopo', color='darkorange')

    # labels e legenda
    ax2.set_xlabel('Oggetti')
    ax2.set_ylabel('Precisione')
    ax2.set_title('Confronto della precisione tra la classifica individuale e quella collaborativa')
    ax2.set_xticks(x)
    ax2.set_xticklabels(df_ranking_comparison['Oggetti'], rotation=45, fontsize=8, ha='right')

    ax2.legend(bbox_to_anchor=(0.5, -0.3), loc='upper center', ncol=2)


    plt.tight_layout()
    plt.subplots_adjust(bottom=0.4)

    # mostra il chart di precisione
    st.pyplot(fig2)


    st.write("--------------------")
    st.subheader("Feedback degli utenti")
    st.write(f"📊 **Media feedback complessivo: {average_feedback:.1f} / 4**")

    # Crea un dataframe per visualizzare le barre
    feedback_df = pd.DataFrame({
        'Categoria': list(feedback_data.keys()),
        'Punteggio': list(feedback_data.values())
    })

    # Ordina per punteggio decrescente
    feedback_df = feedback_df.sort_values('Punteggio', ascending=False)

    # Visualizza le barre orizzontali
    fig_feedback, ax_feedback = plt.subplots(figsize=(10, 6))
    bars = ax_feedback.barh(feedback_df['Categoria'], feedback_df['Punteggio'], color='royalblue')

    # Aggiunge etichette con i valori
    for i, bar in enumerate(bars):
        width = bar.get_width()
        ax_feedback.text(width + 0.1, bar.get_y() + bar.get_height() / 2, f'{width:.1f}',
                         ha='left', va='center')

    ax_feedback.set_xlim(0, 4)
    ax_feedback.set_title('Feedback dell\'esperienza')
    ax_feedback.set_xlabel('Punteggio (0-4)')

    # Mostra il grafico
    st.pyplot(fig_feedback)

    # Aggiunge l'analisi combinata
    st.write("--------------------")
    st.subheader("Analisi combinata automatica")

    # Definisce le soglie per l'analisi
    precision_threshold_high = 0.5
    precision_threshold_low = 0.4
    feedback_threshold_high = 2.5
    feedback_threshold_medium = 2.0

    # Genera il commento in base alle soglie
    if spearman_corr_afterai >= 0.5 and average_feedback >= 2.5:
        commento = "✅ Ottimo risultato! La soluzione è vicina a quella ufficiale e gli utenti hanno espresso un buon livello di soddisfazione."
        commento_colore = "rgba(0, 128, 0, 0.1)"
    elif spearman_corr_afterai < 0.5 and average_feedback >= 2.5:
        commento = "🤔 Esperienza positiva ma risultato migliorabile. La soluzione è distante da quella ufficiale, ma gli utenti hanno valutato positivamente la collaborazione con l'IA."
        commento_colore = "rgba(255, 165, 0, 0.1)"
    elif spearman_corr_afterai >= 0.5 and average_feedback < 2.0:
        commento = "📈 Buon risultato ma esperienza da migliorare. La classifica è vicina a quella corretta, ma l'esperienza è stata percepita negativamente."
        commento_colore = "rgba(0, 0, 255, 0.1)"
    elif precision_threshold_low <= 0.5 < 2.0 and average_feedback >= 2.5:
        commento = "👍 Risultato nella media. Sia la precisione che la soddisfazione degli utenti sono a livelli accettabili."
        commento_colore = "rgba(200, 200, 200, 0.1)"
    else:
        commento = "⚠️ Risultato da migliorare. Sia la precisione che il feedback degli utenti sono sotto le aspettative."
        commento_colore = "rgba(255, 0, 0, 0.1)"

    # Visualizza il commento
    st.markdown(
        f'<div style="background-color: {commento_colore}; padding: 20px; border-radius: 10px; color: white;">{commento}</div>',
        unsafe_allow_html=True)

    # Grafico del quadrante
    st.write("--------------------")
    st.subheader("Quadrante riassuntivo")

    # Crea il grafico a quadranti
    fig_quadrant, ax_quadrant = plt.subplots(figsize=(10, 7.5))

    # Imposta limiti fissi e uguali per gli assi per garantire quadranti uniformi
    ax_quadrant.set_xlim(0, 1)
    ax_quadrant.set_ylim(0, 4)
    ax_quadrant.tick_params(axis='both', which='major', labelsize=6)

    # Disegna le linee che dividono i quadranti
    ax_quadrant.axhline(y=2.0, color='gray', linestyle='--', alpha=0.5)
    ax_quadrant.axvline(x=0.5, color='gray', linestyle='--', alpha=0.5)

    # Aggiunge il punto che rappresenta questa sessione
    ax_quadrant.plot(spearman_corr_afterai, average_feedback, 'ko', alpha=0)

    # Determina l'emoji in base al quadrante
    if spearman_corr_afterai >= 0.5 and average_feedback >= 2.5:
        marker, color, text = "o", "green", "O"  # Ottimo
    elif spearman_corr_afterai < 0.5 and average_feedback >= 2.5:
        marker, color, text = "o", "orange", "S"  # Soddisfacente
    elif spearman_corr_afterai >= 0.5 and average_feedback < 2.5:
        marker, color, text = "o", "blue", "M"  # Migliorabile
    else:
        marker, color, text = "o", "red", "R"  # Da rivedere

    # Calcola posizione sicura per il punto
    safe_x = max(0.05, min(0.95, spearman_corr_afterai))
    safe_y = max(0.15, min(3.85, average_feedback))

    # Disegna un punto visibile per la posizione dell'utente
    ax_quadrant.plot(safe_x, safe_y, marker=marker, markersize=5, color=color, zorder=5)

    # Se il punto è vicino al bordo superiore, mette il testo sotto
    if safe_y > 3.5:
        text_offset_y = -8  # Sotto il punto
    else:
        text_offset_y = 8  # Sopra il punto

    # Se il punto è vicino al bordo destro, mette il testo a sinistra
    if safe_x > 0.8:
        text_offset_x = -8  # A sinistra del punto
    else:
        text_offset_x = 8  # A destra del punto

    # Etichetta il punto con il nome utente
    if 'username' in st.session_state:
        label = st.session_state.username
    else:
        label = "Tu"
    ax_quadrant.annotate(label, (safe_x, safe_y),
                         xytext=(text_offset_x, text_offset_y), textcoords='offset points',
                         fontweight='bold', color='black',
                         fontsize=14,
                         zorder=6)

    # Definisce e colora i quadranti
    # Top-right (Alto-destra): buona precisione, buon feedback
    ax_quadrant.fill_between([0.5, 1], [2.0, 2.0], [4, 4], color='green', alpha=0.1)
    # Top-left (Alto-sinistra): bassa precisione, buon feedback
    ax_quadrant.fill_between([0, 0.5], [2.0, 2.0], [4, 4], color='orange', alpha=0.1)
    # Bottom-right (Basso-destra): buona precisione, cattivo feedback
    ax_quadrant.fill_between([0.5, 1], [0, 0], [2.0, 2.0], color='blue', alpha=0.1)
    # Bottom-left (Basso-sinistra): fallimento totale
    ax_quadrant.fill_between([0, 0.5], [0, 0], [2.0, 2.0], color='red', alpha=0.1)

    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor='green', alpha=0.3, label='Ottimo'),
        Patch(facecolor='orange', alpha=0.3, label='Soddisfacente'),
        Patch(facecolor='blue', alpha=0.3, label='Migliorabile'),
        Patch(facecolor='red', alpha=0.3, label='Da rivedere')
    ]

    ax_quadrant.legend(handles=legend_elements,
                       loc='center left',
                       bbox_to_anchor=(1, 0.5),
                       frameon=True)

    # Personalizza il grafico
    ax_quadrant.set_xlim(0, 1)
    ax_quadrant.set_ylim(0, 4)
    ax_quadrant.set_xlabel("Precisione classifica", fontsize=12)
    ax_quadrant.set_ylabel("Soddisfazione utenti", fontsize=12)
    ax_quadrant.set_title("Precisione vs Soddisfazione", fontsize=12)

    # Ridimensiona i numeri degli assi
    ax_quadrant.tick_params(axis='both', which='major', labelsize=10)

    # Rende il grafico più compatto
    plt.tight_layout()

    # Mostra il grafico
    st.pyplot(fig_quadrant, use_container_width=True)

    with st.form("Ranking Form"):
        user_info = st.session_state.risposte_personali
        submit_button = st.form_submit_button(label='Conferma e termina')

    # Se si clicca il bottone, invia tutti i risultati al database
    if (submit_button):
        if (st.session_state.alone == True):
            engine = get_engine_alone()
            session = get_session(engine)


        elif (st.session_state.alone == False):
            engine = get_engine()
            session = get_session(engine)


        # Passa alla pagina di ringraziamenti
        st.session_state.page = 7
        st.rerun()


elif st.session_state.page == 7:
    st.title("Grazie per aver partecipato!")
