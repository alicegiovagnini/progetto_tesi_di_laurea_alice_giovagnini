import streamlit as st
import requests, uuid, hashlib
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import os, random, re, time, json, copy
import streamlit as st  # type: ignore
from gpt4all import GPT4All  # type: ignore
from st_draggable_list import DraggableList  # type: ignore
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import scipy.stats as stats  # type: ignore
from fuzzywuzzy import process  # type: ignore
import matplotlib.pyplot as plt  # type:ignore
from database import get_engine, get_session, insert_user_results_to_db, insert_user_info_to_db, UserResults, UserInfo;
from groq import Groq  # type:ignore
import websockets  # type:ignore
from apikey import GROQ_API_KEY
import threading
import asyncio
import json
import traceback
from error_handler import backend_is_available

# ------------------------
BASE_URL = "http://127.0.0.1:8000"


def next_page():
    st.session_state.page += 1
    st.rerun()


def prev_page():
    if st.session_state.page > 1:
        st.session_state.page -= 1
        st.rerun()

def send_continua_message(group_id, username):
    """
    Notifica al backend che un utente ha confermato di voler proseguire.
    """
    url = "http://127.0.0.1:8000/aggiorna_conferma"
    payload = {
        "group_id": group_id,
        "username": username
    }
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        if response is None:
            print("Backend non disponibile per l'invio del messaggio di conferma")
            return
        if response.status_code != 200:
            print(f"Errore nell'invio del messaggio di conferma: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Errore nell'invio del messaggio di conferma: {e}")


def get_modalita(group_id=None, username=None):
    """
    Ottiene la modalità di intervento per un utente in un gruppo.
    """
    if group_id is None:
        if 'group_id' in st.session_state:
            group_id = st.session_state.group_id
        elif 'partner' in st.session_state and 'username' in st.session_state:
            user1, user2 = sorted([st.session_state.username, st.session_state.partner])
            group_id = f"{user1}-{user2}"

    if username is None:
        if 'username' in st.session_state:
            username = st.session_state.username


    response = requests.get(f"http://127.0.0.1:8000/get_modalita/{group_id}/{username}")
    if response is None:
        return "nessuna"
    if response.status_code == 200:
        data = response.json()
        return data['modalita']
    return "nessuna"


def send_previous_list_to_backend(previous_list_text=None, group_id=None):
    """
    Invia la lista precedente dell'utente al backend, supportando sia chat 1:1 che gruppi.
    """
    if previous_list_text is None:
        previous_list_text = st.session_state.previous_list_text

    if group_id is None:
        if 'group_id' in st.session_state:
            group_id = st.session_state.group_id
        elif 'partner' in st.session_state and 'username' in st.session_state:
            user1, user2 = sorted([st.session_state.username, st.session_state.partner])
            group_id = f"{user1}-{user2}"

    if not group_id:
        print("Impossibile determinare l'ID del gruppo")
        return False

    try:
        url = "http://127.0.0.1:8000/sync_list"
        payload = {
            "group_id": group_id,
            "username": st.session_state.username,
            "list": st.session_state.previous_list
        }

        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response is None:
            print("Backend non disponibile per l'invio della lista")
            return
        if response.status_code == 200:
            return True
        else:
            print(
                f"Errore nell'invio della lista precedente. Status code: {response.status_code}, Risposta: {response.text}")
            # Fallback all'endpoint precedente se necessario
            if response.status_code == 422:  # Errore di validazione parametri
                # Prova con il vecchio formato
                old_url = "http://127.0.0.1:8000/api/previous_list"

                # Se è un gruppo, cerca di determinare un "partner" per compatibilità
                partner = None
                if 'partner' in st.session_state:
                    partner = st.session_state.partner
                elif group_id in ['group_members'] and len(st.session_state.group_members) > 1:
                    # Scegli un altro membro diverso dall'utente corrente
                    for member in st.session_state.group_members:
                        if member != st.session_state.username:
                            partner = member
                            break

                # Se si ha un partner
                if partner:
                    old_payload = {
                        "username": st.session_state.username,
                        "partner": partner,
                        "updated_list": previous_list_text
                    }

                    old_response = requests.post(
                        old_url,
                        json=old_payload,
                        headers=headers,
                        timeout=5
                    )

                    if old_response.status_code == 200:
                        print(f"Lista inviata con il formato retrocompatibile al backend")
                        return True
                    else:
                        print(f"Anche il tentativo retrocompatibile è fallito: {old_response.status_code}")

            return False


    except Exception as e:
        print(f"Errore durante l'invio della lista: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def send_message():
    """
    Funzione per inviare un messaggio di chat dal frontend al backend.
    Supporta sia chat 1:1 che chat di gruppo.
    """
    user_input = st.session_state.chat_input
    username = st.session_state.username
    group_id = None

    # Determina il destinatario o il gruppo
    if 'group_id' in st.session_state:
        group_id = st.session_state.group_id
    elif 'partner' in st.session_state:
        paired_user = st.session_state.partner
        # Per retrocompatibilità, crea un ID gruppo per chat 1:1
        user1, user2 = sorted([username, paired_user])
        group_id = f"{user1}-{user2}"
        print(f"Invio messaggio in chat 1:1 con ID: {group_id}")

    if not group_id:
        st.error("Errore: Nessun gruppo o partner identificato per l'invio del messaggio")
        return

    if user_input and user_input.strip():
        st.session_state.last_user_input = user_input
        st.session_state.chat_input = ""

        try:
            response = requests.post(f"{BASE_URL}/send_message", json={
                "from_user": username,
                "group_id": group_id,
                "content": user_input
            })
            if response is None:
                print("Backend non disponibile: impossibile inviare il messaggio")
                return
            if response.status_code != 200:
                st.error(f"Errore nell'invio del messaggio: {response.status_code}")
                print(f"Errore nell'invio del messaggio: {response.text}")
            else:
                fetch_messages()
        except Exception as e:
            st.error(f"Errore di connessione: {e}")
            print(f"Eccezione durante l'invio del messaggio: {e}")
    else:
        print("Messaggio vuoto, non inviato")
        st.session_state.chat_input = ""

def register_user_rest(username):
    """
        Registra un utente attraverso l'API REST
        """
    if not username or not username.strip():
        print("Username vuoto, registrazione fallita")
        return False

    try:
        response = requests.post(
            "http://127.0.0.1:8000/rest_register_user",
            json={"username": username},
            timeout=5
        )
        if response is None:
            return False
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                print(f"Utente {username} registrato con successo")
                return True
            else:
                print(f"Errore nella registrazione: {data.get('message')}")
                return False
        else:
            print(f"Errore nella registrazione. Status code: {response.status_code}")
            return False
    except requests.RequestException:
        return False
    except Exception:
        return False


def unregister_user_rest(username):
    """
       Rimuove un utente dal sistema attraverso l'API REST
       """
    if not username:
        return False

    try:
        response = requests.post(
            "http://127.0.0.1:8000/rest_unregister_user",
            json={"username": username},
            timeout=5
        )
        if response is None:
            return
        if response.status_code == 200:
            print(f"Utente {username} rimosso")
            return True
        else:
            print(f"Errore nella rimozione dell'utente. Status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Errore durante la rimozione dell'utente: {e}")
        return False


def chatroom():
    """
    Funzione che gestisce l'interfaccia della chat room.
    Mostra i messaggi e permette all'utente di inviare nuovi messaggi.
    """
    username = st.session_state.username

    if backend_is_available():
        st_autorefresh(interval=2000, key="chat_autorefresh")

    # Determina i membri del gruppo
    group_id = None
    group_members = []

    if 'group_id' in st.session_state:
        group_id = st.session_state.group_id

        try:
            response = requests.get(f"{BASE_URL}/get_group/{group_id}/members", timeout=5)
            if response is None:
                # Fallback alla sessione se il backend non risponde
                if 'group_members' in st.session_state:
                    group_members = st.session_state.group_members
                elif 'partner' in st.session_state:
                    group_members = [username, st.session_state.partner]
            elif response.status_code == 200:
                data = response.json()
                group_members = data.get('members', [])
                # Assicura che tutti i membri siano stringhe
                group_members = [str(m) for m in group_members if m]
                st.session_state.group_members = group_members
            else:
                print(f"Errore nel recupero dei membri del gruppo: {response.status_code}")
        except Exception as e:
            print(f"Errore nel recupero dei membri del gruppo: {e}")

        # Fallback alla sessione o al controllo per chat 1:1
        if not group_members:
            if 'group_members' in st.session_state:
                group_members = st.session_state.group_members
            elif 'partner' in st.session_state:
                group_members = [username, st.session_state.partner]

    # Assicura che siano tutti stringhe uniche
    group_members = [str(m) for m in group_members if m]
    group_members = list(set(group_members))  # Rimuove duplicati

    # Filtra l'utente corrente dall'elenco per la visualizzazione
    all_members = sorted(group_members)

    # Crea il titolo della chat con tutti i membri in ordine alfabetico
    members_str = ", ".join(all_members)
    st.sidebar.markdown("# **Chat di gruppo**")


    # Inizializza variabili di sessione se non esistono
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chat_input" not in st.session_state:
        st.session_state.chat_input = ""
    if "last_user_input" not in st.session_state:
        st.session_state.last_user_input = ""
    if "last_intervention_type" not in st.session_state:
        st.session_state.last_intervention_type = None

    #Mostra sempre tutti i membri del gruppo in una lista
    if len(group_members) > 1:  # Mostra la lista anche per gruppi di 2 membri
        st.sidebar.subheader("Membri del gruppo:")
        for member in all_members:
            if member == username:
                st.sidebar.markdown(f"* **{member} (tu)**")
            else:
                st.sidebar.markdown(f"* {member}")
        st.sidebar.divider()

    # Per i ricercatori: Mostra il tipo di intervento
    intervention_type = None

    # Determina l'ID appropriato per recuperare il tipo di intervento
    intervention_id = group_id
    if not intervention_id and 'partner' in st.session_state:
        intervention_id = st.session_state.partner

    if intervention_id:
        intervention_type = get_intervention_type(username, intervention_id)

    # Mostra info sull'intervento
    intervention_info = st.sidebar.empty()
    if intervention_type:
        intervention_info.info(f"Tipo di intervento IA: {intervention_type}")
    else:
        intervention_info.info("Tipo di intervento IA: In attesa")

    # Recupera i messaggi
    fetch_messages()

    # Info numero messaggi
    st.sidebar.caption(f"Numero di messaggi: {len(st.session_state.messages)}")

    # Container per i messaggi
    message_container = st.sidebar.container()
    with message_container:
        if not st.session_state.messages:
            st.sidebar.info("Nessun messaggio ancora. Inizia la conversazione!")
        else:
            for msg in st.session_state.messages:
                parts = msg.split(':', 1)
                if len(parts) == 2:
                    sender, content = parts[0].strip(), parts[1].strip()

                    # Stile diverso per messaggi dell'utente, partner e LLM
                    if sender == username:
                        # Messaggio dell'utente corrente
                        st.sidebar.markdown(
                            f"""<div style="background-color: #dcf8c6; color: black; padding: 8px 12px; 
                            border-radius: 12px; margin: 4px 0; max-width: 95%;">
                            <b>Tu:</b> {content}</div>""",
                            unsafe_allow_html=True
                        )
                    elif sender == "LLM":
                        # Messaggio dell'LLM
                        # Rimuove le virgolette se presenti
                        clean_content = content
                        if clean_content.startswith("'") and clean_content.endswith("'"):
                            clean_content = clean_content[1:-1]

                        # Sostituisce i punti seguiti da spazio con punto + <br> + spazio
                        import re
                        formatted_content = re.sub(r'\.(\s+)', r'.<br>\1', clean_content)

                        # Se il testo finisce con un punto senza spazio, aggiungi comunque <br>
                        if formatted_content.endswith('.') and not formatted_content.endswith('.<br>'):
                            formatted_content = formatted_content[:-1] + '.<br>'

                        # Evidenzia i nomi degli utenti in grassetto nei messaggi LLM
                        formatted_content = clean_content
                        for member in all_members:
                            if member.lower() in formatted_content.lower():
                                # Sostituisce con case-insensitive ma mantiene la capitalizzazione originale
                                import re
                                pattern = re.compile(re.escape(member), re.IGNORECASE)
                                formatted_content = pattern.sub(f"<b>{member}</b>", formatted_content)

                        # Cerca anche nomi con prima lettera maiuscola seguiti da ":"
                        import re
                        # Pattern per trovare nomi che iniziano con maiuscola seguiti da ":"
                        name_pattern = r'\b([A-Z][a-z]+):'
                        formatted_content = re.sub(name_pattern, r'<b>\1</b>:', formatted_content)

                        st.sidebar.markdown(
                            f"""<div style="background-color: #6c757d; color: white; padding: 8px 12px; 
                            border-radius: 12px; margin: 4px 0; max-width: 95%; border-left: 4px solid #495057;">
                            🤖 <b>LLM:</b> {formatted_content}</div>""",
                            unsafe_allow_html=True
                        )
                    else:
                        # Messaggio di altri utenti
                        st.sidebar.markdown(
                            f"""<div style="background-color: #f0f2f6; color: #262730; padding: 8px 12px; 
                            border-radius: 12px; margin: 4px 0; max-width: 95%;">
                            <b>{sender}:</b> {content}</div>""",
                            unsafe_allow_html=True
                        )
                else:
                    st.sidebar.text(msg)  # Fallback per messaggi in formato non previsto

    # Input per inviare un nuovo messaggio
    prompt = st.chat_input("Invia un messaggio in chat")
    if prompt:
        # Salva il messaggio nell'input e chiama la funzione di invio
        st.session_state.chat_input = prompt
        send_message()
        # Aggiorna immediatamente per mostrare il messaggio inviato
        fetch_messages()
        st.rerun()

def fetch_messages():
    """
    Funzione che recupera i messaggi dal server e li salva in st.session_state.messages.
    Supporta sia chat 1:1 che gruppi.
    """
    username = st.session_state.username

    # Determina l'ID del gruppo
    group_id = None
    if 'group_id' in st.session_state:
        group_id = st.session_state.group_id
    elif 'partner' in st.session_state:
        user1, user2 = sorted([username, st.session_state.partner])
        group_id = f"{user1}-{user2}"

    if not group_id:
        print("Nessun gruppo o partner trovato")
        return

    old_message_count = len(st.session_state.get("messages", []))

    try:
        # Aggiunta di un timestamp casuale per evitare la cache del browser
        timestamp = int(time.time() * 1000)
        random_param = random.randint(1, 10000)
        cache_buster = f"&_={timestamp}&r={random_param}"

        response = requests.get(f"{BASE_URL}/get_group_messages/{group_id}?nocache={cache_buster}", timeout=2)
        if response is None:
            return
        if response.status_code == 200:
            all_messages = response.json().get("messages", [])

            # Aggiorna i messaggi solo se ci sono nuovi messaggi
            if len(all_messages) != old_message_count:
                st.session_state.messages = all_messages
        else:
            print(f"Errore nel recupero dei messaggi: {response.status_code}")
            print(f"Risposta: {response.text}")

        if 'group_id' in st.session_state:
            try:
                # Verifica ogni 5 secondi
                if time.time() % 5 < 1:
                    group_response = requests.get(f"{BASE_URL}/get_group/{username}", timeout=2)
                    if group_response.status_code == 200:
                        group_data = group_response.json()
                        if group_data.get('group_id') == group_id:
                            members = group_data.get('members', [])

                            # Aggiorna solo se i membri sono cambiati
                            if set(members) != set(st.session_state.get('group_members', [])):
                                print(f"Aggiornamento membri del gruppo: {members}")
                                st.session_state.group_members = members
            except Exception as e:
                print(f"Errore nell'aggiornamento dei membri: {e}")

    except Exception as e:
        print(f"Eccezione durante il recupero dei messaggi: {e}")


def check_group_status(username):
    """
    Controlla se l'utente è già in un gruppo e recupera i membri del gruppo
    """
    try:
        # Richiedi direttamente tutti i membri del gruppo
        response = requests.get(f"{BASE_URL}/get_group/{username}", timeout=5)
        if response is None:
            return None, []
        if response.status_code == 200:
            data = response.json()
            group_id = data.get('group_id')

            if group_id:
                # Usa un endpoint specifico per ottenere tutti i membri
                members_response = requests.get(f"{BASE_URL}/get_group_members/{group_id}", timeout=3)
                if members_response is None:
                    members = data.get('members', [])
                if members_response.status_code == 200:
                    members_data = members_response.json()
                    members = members_data.get('members', [])
                else:
                    members = data.get('members', [])

                # Assicura che tutti i membri siano stringhe e unici
                members = [str(m) for m in members if m]
                members = list(set(members))

                st.session_state.group_id = group_id
                st.session_state.group_members = members

                return group_id, members
        return None, []
    except Exception:
        return None, []


def fetch_connected_users():
    """
    Recupera la lista degli utenti connessi dal backend e gestisce gli errori
    """
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            response = requests.get("http://127.0.0.1:8000/rest_connected_users", timeout=3)
            if response is None:
                return []
            if response.status_code == 200:
                users = response.json().get("users", [])
                # Filtra il proprio username se presente
                if "username" in st.session_state:
                    current_username = st.session_state.username.lower()
                    users = [u for u in users if u.lower() != current_username]
                return users
            else:
                retry_count += 1
                time.sleep(1)
        except Exception:
            retry_count += 1
            time.sleep(1)

    return []

def generate_unique_key(username, shared_list):
    list_representation = ','.join([str(item) for item in shared_list])

    list_hash = hashlib.sha256(list_representation.encode()).hexdigest()
    unique_key = f"{username}_{list_hash}"
    return unique_key

def get_modalita_locale():
    username = st.session_state.username
    partner = st.session_state.partner

    response = requests.get(f"http://127.0.0.1:8000/get_modalita/{username}/{partner}")

    if response.status_code == 200:
        data = response.json()
        return data['modalita']


def get_intervention_type(username: str, partner_or_group_id: str):
    """Ottiene il tipo di intervento utilizzato per la chat"""
    try:
        # Determina se è un gruppo o chat 1:1
        if 'group_id' in st.session_state and partner_or_group_id == st.session_state.group_id:
            # È un gruppo
            url = f"http://127.0.0.1:8000/get_group_intervention_type/{partner_or_group_id}"
        else:
            # È una chat 1:1
            url = f"http://127.0.0.1:8000/get_intervention_type/{username}/{partner_or_group_id}"

        response = requests.get(url, timeout=2)
        if response is None:
            return "Ogni 3 messaggi"
        if response.status_code == 200:
            data = response.json()
            intervention_type = data.get('intervention_type', 'Ogni 3 messaggi')
            return intervention_type
        else:
            print(f"Errore nel recupero del tipo di intervento: {response.status_code}")
    except Exception as e:
        print(f"Errore durante il recupero del tipo di intervento: {e}")

    return "Ogni 3 messaggi"  # Default


def get_intervention_stats(username: str, partner: str):
    """Ottiene statistiche dettagliate sul pattern di intervento"""
    response = requests.get(f"{BASE_URL}/get_intervention_stats/{username}/{partner}")
    if response.status_code == 200:
        return response.json()
    return None

def check_group_members(username):
    """
    Controlla se l'utente è già in un gruppo e recupera i membri del gruppo
    """
    try:
        response = requests.get(f"{BASE_URL}/get_group/{username}", timeout=3)
        if response.status_code == 200:
            data = response.json()
            group_id = data.get('group_id')
            members = data.get('members', [])
            return group_id, members
        return None, []
    except Exception as e:
        print(f"Errore nel controllo del gruppo: {e}")
        return None, []


def send_group_invitation(from_user, to_user):
    """
    Invia un invito a un utente per unirsi a un gruppo
    """
    try:
        response = requests.post(
            f"http://127.0.0.1:8000/send_request",
            json={"from_user": from_user, "to_user": to_user, "is_group": True},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return True, data.get("request_id")
        else:
            print(f"Errore nell'invio dell'invito: {response.status_code}")
            return False, None
    except Exception as e:
        print(f"Errore di connessione: {e}")
        return False, None


def accept_group_invitation(request_id, from_user, to_user, group_id=None):
    """
    Accetta un invito a unirsi a un gruppo
    """
    try:
        payload = {
            "request_id": request_id,
            "from_user": from_user,
            "to_user": to_user,
            "response": "accept"
        }

        # Aggiunge il group_id al payload solo se è presente
        if group_id:
            payload["group_id"] = group_id

        response = requests.post(
            f"{BASE_URL}/response_request",
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            # Verifica se tutti hanno accettato
            all_accepted = data.get("all_accepted", False)
            group_id = data.get("group_id")

            if all_accepted and group_id:
                print(f"Tutti hanno accettato! Gruppo {group_id} creato.")
                return True, group_id
            else:
                print(f"Invito accettato, in attesa di altri membri...")
                return True, None  # Ritorna True ma group_id None se non tutti hanno accettato
        else:
            print(f"Errore nell'accettazione dell'invito: {response.status_code}")
            print(f"Dettagli: {response.text}")
            return False, None
    except Exception as e:
        print(f"Errore di connessione: {e}")
        import traceback
        print(traceback.format_exc())
        return False, None

def update_group_status(username):
    """
    Aggiorna lo stato del gruppo e controlla se è pronto per iniziare la chat
    """
    group_id, members = check_group_members(username)

    if not group_id or not members:
        return False, None, []

    # Controlla se il gruppo ha abbastanza membri per iniziare (almeno 2)
    if len(members) >= 2:
        return True, group_id, members

    return False, group_id, members


def start_group_chat(group_id, username):
    """
    Avvia una chat di gruppo
    """
    try:
        # Ottiene i membri del gruppo
        response = requests.get(f"{BASE_URL}/get_group/{username}", timeout=3)
        if response.status_code == 200:
            data = response.json()
            members = data.get('members', [])

            # Invia la lista precedente dell'utente
            send_previous_list_to_backend(st.session_state.previous_list_text, group_id)

            # Imposta le variabili di sessione per la chat di gruppo
            st.session_state.group_id = group_id
            st.session_state.group_members = members

            # Passa alla pagina della chat
            st.session_state.page = 21
            return True
        else:
            print(f"Errore nel recupero dei membri del gruppo: {response.status_code}")
            return False
    except Exception as e:
        print(f"Errore nell'avvio della chat di gruppo: {e}")
        return False

def send_multiple_group_invitations(from_user, to_users):
    """
    Invia inviti a più utenti per unirsi a un gruppo con una singola richiesta.
    """
    try:
        # Genera un ID univoco per il gruppo
        import time
        import random
        group_id = f"group_{from_user}_{int(time.time())}_{random.randint(1000, 9999)}"

        # Inizializza la struttura dati per il gruppo sul backend
        response = requests.post(
            "http://127.0.0.1:8000/create_pending_group",  # Crea un nuovo endpoint per questo
            json={
                "creator": from_user,
                "members_to_invite": to_users,
                "group_id": group_id
            },
            timeout=5
        )

        if response.status_code != 200:
            print(f"Errore nell'inizializzazione del gruppo: {response.status_code}")
            return False, None

        # Invia gli inviti a ciascun utente
        for to_user in to_users:
            response = requests.post(
                "http://127.0.0.1:8000/send_request",
                json={
                    "from_user": from_user,
                    "to_user": to_user,
                    "is_group": True,
                    "group_id": group_id
                },
                timeout=5
            )

            if response.status_code == 200:
                print(f"Invito inviato con successo a {to_user} per gruppo {group_id}")
            else:
                print(f"Errore nell'invio dell'invito a {to_user}: {response.status_code}")

        return True, group_id

    except Exception as e:
        print(f"Errore di connessione: {e}")
        return False, None





def respond_to_group_invitation(group_id, response_type, from_user, to_user):
    """
    Risponde a un invito di gruppo (accetta o rifiuta)
    """
    try:
        # Invia la risposta via WebSocket se l'utente è connesso
        if to_user in st.session_state.get("usernames", {}):
            st.session_state.usernames[to_user].send_json({
                "type": "group_response",
                "groupId": group_id,
                "response": response_type
            })
            return True
        else:
            # Altrimenti invia attraverso l'API REST
            return fetch_messages_from_websocket({
                "type": "group_response",
                "groupId": group_id,
                "response": response_type
            }, to_user)
    except Exception as e:
        print(f"Errore nella risposta all'invito di gruppo: {e}")
        return False


def fetch_messages_from_websocket(message_data, username):
    """
    Funzione helper per inviare messaggi al WebSocket
    """
    try:
        # Implementazione per inviare il messaggio al backend
        websocket_url = f"ws://127.0.0.1:8000/ws/{username}"
        import websockets
        import asyncio
        import json

        async def send_message():
            async with websockets.connect(websocket_url) as websocket:
                await websocket.send(json.dumps(message_data))
                return await websocket.recv()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(send_message())
        loop.close()
        return True
    except Exception as e:
        print(f"Errore nell'invio del messaggio al WebSocket: {e}")
        return False


def setup_websocket_connection(username):
    """
    Configura una connessione WebSocket per ricevere aggiornamenti in tempo reale.
    """
    if "ws_connected" in st.session_state and st.session_state.ws_connected:
        return  # Evita di creare più connessioni

    async def handle_websocket_messages():
        ws_url = f"ws://127.0.0.1:8000/ws/{username}"

        while True:
            try:
                async with websockets.connect(ws_url) as websocket:
                    st.session_state.ws_connected = True
                    st.session_state.ws_connection_active = True

                    while True:
                        try:
                            message = await websocket.recv()

                            # Analizza il messaggio JSON
                            data = json.loads(message)
                            msg_type = data.get("type")

                            if msg_type == "list_sync":
                                # Ricevuto aggiornamento lista
                                group_id = data.get("group_id")
                                sender = data.get("username", "unknown")
                                new_list = data.get("list")
                                list_hash = data.get("list_hash")


                                if sender != username and new_list:
                                    print(f"[WebSocket] 📥 Aggiornamento lista da {sender}")
                                    # Verifica se la lista è effettivamente diversa usando l'hash
                                    current_hash = hashlib.md5(str([item['id'] for item in
                                                                    st.session_state.get('previous_list',
                                                                                         [])]).encode()).hexdigest()[:8]

                                    if list_hash != current_hash:
                                        st.session_state.receiving_update = True

                                        st.session_state.previous_list = copy.deepcopy(new_list)
                                        st.session_state.force_rerun = True
                                        print(f"[WebSocket] Lista aggiornata con hash {list_hash}")

                                        # Delay prima del rerun per evitare conflitti
                                        await asyncio.sleep(0.3)
                                        # Forza immediatamente il rerun
                                        st.rerun()
                                    else:
                                        print(f"[WebSocket] Lista già aggiornata, skip")

                            # Gestisce diversi tipi di messaggi
                            elif data.get("type") == "group_created":
                                # Gruppo creato con successo
                                group_id = data.get("groupId")
                                members = data.get("members", [])

                                # Salva le informazioni del gruppo nella sessione
                                st.session_state.group_id = group_id
                                st.session_state.group_members = members

                                # Forza l'aggiornamento della pagina
                                st.session_state.notifications = st.session_state.get("notifications", [])
                                st.session_state.notifications.append({
                                    "type": "success",
                                    "message": f"Gruppo creato con successo! Membri: {', '.join(members)}"
                                })

                                # Imposta un flag per passare alla pagina di chat
                                st.session_state.go_to_chat = True

                            elif data.get("type") == "group_members_update":
                                group_id = data.get("groupId")
                                members = data.get("members", [])

                                # Aggiorna i membri nella sessione
                                st.session_state.group_members = members

                                # Aggiunge una notifica
                                st.session_state.notifications = st.session_state.get("notifications", [])
                                st.session_state.notifications.append({
                                    "type": "info",
                                    "message": f"Lista membri aggiornata: {', '.join(members)}"
                                })

                                # Forza l'aggiornamento della pagina
                                st.experimental_rerun()

                            # Gestione per i messaggi di controllo aggiornamenti
                            elif data.get("type") == "check_list_updates":
                                group_id = data.get("groupId")

                                # Forza l'aggiornamento della lista impostando un flag
                                st.session_state.list_update_needed = True
                                st.session_state.list_update_group = group_id
                                st.session_state.list_update_time = data.get("timestamp", time.time())

                                print(f"Ricevuta notifica di controllo aggiornamenti per il gruppo {group_id}")

                            elif data.get("type") == "list_locked":
                                # Lista bloccata da un altro utente
                                st.session_state.list_locked = True
                                st.session_state.locked_by = data.get("locked_by", "")
                                print(f"Lista bloccata da {st.session_state.locked_by}")
                                st.rerun()

                            elif data.get("type") == "list_unlocked":
                                # Lista sbloccata
                                st.session_state.list_locked = False
                                st.session_state.locked_by = ""
                                print("Lista sbloccata")
                                st.rerun()

                            elif data.get("type") == "editing_lock_start":
                                # Un altro utente ha iniziato a modificare
                                st.session_state.list_locked = True
                                st.session_state.locked_by_user = data.get("editing_user")
                                print(f" Lista bloccata da {data.get('editing_user')}")
                                st.rerun()

                            elif data.get("type") == "editing_lock_end":
                                # L'altro utente ha finito di modificare
                                st.session_state.list_locked = False
                                st.session_state.locked_by_user = ""
                                print(f" Lista sbloccata da {data.get('editing_user')}")
                                st.rerun()

                            elif data.get("type") == "group_member_joined":
                                # Un nuovo membro si è unito al gruppo
                                joined_user = data.get("username")
                                members = data.get("members", [])

                                # Aggiorna i membri nella sessione
                                st.session_state.group_members = members

                                st.session_state.notifications = st.session_state.get("notifications", [])
                                st.session_state.notifications.append({
                                    "type": "success",
                                    "message": f"{joined_user} si è unito al gruppo!"
                                })

                            elif data.get("type") == "group_member_accepted":
                                # Un membro ha accettato l'invito
                                st.session_state.notifications = st.session_state.get("notifications", [])
                                st.session_state.notifications.append({
                                    "type": "info",
                                    "message": f"{data.get('acceptedUser')} ha accettato l'invito al gruppo. ({data.get('totalAccepted')}/{data.get('totalInvited')} membri)"
                                })

                            elif data.get("type") == "partner_disconnected":
                                # Partner di chat disconnesso
                                disconnected_user = data.get("username")
                                st.session_state.notifications = st.session_state.get("notifications", [])
                                st.session_state.notifications.append({
                                    "type": "warning",
                                    "message": f"{disconnected_user} si è disconnesso dalla chat."
                                })
                                # Reset del partner se necessario
                                if st.session_state.get("partner") == disconnected_user:
                                    st.session_state.partner = ""

                            elif data.get("type") == "user_list_update":
                                # Lista utenti aggiornata
                                new_users = data.get("users", [])
                                # Forza l'aggiornamento della lista utenti
                                st.session_state.force_user_list_refresh = True

                            elif data.get("type") == "group_member_disconnected":
                                disconnected_user = data.get("username")
                                group_id = data.get("groupId")
                                st.session_state.notifications = st.session_state.get("notifications", [])
                                st.session_state.notifications.append({
                                    "type": "warning",
                                    "message": f"{disconnected_user} si è disconnesso dal gruppo."
                                })
                                # Aggiorna la lista dei membri del gruppo
                                if 'group_members' in st.session_state and disconnected_user in st.session_state.group_members:
                                    st.session_state.group_members.remove(disconnected_user)

                            elif data.get("type") == "list_locked":
                                # Lista bloccata da un altro utente
                                locked_by = data.get("locked_by")
                                message_text = data.get("message", f"Lista bloccata da {locked_by}")
                                group_id = data.get("group_id")

                                print(f"[WS] Ricevuta notifica di blocco lista da {locked_by} per gruppo {group_id}")

                                # Aggiorna lo stato locale
                                if not hasattr(st.session_state, 'list_locked'):
                                    st.session_state.list_locked = {}
                                st.session_state.list_locked[group_id] = {
                                    "locked": True,
                                    "locked_by": locked_by
                                }

                                # Aggiungi notifica per l'utente
                                if not hasattr(st.session_state, 'notifications'):
                                    st.session_state.notifications = []
                                st.session_state.notifications.append({
                                    "type": "warning",
                                    "message": message_text
                                })

                                # Forza l'aggiornamento della pagina per riflettere il blocco
                                print(f"[WS] Forzando rerun per riflettere il blocco")
                                st.rerun()


                        except websockets.exceptions.ConnectionClosed:
                            print("Connessione WebSocket chiusa")
                            st.session_state.ws_connection_active = False
                            break
                        except json.JSONDecodeError:
                            print("[DEBUG WS] Errore decodifica JSON dal messaggio WebSocket")
                            continue
                        except Exception as e:
                            print(f"Errore nella gestione del messaggio WebSocket: {e}")
                            import traceback
                            print(traceback.format_exc())
                            await asyncio.sleep(1)

            except Exception as e:
                print(f"Errore nella connessione WebSocket: {e}")
                st.session_state.ws_connection_active = False
                await asyncio.sleep(3)  # Attesa prima di riconnettersi

    # Avvia il listener in un thread separato
    def run_websocket_loop():

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(handle_websocket_messages())
        except Exception as e:
            print(f"Errore nel thread WebSocket: {e}")
            import traceback
            print(traceback.format_exc())
        finally:
            loop.close()

    ws_thread = threading.Thread(target=run_websocket_loop(), daemon=True)
    ws_thread.start()
    print(f"Thread WebSocket avviato per {username}")
    st.session_state.ws_thread = ws_thread
    return ws_thread
