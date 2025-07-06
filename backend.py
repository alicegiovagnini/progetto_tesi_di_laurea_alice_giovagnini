import json
import copy
import hashlib
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Tuple
from threading import Lock
import random
import time
import asyncio
import datetime
from groq import Groq
from apikey import GROQ_API_KEY


# Lista degli oggetti disponibili per i gruppi
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

def should_suppress_websocket_error(error):
    """Determina se un errore WebSocket dovrebbe essere soppresso"""
    error_msg = str(error).lower()
    suppressed_phrases = [
        "websocket.send",
        "websocket.close",
        "response already completed",
        "unexpected asgi message",
        "websocket closed",
        "connection closed"
    ]
    return any(phrase in error_msg for phrase in suppressed_phrases)

def ask_llm(messages, group_id=None, sender=None):
    """
    Genera una risposta dell'IA basata sui messaggi recenti.
    """
    conversazione = "\n".join(messages)
    # Determina chat_key
    chat_key = group_id

    # Determina gli utenti del gruppo e le loro modalità
    users = []
    if group_id in manager.groups:
        users = manager.groups[group_id]
    elif "-" in group_id:
        users = group_id.split("-")

    # Separa gli utenti in base alla loro modalità individuale
    users_accordo = []
    users_disaccordo = []

    if hasattr(manager, 'user_modes'):
        for user in users:
            if manager.user_modes.get(user) == "accordo":
                users_accordo.append(user)
            elif manager.user_modes.get(user) == "disaccordo":
                users_disaccordo.append(user)

    # Lista completa degli oggetti disponibili
    oggetti_disponibili = [
        "Scatola di Fiammiferi",
        "Concentrato Alimentare",
        "Corda in nylon di 15 metri",
        "Paracadute di seta",
        "Unità di Riscaldamento Portatile",
        "Due pistole calibro .45",
        "Latte disidratato",
        "Bombole di ossigeno di 45kg",
        "Mappa delle stelle",
        "Zattera di salvataggio autogonfiabile",
        "Bussola Magnetica",
        "20 litri d'acqua",
        "Razzo di segnalazione",
        "Cassa di pronto soccorso",
        "Radiolina alimentata con energia solare"
    ]

    lista_oggetti_formattata = "\n".join([f"- {obj}" for obj in oggetti_disponibili])

    system_content = (
            "Gli utenti stanno lavorando in un gruppo per stilare una classifica degli oggetti più importanti per la sopravvivenza sulla luna. "
            "Questa è la lista completa degli oggetti disponibili:\n" + lista_oggetti_formattata + "\n\n"
    )

    if users_accordo:
        accordo_list = ", ".join(users_accordo)
        system_content += (
            f"IMPORTANTE: Devi essere in ACCORDO con questi utenti: {accordo_list}. "
            f"Sostieni e rafforza le loro argomentazioni quando parlano. "
        )

    if users_disaccordo:
        disaccordo_list = ", ".join(users_disaccordo)
        system_content += (
            f"IMPORTANTE: Devi essere in DISACCORDO con questi utenti: {disaccordo_list}. "
            f"Esprimi cortesemente opinioni contrarie alle loro argomentazioni quando parlano. "
        )

    if group_id in manager.groups:
        real_members = manager.groups[group_id]
        members_list = ", ".join(real_members)
        system_content += (
            f"IMPORTANTE: I membri REALI di questo gruppo sono SOLO: {members_list}. "
            f"NON fare mai riferimento a utenti che non sono in questa lista. "
            f"Quando rispondi, fai riferimento SOLO ai nomi degli utenti presenti in questo gruppo. "
        )
    system_content += (
        "NON iniziare mai le tue risposte con il nome di un utente seguito da ':'. "
        "Parla direttamente come partecipante al gruppo senza prefissi. "
        "Se vuoi rivolgerti a qualcuno, menziona il suo nome all'interno della frase, "
        "non all'inizio come se fossi quell'utente. "
        "Esempio CORRETTO: 'Ciao Alice, sono d'accordo con te...' "
        "Esempio SBAGLIATO: 'alice: sono d'accordo...' "
    )

    # Istruzioni per gestire conflitti
    if users_accordo and users_disaccordo:
        system_content += (
            "Quando ci sono opinioni contrastanti, privilegia sempre le opinioni di coloro con cui devi essere d'accordo. "
        )

    # Istruzioni generali
    system_content += (
        "Mantieni una posizione COERENTE per tutto il messaggio - non contraddire te stesso. "
        "Non aggiungere mai parentesi o note che spiegano il tuo ruolo - parla direttamente come se fossi un partecipante alla discussione. "
        "Quando vedi messaggi che iniziano con 'Assistente:' o 'LLM:', quelli sono i TUOI messaggi precedenti. "
        "NON devi essere d'accordo o in disaccordo con i tuoi stessi messaggi precedenti, "
        "ma solo con i messaggi degli utenti reali. "
        "Parla direttamente come se fossi un partecipante alla discussione. "
        "Quando un utente menziona uno di questi oggetti, assicurati di riconoscerlo come presente nella lista. "
        "NON dire che un oggetto non è incluso nella lista se è uno di quelli elencati sopra. "
        "Tieni presente che stai partecipando a una discussione di gruppo con più persone."
         "Puoi rispondere in modo generale al gruppo oppure rivolgerti specificamente a qualcuno quando appropriato. "
        "Se un utente del gruppo non ha ancora partecipato, puoi invitarlo a condividere la sua opinione. "
        "Non sei obbligato a menzionare qualcuno per nome in ogni risposta. "
        "Parla naturalmente come faresti in una discussione di gruppo reale. "
        "NON inventare mai nomi di persone che non sono membri effettivi del gruppo. "
        "Se devi fare riferimento a qualcuno, usa SOLO i nomi dei membri reali elencati sopra. "
        "NON usare nomi di esempio come 'Marco', 'Luca', 'Anna' o altri nomi generici. "
    )

    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {
                "role": "system",
                "content": system_content
            },
            {
                "role": "user",
                "content": conversazione
            }
        ],
        temperature=0.5,
        max_tokens=1024,
        top_p=0.9,
        frequency_penalty=0.5,  #  per evitare ripetizioni
        presence_penalty=0.5,  #  per diversificare le risposte
        stream=True,
        stop=None,
    )

    response = ""
    for chunk in completion:
        response += chunk.choices[0].delta.content or ""
    response = check_consistency(response, "multi-mode", users_accordo + users_disaccordo)
    return f"LLM : '{response}'"


def initial_llm_query(group_id, user_lists):
    """
    Genera una risposta iniziale basata sulle liste degli utenti nel gruppo.
    """
    print(f"DATI INITIAL LLM QUERY per gruppo {group_id}: {user_lists}")
    # Verifica che ci siano abbastanza messaggi nella chat
    if group_id in manager.chat_storage:
        recent_messages = manager.chat_storage[group_id]
        user_messages_count = sum(1 for msg in recent_messages if not msg.startswith("LLM :"))

        # Richiede almeno 3 messaggi prima dell'intervento iniziale
        if user_messages_count < 3:
            print(f"Non abbastanza messaggi utente ({user_messages_count}/3) per l'intervento iniziale in {group_id}")
            return None  # Non genera risposta

    # Determina le modalità per tutti gli utenti del gruppo
    available_users = list(user_lists.keys())
    users_accordo = []
    users_disaccordo = []

    if hasattr(manager, 'user_modes'):
        for username in available_users:
            if manager.user_modes.get(username) == "accordo":
                users_accordo.append(username)
                print(f"Utente {username} in modalità ACCORDO")
            elif manager.user_modes.get(username) == "disaccordo":
                users_disaccordo.append(username)
                print(f"Utente {username} in modalità DISACCORDO")
            else:
                # Default per utenti senza modalità
                print(f"Utente {username} senza modalità, assegnato DISACCORDO")
    else:
        # Se non si hanno dati delle modalità, assegna tutti a disaccordo
        print("Nessun dato modalità disponibile, tutti gli utenti assegnati a DISACCORDO")

    print(f"UTENTI ACCORDO: {users_accordo}")
    print(f"UTENTI DISACCORDO: {users_disaccordo}")

    # Lista completa degli oggetti disponibili
    oggetti_disponibili = [
        "Scatola di Fiammiferi",
        "Concentrato Alimentare",
        "Corda in nylon di 15 metri",
        "Paracadute di seta",
        "Unità di Riscaldamento Portatile",
        "Due pistole calibro .45",
        "Latte disidratato",
        "Bombole di ossigeno di 45kg",
        "Mappa delle stelle",
        "Zattera di salvataggio autogonfiabile",
        "Bussola Magnetica",
        "20 litri d'acqua",
        "Razzo di segnalazione",
        "Cassa di pronto soccorso",
        "Radiolina alimentata con energia solare"
    ]

    lista_oggetti_formattata = "\n".join([f"- {obj}" for obj in oggetti_disponibili])

    system_content = (
            "Sei un assistente che analizza le classifiche fornite da un gruppo di utenti. "
            "Gli utenti hanno stilato le classifiche degli oggetti fondamentali per la sopravvivenza sulla luna. "
            "Questa è la lista completa degli oggetti disponibili:\n" + lista_oggetti_formattata + "\n\n"
    )

    # Istruzioni per accordo
    if users_accordo:
        accordo_list = ", ".join(users_accordo)
        system_content += (
            f"IMPORTANTE: Devi essere in ACCORDO con questi utenti: {accordo_list}. "
            f"Sostieni e rafforza le loro classifiche e argomentazioni. "
        )

    # Istruzioni per disaccordo
    if users_disaccordo:
        disaccordo_list = ", ".join(users_disaccordo)
        system_content += (
            f"IMPORTANTE: Devi essere in DISACCORDO con questi utenti: {disaccordo_list}. "
            f"Esprimi cortesemente opinioni contrarie alle loro classifiche e argomentazioni. "
        )

    # Istruzioni per gestire conflitti
    if users_accordo and users_disaccordo:
        system_content += (
            "Quando ci sono opinioni contrastanti tra le classifiche, privilegia sempre le opinioni "
            "di coloro con cui devi essere d'accordo. "
        )

    # Istruzioni generali
    system_content += (
        "Mantieni una posizione COERENTE - non contraddire te stesso. "
        "NON fare mai riferimento a 'LLM' o 'Assistente' come se fosse un'altra persona - sei TU. "
        "Non dire mai frasi come 'Sono d'accordo con LLM' o 'Sono d'accordo con Assistente' "
        "perché TU SEI l'Assistente/LLM. "
        "Non spiegare il tuo ruolo o aggiungere note su cosa stai facendo - parla direttamente come partecipante. "
        "Quando un utente menziona uno di questi oggetti, assicurati di riconoscerlo come presente nella lista. "
        "NON dire che un oggetto non è incluso nella lista se è uno di quelli elencati sopra."
    )

    messages = [
        {
            "role": "system",
            "content": system_content
        }
    ]

    # Aggiunge le classifiche di tutti gli utenti
    for username, user_list in user_lists.items():
        messages.append({
            "role": "user",
            "content": f"Questa è la classifica dell'utente {username}: {user_list}"
        })

    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=messages,
        temperature=0.75,
        top_p=1,
        frequency_penalty=0.5,
        presence_penalty=0.2,
        stream=True,
        stop=None,
    )

    response = ""
    for chunk in completion:
        response += chunk.choices[0].delta.content or ""

    return f"LLM : '{response}'"


origins = [
    "http://localhost:8501",  # Streamlit app origin
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class ChatPartnerRequest(BaseModel):
    username: str
    chat_partner: str


class UpdateListRequest(BaseModel):
    username: str
    partner: str
    updated_list: list


class Message(BaseModel):
    from_user: str
    group_id: str = None
    to_user: str = None
    content: str


class Confirm(BaseModel):
    group_id: str
    username: str

class SyncListRequest(BaseModel):
    group_id: str
    username: str
    list: list


@app.post("/aggiorna_conferma")
async def update_status(request: Confirm):
    """
    Aggiorna lo stato di conferma di un utente nel gruppo.
    Quando tutti gli utenti confermano, imposta lo stato del gruppo su True.
    """
    group_id = request.group_id
    username = request.username

    # Inizializza il contatore di conferme per questo gruppo se non esiste
    if 'group_confirmations' not in manager.__dict__:
        manager.group_confirmations = {}

    if group_id not in manager.group_confirmations:
        manager.group_confirmations[group_id] = set()

    # Aggiunge l'utente al set di conferme
    manager.group_confirmations[group_id].add(username)

    # Verifica se tutti gli utenti hanno confermato
    if group_id in manager.groups:
        total_members = len(manager.groups[group_id])
        confirmed_members = len(manager.group_confirmations[group_id])

        # Se tutti hanno confermato, aggiorna lo stato del gruppo
        if confirmed_members == total_members:
            manager.conferma[group_id] = True

    return {"status": "Conferma aggiornata", "username": username}


@app.get("/get_shared_list/{group_id}")
async def get_shared_list_by_group(group_id: str):
    """
    Restituisce la lista condivisa per un gruppo specifico.
    """

    # Controlla se il gruppo esiste
    if group_id in manager.shared_lists:
        # Crea una copia profonda della lista per evitare problemi di riferimento
        shared_list = copy.deepcopy(manager.shared_lists[group_id])

        # Stampa anche l'ordine degli ID per verificare
        ids = [item['id'] for item in shared_list]

        return {
            "lista": shared_list,
            "status": manager.conferma.get(group_id, False),
            "timestamp": int(time.time() * 1000)
        }

    # Per retrocompatibilità, gestisce anche casi in cui group_id è un username
    if group_id in manager.chat_groups:
        # Se è un username, ottiene l'ID del gruppo
        group_id = manager.chat_groups[group_id]
        print(f"Convertito username in group_id: {group_id}")

    # Controlla se il gruppo esiste
    if group_id in manager.shared_lists:
        # Crea una copia profonda della lista per evitare problemi di riferimento
        shared_list = copy.deepcopy(manager.shared_lists[group_id])
        print(f"Lista trovata per gruppo {group_id} - {len(shared_list)} elementi")
        print(f"Primi elementi: {shared_list[:3]}")

        timestamp = int(time.time() * 1000)
        for item in shared_list:
            if 'last_modified' not in item:
                item['last_modified'] = timestamp

        return {
            "lista": shared_list,
            "status": manager.conferma.get(group_id, False),
            "timestamp": timestamp
        }
    else:
        if "-" in group_id:
            user1, user2 = group_id.split("-")
            key = tuple(sorted([user1, user2]))
            if key in manager.shared_lists:
                shared_list = copy.deepcopy(manager.shared_lists[key])
                print(f"Lista trovata per chat 1:1 {key} - {len(shared_list)} elementi")

                # Aggiorna i timestamp
                timestamp = int(time.time() * 1000)
                for item in shared_list:
                    if 'last_modified' not in item:
                        item['last_modified'] = timestamp

                return {
                    "lista": shared_list,
                    "status": manager.conferma.get(key, False),
                    "timestamp": timestamp
                }
    return {"lista": [], "status": False}


@app.get("/get_modalita/{group_id}/{username}")
async def get_modalita(group_id: str, username: str):
    """
    Ottiene la modalità di intervento per un utente in un gruppo.
    """
    # Determina la modalità per l'utente nel gruppo
    if group_id in manager.shared_modes:
        modo, target_user = manager.shared_modes[group_id]
        # Se l'utente è il target, restituisci la modalità
        if target_user == username:
            return {"modalita": modo}

    if "-" in group_id:
        user1, user2 = group_id.split("-")
        key = tuple(sorted([user1, user2]))
        if key in manager.shared_modes:
            modo, target_user = manager.shared_modes[key]
            if target_user == username:
                return {"modalita": modo}

    return {"modalita": "nessuna"}

@app.post("/api/previous_list")
async def previous_list(request: UpdateListRequest):
    """
    Aggiorna la lista precedente di un utente nel gruppo.
    """

    group_id = request.group_id
    username = request.username
    previous_list = request.previous_list

    # Per retrocompatibilità
    if not group_id and request.username and request.partner:
        pair_key = tuple(sorted((request.username, request.partner)))
        index = 0 if request.username < request.partner else 1

        with manager.lock:
            if pair_key not in manager.previous_lists.keys():
                manager.previous_lists[pair_key] = ["", ""]

            manager.previous_lists[pair_key][index] = previous_list
            print(f"Lista precedente aggiornata per {pair_key} (utente {request.username})")

        return {"status": "Previous list updated (compatibility mode)"}

    # Gestione per i gruppi
    with manager.lock:
        if group_id not in manager.previous_lists:
            # Inizializza la struttura per il gruppo se non esiste
            manager.previous_lists[group_id] = {}

        # Salva la lista precedente dell'utente
        manager.previous_lists[group_id][username] = previous_list
        print(f"Lista precedente aggiornata per gruppo {group_id}, utente {username}")

        # Controlla se tutti gli utenti hanno inviato le loro liste
        if group_id in manager.groups:
            expected_users = set(manager.groups[group_id])
            actual_users = set(manager.previous_lists[group_id].keys())

            # Se tutti hanno inviato le liste, si può generare un messaggio del LLM
            if expected_users.issubset(actual_users):
                # Ottieni tutte le liste
                user_lists = manager.previous_lists[group_id]

                # Genera una risposta iniziale del LLM
                response = initial_llm_query(group_id, user_lists)
                if response:
                    # Aggiunge la risposta alla chat
                    manager.chat_storage[group_id].append(response)
                    print(f"Risposta iniziale LLM aggiunta per gruppo {group_id}")

                    # Notifica tutti i membri del gruppo che l'LLM ha risposto
                    for member in manager.groups[group_id]:
                        try:
                            if member in manager.usernames:
                                await manager.usernames[member].send_text(json.dumps({
                                    "type": "new_message",
                                    "from_user": "LLM",
                                    "content": response,
                                    "group_id": group_id
                                }))
                                print(f"Notifica risposta iniziale inviata a {member}")
                        except Exception as e:
                            print(f"Errore nel notificare {member}: {e}")
                else:
                    print(f"Nessuna risposta iniziale generata per il gruppo {group_id}")

                # Aggiunge la risposta alla chat
                if group_id not in manager.chat_storage:
                    manager.chat_storage[group_id] = []

                manager.chat_storage[group_id].append(response)
                print(f"Aggiunta risposta iniziale LLM per gruppo {group_id}")

                # Notifica tutti i membri del gruppo che l'LLM ha risposto
                for member in manager.groups[group_id]:
                    try:
                        if member in manager.usernames:
                            await manager.usernames[member].send_text(json.dumps({
                                "type": "new_message",
                                "from_user": "LLM",
                                "content": response,
                                "group_id": group_id
                            }))
                    except Exception as e:
                        print(f"Errore nel notificare {member}: {e}")

        return {"status": "Previous list updated"}

class EditingLockRequest(BaseModel):
    group_id: str
    username: str
    action: str

class ConnectionManager:

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connected_users: List[str] = []
        self.usernames = {}

        self.chat_groups = {}
        self.groups = {}

        self.lock = Lock()
        self.shared_lists = {}
        self.previous_lists = {}
        self.shared_modes = {}
        self.group_requests = {}

        self.chat_storage = {}
        self.intervention_types = {}  # Memorizza il tipo di intervento per ogni chat
        self.intervention_times = {}  # Memorizza il momento dell'ultimo intervento
        self.conferma = {}

        self.chat_partners = {}
        self.questionnaire_scores = {}  # Memorizza i punteggi del questionario per ogni utente

        self.editing_locks = {}
        self.pending_disconnects = {}

    async def delayed_disconnect(self, username: str, websocket: WebSocket):
        """Disconnette con delay per gestire i reload"""
        self.pending_disconnects[username] = time.time()

        # Aspetta 3 secondi
        await asyncio.sleep(3)

        # Controlla se l'utente si è riconnesso nel frattempo
        if (username in self.pending_disconnects and
                username not in self.usernames):

            # Disconnessione reale
            print(f"Utente {username} disconnesso (confermato)")

            if username in self.connected_users:
                self.connected_users.remove(username)
            del self.pending_disconnects[username]

            await self.broadcast_user_list()

            # Notifica membri del gruppo
            if hasattr(self, 'chat_groups') and username in self.chat_groups:
                group_id = self.chat_groups[username]
                if hasattr(self, 'groups') and group_id in self.groups:
                    for member in self.groups[group_id]:
                        if member != username:
                            await self.safe_send_notification(member, {
                                "type": "group_member_disconnected",
                                "username": username,
                                "groupId": group_id
                            })
        else:
            # Era solo un reload
            if username in self.pending_disconnects:
                del self.pending_disconnects[username]

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()

    def disconnect(self, websocket: WebSocket, username: str):
        with self.lock:
            try:
                if websocket in self.active_connections:
                    self.active_connections.remove(websocket)
            except ValueError:
                pass

            try:
                if username in self.connected_users:
                    self.connected_users.remove(username)
            except ValueError:
                pass

            try:
                if username in self.usernames:
                    del self.usernames[username]
            except KeyError:
                pass
        print(f"Utente {username} disconnesso")

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"Errore durante il broadcast: {e}")

    async def broadcast_user_list(self):
        message = {
            "type": "user_list",
            "users": self.connected_users
        }
        json_message = json.dumps(message)

        # Crea una copia del dizionario per evitare race conditions
        usernames_copy = dict(self.usernames)

        for username, connection in usernames_copy.items():
            try:
                await connection.send_text(json_message)
            except Exception as e:
                # Rimuove la connessione fallita dal dizionario originale
                if username in self.usernames:
                    try:
                        del self.usernames[username]
                    except KeyError:
                        pass

    async def safe_send_notification(self, username: str, message: dict):
        """Invia una notifica in modo sicuro, gestendo connessioni chiuse"""
        if username in self.usernames:
            try:
                await self.usernames[username].send_text(json.dumps(message))
                return True
            except Exception as e:
                # Nasconde gli errori specifici di WebSocket già chiuso
                error_message = str(e).lower()
                if any(keyword in error_message for keyword in [
                    "unexpected asgi message",
                    "websocket.send",
                    "websocket.close",
                    "response already completed"
                ]):
                    # Non stampa questi errori specifici
                    pass
                else:
                    # Stampa altri tipi di errore
                    print(f"Errore nell'invio della notifica a {username}: {e}")

                # Rimuove la connessione fallita
                try:
                    del self.usernames[username]
                    if username in self.connected_users:
                        self.connected_users.remove(username)
                except (KeyError, ValueError):
                    pass
                return False
        return False

    async def send_request(self, to_username: str, from_username: str):
        """Invia una richiesta di chat da un utente a un altro"""
        if to_username in self.usernames:
            try:
                await self.usernames[to_username].send_text(
                    json.dumps({
                        "type": "request",
                        "fromUser": from_username
                    })
                )
                print(f"Richiesta inviata da {from_username} a {to_username}")
                return True
            except Exception as e:
                print(f"Errore nell'invio della richiesta: {e}")
                return False
        else:
            print(f"Utente {to_username} non trovato per l'invio della richiesta")
            return False


manager = ConnectionManager()


@app.get("/rest_connected_users")
def rest_connected_users():
    """Restituisce la lista degli utenti connessi"""
    return {"users": manager.connected_users}


@app.post("/rest_register_user")
def rest_register_user(data: dict):
    """Registra un utente attraverso l'API REST"""
    username = data.get("username")

    if not username:
        return {"status": "error", "message": "Username non fornito"}

    # Controllo case-insensitive
    username_lower = username.lower()
    connected_users_lower = [u.lower() for u in manager.connected_users]

    if username_lower in connected_users_lower:
        return {"status": "error", "message": f"Username '{username}' già in uso"}

    print(f"Registrazione utente: {username}")
    manager.connected_users.append(username)
    return {"status": "success", "message": f"Utente {username} registrato"}


@app.post("/rest_unregister_user")
def rest_unregister_user(data: dict):
    """Cancella un utente attraverso l'API REST"""
    username = data.get("username")

    if not username:
        return {"status": "error", "message": "Username non fornito"}

    if username in manager.connected_users:
        manager.connected_users.remove(username)
        print(f"Utente {username} rimosso")
        return {"status": "success", "message": f"Utente {username} rimosso"}

    return {"status": "error", "message": f"Utente {username} non trovato"}


@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    """
    Endpoint WebSocket per la connessione degli utenti.
    Gestisce la connessione, lo scambio di messaggi e la disconnessione.
    """

    await manager.connect(websocket, username)
    # Verifica se l'utente è già connesso
    if username not in manager.connected_users:
        manager.active_connections.append(websocket)
        manager.connected_users.append(username)
        manager.usernames[username] = websocket
        print(f"Utente {username} connesso via WebSocket")
    else:
        # Aggiorna il WebSocket per l'utente esistente
        manager.usernames[username] = websocket

    # Verifica se l'utente è già in un gruppo
    if username in manager.chat_groups:
        group_id = manager.chat_groups[username]
        if group_id in manager.groups:
            members = manager.groups[group_id]
            print(f"Utente {username} già in gruppo {group_id} con membri: {members}")

            # Invia una notifica di gruppo esistente
            try:
                await websocket.send_text(json.dumps({
                    "type": "group_info",
                    "groupId": group_id,
                    "members": members
                }))

                for member in members:
                    if member != username and member in manager.usernames:
                        await manager.usernames[member].send_text(json.dumps({
                            "type": "group_members_update",
                            "groupId": group_id,
                            "members": members
                        }))
                        print(f"Notifica aggiornamento membri inviata a {member}")
            except Exception as e:
                print(f"Errore nell'invio delle informazioni di gruppo: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Dati ricevuti da {username}: {data}")
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                print(f"Errore nel parsing JSON: {data}")
                message = {"type": "unknown"}

            # Gestione per la richiesta esplicita della lista utenti
            if message.get('type') == 'request_user_list':
                print(f"Richiesta lista utenti da {username}")
                users_message = {
                    "type": "user_list",
                    "users": manager.connected_users
                }
                await websocket.send_text(json.dumps(users_message))
                print(f"Lista utenti inviata a {username}: {manager.connected_users}")

            elif message.get('type') == 'request_group_members':
                group_id = message.get('groupId')
                if group_id and group_id in manager.groups:
                    # Invia la lista aggiornata dei membri
                    members = manager.groups[group_id]
                    await websocket.send_text(json.dumps({
                        "type": "group_members_response",
                        "groupId": group_id,
                        "members": members
                    }))
                    print(f"Lista membri richiesta per gruppo {group_id}: {members}")

            elif message.get('type') == 'request':
                to_user = message.get('toUser')
                print(f"Richiesta di chat da {username} a {to_user}")

                if to_user in manager.usernames:
                    await manager.send_request(to_user, username)
                else:
                    print(f"Utente destinatario {to_user} non trovato")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Utente {to_user} non trovato o non connesso"
                    }))

            elif message.get('type') == 'response':
                to_user = message['toUser']
                response = message['response']

                if response == 'accept':
                    # Crea una connessione di chat tra gli utenti
                    user1, user2 = sorted([username, to_user])
                    chat_key = f"{user1}-{user2}"

                    # Verifica se l'utente è già in un gruppo
                    if username in manager.chat_groups:
                        old_group_id = manager.chat_groups[username]
                        print(f"Utente {username} già in gruppo {old_group_id}, rimuovendo...")

                        # Rimuove l'utente dal gruppo precedente
                        if old_group_id in manager.groups:
                            if username in manager.groups[old_group_id]:
                                manager.groups[old_group_id].remove(username)

                            # Se il gruppo è vuoto, rimuovilo
                            if not manager.groups[old_group_id]:
                                del manager.groups[old_group_id]
                                print(f"Gruppo {old_group_id} rimosso perché vuoto")

                    # Inizializza le strutture dati per questa chat
                    if not hasattr(manager, 'chat_storage'):
                        manager.chat_storage = {}

                    if chat_key not in manager.chat_storage:
                        manager.chat_storage[chat_key] = []

                    # Salva l'associazione utente-partner
                    if not hasattr(manager, 'chat_partners'):
                        manager.chat_partners = {}

                    manager.chat_partners[to_user] = username
                    manager.chat_partners[username] = to_user

                    # Inizializza shared_lists se non esiste
                    if not hasattr(manager, 'shared_lists'):
                        manager.shared_lists = {}

                    pair_key = tuple(sorted((to_user, username)))
                    if pair_key not in manager.shared_lists:
                        manager.shared_lists[pair_key] = []

                    # Notifica gli utenti che la chat è stata creata
                    if to_user in manager.usernames:
                        # Notifica all'utente che ha ricevuto la richiesta
                        await manager.usernames[to_user].send_text(json.dumps({
                            "type": "chat_created",
                            "partner": username
                        }))

                    # Notifica al mittente che ha inviato la richiesta
                    await websocket.send_text(json.dumps({
                        "type": "chat_created",
                        "partner": to_user
                    }))

                    print(f"Chat creata tra {username} e {to_user}")

            elif message.get('type') == 'group_response':
                group_id = message.get('groupId')
                response = message.get('response')

                if group_id in manager.pending_group_requests:
                    request = manager.pending_group_requests[group_id]

                    if response == 'accept':
                        # Aggiunge l'utente al gruppo
                        if username not in request['accepted']:
                            request['accepted'].append(username)
                        print(f"Utente {username} ha accettato l'invito per il gruppo {group_id}")
                        print(f"Membri accettati: {request['accepted']}")
                        print(f"Membri invitati totali: {len(request['invited']) + 1}")

                        # Se si hanno almeno 2 membri (il creatore più chi ha accettato), si può creare il gruppo
                        if len(request['accepted']) >= 2:
                            members = request['accepted']
                            creator = request.get('creator')

                            # Verifica se qualcuno è già in altri gruppi
                            for member in members:
                                if member in manager.chat_groups:
                                    old_group_id = manager.chat_groups[member]
                                    print(f"Utente {member} già in gruppo {old_group_id}, rimuovendo...")

                                    # Rimuove il membro dal vecchio gruppo
                                    if old_group_id in manager.groups and member in manager.groups[old_group_id]:
                                        manager.groups[old_group_id].remove(member)

                                    # Se il vecchio gruppo è vuoto, lo rimuove
                                    if old_group_id in manager.groups and not manager.groups[old_group_id]:
                                        del manager.groups[old_group_id]
                                        print(f"Gruppo {old_group_id} rimosso perché vuoto")

                            print(f"Creazione gruppo {group_id} con membri: {members}")

                            # Crea il gruppo
                            if not hasattr(manager, 'groups'):
                                manager.groups = {}

                            # Usa una copia della lista per evitare problemi di riferimento
                            manager.groups[group_id] = members.copy()

                            # Associa ogni utente al gruppo
                            if not hasattr(manager, 'chat_groups'):
                                manager.chat_groups = {}
                            for member in members:
                                manager.chat_groups[member] = group_id

                            # Inizializza le strutture dati per il gruppo
                            if not hasattr(manager, 'shared_lists'):
                                manager.shared_lists = {}
                            manager.shared_lists[group_id] = items

                            if not hasattr(manager, 'chat_storage'):
                                manager.chat_storage = {}
                            manager.chat_storage[group_id] = []

                            if not hasattr(manager, 'conferma'):
                                manager.conferma = {}
                            manager.conferma[group_id] = False


                            # Notifica tutti i membri che il gruppo è stato creato
                            for member in members:
                                if member in manager.usernames:
                                    try:
                                        await manager.usernames[member].send_text(json.dumps({
                                            "type": "group_created",
                                            "groupId": group_id,
                                            "members": members
                                        }))
                                        print(f"Notifica di gruppo creato inviata a {member}")

                                        await manager.usernames[member].send_text(json.dumps({
                                            "type": "group_members_update",
                                            "groupId": group_id,
                                            "members": members  # Invia la lista completa
                                        }))
                                        print(f"Aggiornamento membri inviato a {member}")

                                    except Exception:
                                        pass

                            # Rimuove la richiesta dalla lista delle richieste in sospeso se tutti hanno accettato
                            if len(request['accepted']) == len(request['invited']) + 1:  # +1 per il creatore
                                del manager.pending_group_requests[group_id]
                                print(f"Gruppo {group_id} rimosso da pending_group_requests - tutti hanno accettato")

                            # Determina se tutti hanno accettato
                            all_accepted = len(request['accepted']) == len(request['invited']) + 1

                            if not all_accepted:
                                for existing_member in members:
                                    if existing_member != username and existing_member in manager.usernames:
                                        try:
                                            await manager.usernames[existing_member].send_text(json.dumps({
                                                "type": "group_member_joined",
                                                "username": username,
                                                "groupId": group_id,
                                                "members": members  # Lista completa e aggiornata
                                            }))
                                            print(f"Notifica nuovo membro inviata a {existing_member}")
                                        except Exception:
                                            pass
                            return {
                                "status": "success",
                                "message": "Gruppo creato con successo",
                                "group_id": group_id,
                                "all_accepted": all_accepted
                            }
                        else:
                            # Non tutti hanno ancora accettato
                            return {
                                "status": "success",
                                "message": "Utente aggiunto al gruppo in attesa",
                                "all_accepted": False,
                                "group_id": group_id
                            }

    except WebSocketDisconnect:
        asyncio.create_task(manager.delayed_disconnect(username, websocket))

    except Exception as e:
        print(f"Errore nell'endpoint WebSocket per {username}: {e}")
        import traceback
        traceback.print_exc()

        # Solo delayed disconnect, nessuna notifica immediata
        asyncio.create_task(manager.delayed_disconnect(username, websocket))



@app.get("/connected_users")
async def get_connected_users():
    return manager.connected_users


@app.get("/api/active_users")
async def get_active_users():
    """Endpoint REST per ottenere la lista degli utenti attivi"""
    return {"users": manager.connected_users}


# Endpoint per controllare lo stato di un utente
@app.get("/check_user/{username}")
def check_user(username: str):
    """Verifica se un utente è connesso"""
    is_connected = username in manager.connected_users
    return {"username": username, "connected": is_connected}


@app.get("/get_chat_partner/{username}")
async def get_chat_partner(username: str):
    """Ottiene il partner di chat di un utente"""
    if not hasattr(manager, 'chat_partners'):
        manager.chat_partners = {}

    if username in manager.chat_partners:
        partner = manager.chat_partners[username]
        print(f"Partner trovato per {username}: {partner}")
        return {"chat_partner": partner}
    else:
        return {"chat_partner": None}


@app.get("/get_shared_list_by_user/{username}")
async def get_shared_list_by_user(username: str):
    partner = manager.chat_partners[username]
    key = tuple(sorted((username, partner)))
    if (key not in manager.conferma.keys()):
        print("Eccola, non trovo la chiave")
    if (key in manager.shared_lists.keys()):
        return {"lista": manager.shared_lists[key], "status": manager.conferma[key]}


@app.get("/debug_chat_mode/{user1}/{user2}")
async def debug_chat_mode(user1: str, user2: str):
    """Endpoint di debug per verificare la modalità corrente dell'IA"""
    chat_key = f"{user1}-{user2}" if user1 < user2 else f"{user2}-{user1}"
    key = tuple(sorted((user1, user2)))

    if key in manager.shared_modes:
        modo, utente = manager.shared_modes[key]
        return {
            "chat_key": chat_key,
            "modalita": modo,
            "utente_target": utente,
            "messaggio": f"L'IA è in {modo} con l'utente {utente}"
        }
    else:
        return {"error": "Modalità non trovata per questa chat"}


@app.get("/get_messages/{user1}/{user2}")
async def get_messages(user1: str, user2: str):
    chat_key = f"{user1}-{user2}" if user1 < user2 else f"{user2}-{user1}"
    messages = manager.chat_storage.get(chat_key, [])
    return {"messages": messages}


@app.post("/send_message")
async def send_message(message: Message):
    """
    Gestisce l'invio di un messaggio nella chat di gruppo.
    """
    # Determina il gruppo
    group_id = message.group_id
    if not group_id and message.to_user:
        # Per retrocompatibilità, supporta ancora le chat 1:1 della versione precedente del codice
        user1, user2 = sorted([message.from_user, message.to_user])
        chat_key = f"{user1}-{user2}"
        group_id = chat_key


    # Inizializza lo storage della chat se necessario
    if group_id not in manager.chat_storage:
        manager.chat_storage[group_id] = []
        print(f"Creato nuovo chat_storage per {group_id}")

    if not hasattr(manager, 'shared_lengths'):
        manager.shared_lengths = {}
    if group_id not in manager.shared_lengths:
        manager.shared_lengths[group_id] = [0, 0]

    # Aggiunge il messaggio alla chat
    formatted_message = f"{message.from_user}: {message.content}"
    manager.chat_storage[group_id].append(formatted_message)

    # Determina i destinatari
    recipients = []
    if group_id in manager.groups:
        # Chat di gruppo
        recipients = [user for user in manager.groups[group_id] if user != message.from_user]
    elif message.to_user:
        # Chat 1:1 (retrocompatibilità)
        recipients = [message.to_user]

    # Invia il messaggio a tutti i destinatari
    for recipient in recipients:
        try:
            recipient_ws = manager.usernames.get(recipient)
            if recipient_ws:
                notification = {
                    "type": "new_message",
                    "from_user": message.from_user,
                    "content": message.content,
                    "group_id": group_id
                }
                await recipient_ws.send_text(json.dumps(notification))
        except Exception as e:
            if not should_suppress_websocket_error(e):
                print(f"Errore nell'invio del messaggio a {recipient}: {e}")

    try:
        # Verifica se l'ultimo messaggio è dell'IA
        last_message = manager.chat_storage[group_id][-1] if len(manager.chat_storage[group_id]) > 1 else None
        if last_message and "LLM :" in last_message:
            print("L'ultimo messaggio è già dell'IA, salto l'intervento")
            return {"status": "Message sent"}

        # Inizializza o aggiorna il contatore dei messaggi per questo gruppo
        if group_id not in manager.shared_lengths:
            manager.shared_lengths[group_id] = [0, 0]

        old_length = manager.shared_lengths[group_id][0]
        current_length = len(manager.chat_storage[group_id])
        manager.shared_lengths[group_id][1] = current_length

        # Intervento dell'IA ogni tre messaggi
        if (current_length - old_length >= 3):
            manager.shared_lengths[group_id][0] = current_length

            # Ottiene gli ultimi tre messaggi per l'analisi
            latest_messages = []
            start_index = max(0, old_length)
            for i in range(start_index, current_length):
                latest_messages.append(manager.chat_storage[group_id][i])

            if latest_messages:
                llm_response = ask_llm(latest_messages, group_id, None)
                manager.chat_storage[group_id].append(llm_response)

                # Invia la risposta dell'IA a tutti i membri del gruppo
                group_members = []
                if group_id in manager.groups:
                    group_members = manager.groups[group_id]
                elif message.to_user:  # Retrocompatibilità per chat 1:1
                    group_members = [message.from_user, message.to_user]

                for participant in group_members:
                    participant_ws = manager.usernames.get(participant)
                    if participant_ws:
                        try:
                            await participant_ws.send_text(json.dumps({
                                "type": "new_message",
                                "from_user": "LLM",
                                "content": llm_response,
                                "group_id": group_id
                            }))
                            print(f"Risposta LLM inviata a {participant}")
                        except Exception as e:
                            if not should_suppress_websocket_error(e):
                                print(f"Errore nell'invio della risposta LLM a {participant}: {e}")

                # Aggiorna il tipo di intervento per riferimenti futuri
                manager.intervention_types[group_id] = "simple_message_count"

        # Controlla messaggi ripetitivi
        is_repetitive = check_simple_repetitive_message(group_id, message.from_user)
        if is_repetitive:
            reminder = (
                "LLM: Ricordate che questo è un test sulla creazione di una classifica collaborativa. "
                "Per favore, cercate di inviare messaggi pertinenti alla discussione sugli oggetti "
                "da ordinare per importanza nella sopravvivenza sulla luna."
            )
            manager.chat_storage[group_id].append(reminder)

            # Invia il reminder a tutti i membri del gruppo
            group_members = []
            if group_id in manager.groups:
                group_members = manager.groups[group_id]
            elif message.to_user:
                group_members = [message.from_user, message.to_user]

            for participant in group_members:
                participant_ws = manager.usernames.get(participant)
                if participant_ws:
                    try:
                        await participant_ws.send_text(json.dumps({
                            "type": "new_message",
                            "from_user": "LLM",
                            "content": reminder,
                            "group_id": group_id
                        }))
                    except Exception:
                        pass

            print("Aggiunto avviso per messaggi ripetitivi")
            return {"status": "Message sent with reminder"}

    except Exception as e:
        print(f"Errore nella logica di intervento IA: {e}")

    return {"status": "Message sent"}

def check_simple_repetitive_message(group_id, sender):
    """
    Controlla solo gli ultimi 3 messaggi dello stesso utente.
    """
    try:
        # Raccoglie gli ultimi messaggi dell'utente
        user_messages = []
        recent_messages = manager.chat_storage.get(group_id, [])[-5:]  # Solo ultimi 5 messaggi

        for msg in recent_messages:
            parts = msg.split(":", 1)
            if len(parts) == 2 and parts[0].strip() == sender:
                content = parts[1].strip().lower()
                user_messages.append(content)

        # Verifica se ci sono almeno 3 messaggi identici negli ultimi messaggi
        if len(user_messages) >= 3:
            if user_messages[-1] == user_messages[-2] == user_messages[-3]:
                return True

        # Verifica saluti ripetuti
        if len(user_messages) >= 2:
            greetings = ["ciao", "salve", "ehi", "hey", "hi", "hello"]
            recent_greetings = sum(1 for msg in user_messages[-3:] if msg.strip() in greetings)
            if recent_greetings >= 2:
                return True

        return False

    except Exception as e:
        print(f"Errore nel controllo messaggi ripetitivi: {e}")
        return False

@app.post("/api/previous_list")
async def previous_list(request: UpdateListRequest):
    index = 0
    pair_key = tuple(sorted((request.username, request.partner)))

    if (request.username > request.partner):
        index = 1
    with manager.lock:
        if pair_key not in manager.previous_lists.keys():
            print("Errore : non ho inserito la chiave in previous lists")
            # Inizializza se non esiste
            manager.previous_lists[pair_key] = ["", ""]

            # Aggiorna la lista precedente
            manager.previous_lists[pair_key][index] = request.updated_list
            print(f"Lista precedente aggiornata per {pair_key}")

        return {"status": "Previous list updated"}

@app.get("/get_modalita/{username}/{partner}")
async def get_modalita(username: str, partner: str):
    key = tuple(sorted((username, partner)))
    utente = manager.shared_modes[key][1]
    modalita = manager.shared_modes[key][0]
    if (utente == username):
        return {"modalita": modalita}
    else:
        return {"modalita": "nessuna"}


@app.get("/get_intervention_type/{user1}/{user2}")
async def get_intervention_type(user1: str, user2: str):
    """Ottiene il tipo di intervento per chat 1:1"""
    chat_key = f"{user1}-{user2}" if user1 < user2 else f"{user2}-{user1}"

    #il tipo è sempre "Ogni 3 messaggi"
    return {"intervention_type": "Ogni 3 messaggi"}


@app.get("/get_group_intervention_type/{group_id}")
async def get_group_intervention_type(group_id: str):
    """Ottieni il tipo di intervento per chat di gruppo"""

    #il tipo è sempre "Ogni 3 messaggi"
    return {"intervention_type": "Ogni 3 messaggi"}

@app.on_event("startup")
async def startup_event():
    """Inizializza le variabili necessarie all'avvio del server"""
    print("=== Avvio del server FastAPI ===")
    print(f"Ora: {datetime.datetime.now()}")

    # Inizializza la lista di utenti connessi
    if not hasattr(manager, 'connected_users'):
        manager.connected_users = []

    if not hasattr(manager, 'chat_partners'):
        manager.chat_partners = {}

    if not hasattr(manager, 'usernames'):
        manager.usernames = {}

    if not hasattr(manager, 'group_feedback'):
        manager.group_feedback = {}

    if not hasattr(manager, 'group_feedback_averages'):
        manager.group_feedback_averages = {}

    if not hasattr(manager, 'group_aggregated_feedback'):
        manager.group_aggregated_feedback = {}

    if not hasattr(manager, 'group_overall_average'):
        manager.group_overall_average = {}

    if not hasattr(manager, 'group_questionnaire_completions'):
        manager.group_questionnaire_completions = {}

    print("Server pronto per accettare connessioni")
    print("================================")


@app.get("/get_group/{username}")
async def get_group(username: str):
    """Ottiene informazioni sul gruppo di un utente"""
    try:
        if username in manager.chat_groups:
            group_id = manager.chat_groups[username]
            if group_id in manager.groups:

                members = [str(member) for member in manager.groups[group_id] if member]
                return {
                    "group_id": group_id,
                    "members": members
                }
        return {"group_id": None, "members": []}
    except Exception as e:
        print(f"Errore in get_group: {e}")
        return {"group_id": None, "members": [], "error": str(e)}


@app.get("/get_group_messages/{group_id}")
async def get_group_messages(group_id: str):
    """Ottiene i messaggi di un gruppo"""
    messages = manager.chat_storage.get(group_id, [])
    return {"messages": messages}


@app.on_event("shutdown")
async def shutdown_event():
    """Pulisce le risorse quando il server viene spento"""
    print("=== Spegnimento del server FastAPI ===")

    print("Risorse pulite")
    print("================================")

@app.get("/health")
async def health_check():
    """
    Endpoint di health check per verificare che il server sia attivo
    """
    return {
        "status": "ok",
        "timestamp": datetime.datetime.now().isoformat(),
        "users_count": len(manager.connected_users),
        "active_chats": len(manager.chat_partners) // 2,  # ogni chat ha 2 partner
    }


class SendRequestModel(BaseModel):
    from_user: str
    to_user: str
    is_group: bool = False
    group_id: str = None


class ResponseRequestModel(BaseModel):
    request_id: str
    from_user: str
    to_user: str
    response: str
    group_id: Optional[str] = None


@app.post("/send_request")
async def send_request_endpoint(request: SendRequestModel):
    """Endpoint per inviare una richiesta di chat"""
    from_user = request.from_user
    to_user = request.to_user
    is_group = request.is_group if hasattr(request, 'is_group') else False
    group_id = request.group_id if hasattr(request, 'group_id') else None

    # Verifica dei parametri
    if not from_user or not to_user:
        return {"status": "error", "message": "Parametri mancanti"}

    # Genera un ID univoco per la richiesta
    request_id = f"req_{from_user}_{to_user}_{int(time.time())}"

    # Inizializza la struttura dati per le richieste in attesa se non esiste
    if not hasattr(manager, 'pending_requests'):
        manager.pending_requests = {}

    # Salva la richiesta
    if to_user not in manager.pending_requests:
        manager.pending_requests[to_user] = []

    # Aggiunge la richiesta alla lista delle richieste in attesa
    request_data = {
        "request_id": request_id,
        "from_user": from_user,
        "timestamp": time.time(),
        "is_group": is_group
    }

    # Aggiunge il group_id solo se è presente
    if group_id:
        request_data["group_id"] = group_id

    manager.pending_requests[to_user].append(request_data)

    # Invia la richiesta via WebSocket se l'utente è connesso
    try:
        if to_user in manager.usernames:
            notification = {
                "type": "request",
                "fromUser": from_user,
                "requestId": request_id,
                "isGroup": is_group
            }

            # Aggiunge il group_id alla notifica se è presente
            if group_id:
                notification["groupId"] = group_id

            await manager.usernames[to_user].send_text(json.dumps(notification))
    except Exception as e:
        print(f"Errore nell'invio della richiesta via WebSocket: {e}")

    # Se è una richiesta di gruppo, tiene traccia degli inviti
    if is_group:
        # Inizializza la struttura per gli inviti di gruppo
        if not hasattr(manager, 'group_invitations'):
            manager.group_invitations = {}

        # Usa il group_id fornito o crea un nuovo ID se non esiste
        current_group_id = group_id or f"group_{from_user}_{int(time.time())}"

        # Inizializza il gruppo se non esiste
        if current_group_id not in manager.group_invitations:
            manager.group_invitations[current_group_id] = {
                'creator': from_user,
                'invited': [to_user],
                'accepted': [from_user],  # Il creatore è già accettato
                'pending': [to_user]
            }
        else:
            # Aggiungi il nuovo invitato al gruppo esistente
            if to_user not in manager.group_invitations[current_group_id]['invited']:
                manager.group_invitations[current_group_id]['invited'].append(to_user)
            if to_user not in manager.group_invitations[current_group_id]['pending']:
                manager.group_invitations[current_group_id]['pending'].append(to_user)

    return {"status": "success", "request_id": request_id, "group_id": group_id}


@app.post("/create_group")
async def create_group(data: dict):
    """
    Crea un nuovo gruppo con i membri specificati.
    Utile per forzare la creazione di un gruppo quando i meccanismi automatici falliscono.
    """
    creator = data.get("creator")
    members = data.get("members", [])
    group_id = data.get("group_id")  # Possibilità di fornire un ID gruppo specifico

    if not creator:
        return {"status": "error", "message": "Creatore del gruppo non specificato"}

    if not members:
        members = [creator]  # Se non ci sono membri, usa solo il creatore
    elif creator not in members:
        members.append(creator)  # Assicura che il creatore sia sempre nella lista dei membri

    # Assicura che tutti i membri siano rappresentati come stringhe
    members = [str(member) for member in members if member]

    try:
        # Crea un ID unico per il gruppo se non fornito
        if not group_id:
            group_id = f"group_{int(time.time())}_{random.randint(1000, 9999)}"

        # Registra il gruppo
        manager.groups[group_id] = members.copy()

        # Associa ogni utente al gruppo
        for member in members:
            manager.chat_groups[member] = group_id

        # Inizializza le strutture dati per il gruppo
        manager.shared_lists[group_id] = items  # Usa la lista di item predefinita
        manager.chat_storage[group_id] = []
        manager.conferma[group_id] = False

        print(f"Gruppo {group_id} creato con membri: {members}")
        print(f"Verifica membri inseriti: {manager.groups[group_id]}")

        # Notifica tutti i membri connessi (solo se ci sono più di 1 membro)
        for member in members:
            if member in manager.usernames:
                try:
                    await manager.usernames[member].send_text(json.dumps({
                        "type": "group_created",
                        "groupId": group_id,
                        "members": members
                    }))
                except Exception as e:
                    print(f"Errore nella notifica a {member}: {e}")

        return {"status": "success", "group_id": group_id, "members": members}

    except Exception as e:
        print(f"Errore nella creazione del gruppo: {e}")
        import traceback
        print(traceback.format_exc())
        return {"status": "error", "message": f"Errore nella creazione del gruppo: {str(e)}"}


@app.get("/check_pending_requests/{username}")
async def check_pending_requests(username: str):
    """Endpoint per controllare le richieste in attesa per un utente"""
    try:
        # Inizializza la struttura se non esiste
        if not hasattr(manager, 'pending_requests'):
            manager.pending_requests = {}

        # Assicura che username esista nelle pending_requests
        if username not in manager.pending_requests:
            manager.pending_requests[username] = []

        # Ottiene le richieste
        pending = manager.pending_requests.get(username, [])

        # Filtra le richieste vecchie
        current_time = time.time()
        valid_requests = [req for req in pending if req is not None and current_time - req.get("timestamp", 0) < 600]

        # Aggiorna la lista
        manager.pending_requests[username] = valid_requests

        return {"pending_requests": valid_requests}
    except Exception as e:
        # In caso di errore, log e ritorna lista vuota
        print(f"Errore nel check_pending_requests: {e}")
        return {"pending_requests": []}


@app.post("/response_request")
async def response_request_endpoint(request: ResponseRequestModel):
    """Endpoint per rispondere a una richiesta di chat"""
    try:
        request_id = request.request_id
        from_user = request.from_user
        to_user = request.to_user
        response = request.response

        if response != "accept":
            return {"status": "error", "message": "Solo le richieste di accettazione sono permesse"}

        # Gestisce il group_id se presente nella richiesta, altrimenti sarà None
        group_id = request.group_id if hasattr(request, 'group_id') and request.group_id else None

        # Verifica che tutte le strutture dati esistano
        if not hasattr(manager, 'pending_requests'):
            manager.pending_requests = {}
            return {"status": "error", "message": "Nessuna richiesta in attesa: struttura dati non inizializzata"}

        if not hasattr(manager, 'pending_group_requests'):
            manager.pending_group_requests = {}

        # Verifica che la richiesta esista
        if to_user not in manager.pending_requests:
            return {"status": "error", "message": f"Nessuna richiesta in attesa per {to_user}"}

        pending = manager.pending_requests[to_user]

        # Se non ci sono richieste pendenti
        if not pending:
            return {"status": "error", "message": f"Nessuna richiesta attiva trovata per {to_user}"}

        request_index = None
        request_data = None

        for i, req in enumerate(pending):
            if req and req.get("request_id") == request_id:
                request_index = i
                request_data = req
                break

        if request_index is None:
            return {"status": "error", "message": f"Richiesta {request_id} non trovata"}

        # Rimuove la richiesta dalla lista
        pending.pop(request_index)

        # Gestisce la risposta
        if response == "accept":
            is_group = request_data.get("is_group", False)

            # Usa group_id dalla richiesta o dal request_data
            if not group_id:
                group_id = request_data.get("group_id")

            if is_group and group_id:
                # Verifica se esiste già un pending_group_request per questo gruppo
                if group_id not in manager.pending_group_requests:
                    # Inizializza una nuova richiesta di gruppo
                    manager.pending_group_requests[group_id] = {
                        'creator': from_user,
                        'invited': [],
                        'accepted': [from_user],  # Il creatore è già accettato
                        'status': 'pending'
                    }

                # Aggiunge l'utente che ha accettato alla lista degli accettati
                if to_user not in manager.pending_group_requests[group_id]['accepted']:
                    manager.pending_group_requests[group_id]['accepted'].append(to_user)

                # Aggiunge l'utente alla lista degli invitati se non c'è già
                if to_user not in manager.pending_group_requests[group_id]['invited']:
                    manager.pending_group_requests[group_id]['invited'].append(to_user)

                # Calcola il totale degli invitati e il totale accettato
                creator = manager.pending_group_requests[group_id].get('creator')
                all_invited = manager.pending_group_requests[group_id].get('invited', [])
                total_expected = len(all_invited) + 1  # +1 per il creatore
                total_accepted = len(manager.pending_group_requests[group_id]['accepted'])

                # Crea il gruppo solo se hanno accettato tutti gli invitati
                if total_accepted == total_expected:
                    members = manager.pending_group_requests[group_id]['accepted']

                    # Crea il gruppo
                    if not hasattr(manager, 'groups'):
                        manager.groups = {}

                    # Assicura che tutti i membri siano stringhe e unici
                    members = [str(m) for m in members if m]
                    members = list(set(members))

                    manager.groups[group_id] = members

                    # Associa ogni utente al gruppo
                    if not hasattr(manager, 'chat_groups'):
                        manager.chat_groups = {}
                    for member in members:
                        manager.chat_groups[member] = group_id

                    # Inizializza le strutture dati per il gruppo
                    if not hasattr(manager, 'shared_lists'):
                        manager.shared_lists = {}
                    manager.shared_lists[group_id] = items

                    if not hasattr(manager, 'chat_storage'):
                        manager.chat_storage = {}
                    manager.chat_storage[group_id] = []

                    if not hasattr(manager, 'conferma'):
                        manager.conferma = {}
                    manager.conferma[group_id] = False


                    # Notifica tutti i membri
                    for member in members:
                        if member in manager.usernames:
                            try:
                                await manager.usernames[member].send_text(json.dumps({
                                    "type": "group_created",
                                    "groupId": group_id,
                                    "members": members
                                }))
                            except Exception as e:
                                pass

                    # Rimuove dalle richieste in sospeso
                    del manager.pending_group_requests[group_id]

                    return {
                        "status": "success",
                        "message": "Gruppo creato con successo",
                        "group_id": group_id,
                        "all_accepted": True
                    }
                else:
                    # Non tutti hanno ancora accettato, invia notifiche ma non crea il gruppo
                    print(f"[DEBUG] Non tutti i membri hanno accettato, attesa...")

                    # Invia notifica agli altri membri
                    for member in manager.pending_group_requests[group_id]['accepted']:
                        if member != to_user and member in manager.usernames:
                            try:
                                await manager.usernames[member].send_text(json.dumps({
                                    "type": "group_member_accepted",
                                    "acceptedUser": to_user,
                                    "groupId": group_id,
                                    "totalAccepted": total_accepted,
                                    "totalInvited": total_expected
                                }))
                            except Exception as e:
                                pass

                    return {
                        "status": "success",
                        "message": "Utente aggiunto al gruppo in attesa",
                        "all_accepted": False,
                        "group_id": group_id
                    }

    except Exception as e:
        import traceback
        print(f"[ERROR] Exception in response_request_endpoint: {e}")
        print(traceback.format_exc())
        return {"status": "error", "message": f"Errore interno del server: {str(e)}"}


@app.get("/debug_pending_requests")
async def debug_pending_requests():
    """Endpoint di debug per vedere tutte le richieste pendenti"""
    if not hasattr(manager, 'pending_requests'):
        return {"status": "empty", "pending_requests": {}}

    # Converte la struttura dati in un formato serializzabile
    serializable_pending = {}
    for username, requests in manager.pending_requests.items():
        serializable_pending[username] = []
        for req in requests:
            serializable_req = {
                "request_id": req.get("request_id"),
                "from_user": req.get("from_user"),
                "timestamp": req.get("timestamp"),
                "is_group": req.get("is_group", False)
            }
            serializable_pending[username].append(serializable_req)

    return {"status": "ok", "pending_requests": serializable_pending}


@app.post("/send_group_request")
async def send_group_request(data: dict):
    """
    Invia richieste di gruppo a più utenti contemporaneamente.
    """
    creator = data.get("from_user")
    to_users = data.get("to_users", [])

    if not creator or not to_users:
        return {"status": "error", "message": "Parametri mancanti"}

    # Genera un ID univoco per il gruppo
    group_id = f"group_{creator}_{int(time.time())}"

    # Inizializza la richiesta di gruppo
    manager.pending_group_requests[group_id] = {
        'creator': creator,
        'invited': to_users,
        'accepted': [creator],  # Il creatore è già nel gruppo
        'status': 'pending'
    }

    print(f"Creata richiesta di gruppo {group_id} da {creator} per {to_users}")

    # Invia la richiesta a tutti i destinatari
    success_count = 0
    for to_user in to_users:
        try:
            if to_user in manager.usernames:
                await manager.usernames[to_user].send_text(json.dumps({
                    "type": "group_request",
                    "fromUser": creator,
                    "groupId": group_id
                }))
                success_count += 1
                print(f"Richiesta di gruppo inviata a {to_user}")
            else:
                print(f"Utente {to_user} non connesso")
        except Exception as e:
            print(f"Errore nell'invio della richiesta a {to_user}: {e}")

    return {
        "status": "success",
        "group_id": group_id,
        "sent_to": success_count,
        "total": len(to_users)
    }


@app.get("/get_group/{group_id}/members")
async def get_group_members(group_id: str):
    """Ottiene direttamente i membri di un gruppo specifico"""
    try:
        if group_id in manager.groups:
            # Si assicura che tutti i membri siano rappresentati come stringhe
            members = [str(member) for member in manager.groups[group_id] if member]
            return {"members": members}
        else:
            # Gestisce anche il caso di chat 1:1
            if "-" in group_id:
                user1, user2 = group_id.split("-")
                return {"members": [user1, user2]}

        return {"members": []}
    except Exception as e:
        print(f"Errore in get_group_members: {e}")
        return {"members": [], "error": str(e)}


@app.post("/create_pending_group")
async def create_pending_group(data: dict):
    """
    Inizializza un gruppo in attesa che tutti gli utenti accettino.
    """
    creator = data.get("creator")
    members_to_invite = data.get("members_to_invite", [])
    group_id = data.get("group_id")

    if not creator or not group_id:
        return {"status": "error", "message": "Dati mancanti"}

    # Inizializza la struttura per i gruppi in attesa
    if not hasattr(manager, 'pending_group_requests'):
        manager.pending_group_requests = {}

    # Inizializza la richiesta di gruppo
    manager.pending_group_requests[group_id] = {
        'creator': creator,
        'invited': members_to_invite,
        'accepted': [creator],  # Il creatore è già nel gruppo
        'status': 'pending'
    }

    print(f"DEBUG: Gruppo {group_id} in attesa creato, invitati: {members_to_invite}")

    return {"status": "success", "group_id": group_id}


@app.get("/get_group_members/{group_id}")
async def get_group_members(group_id: str):
    """Ottiene tutti i membri di un gruppo specifico"""
    try:
        all_members = []

        # Metodo diretto: controlla in manager.groups
        if group_id in manager.groups:
            # Prende i membri direttamente dalla lista dei gruppi
            all_members = manager.groups[group_id]

        # Metodo alternativo: controlla ogni utente che potrebbe essere nel gruppo
        for username, group in manager.chat_groups.items():
            if group == group_id and username not in all_members:
                all_members.append(username)

        # Per gruppi chat 1:1
        if "-" in group_id and not all_members:
            user1, user2 = group_id.split("-")
            all_members = [user1, user2]
            print(f"Gruppo 1:1 identificato: {all_members}")

        # Assicura che tutti i membri siano stringhe valide e unici
        all_members = [str(member) for member in all_members if member]
        all_members = list(set(all_members))  # Rimuove duplicati

        return {"members": all_members}
    except Exception as e:
        print(f"Errore in get_group_members: {e}")
        import traceback
        print(traceback.format_exc())
        return {"members": [], "error": str(e)}


@app.get("/admin/check_group_integrity/{group_id}")
async def check_group_integrity(group_id: str):
    """
    Assicura che tutti gli utenti associati al gruppo siano nei manager.groups e viceversa.
    """
    try:
        # Recupera gli utenti associati a questo gruppo
        associated_users = []
        for username, g_id in manager.chat_groups.items():
            if g_id == group_id:
                associated_users.append(username)

        # Recupera i membri diretti dal gruppo
        direct_members = manager.groups.get(group_id, []) if group_id in manager.groups else []

        # Trova le discrepanze
        missing_in_group = [user for user in associated_users if user not in direct_members]
        missing_associations = [member for member in direct_members if member not in associated_users]

        changes_made = False

        # Corregge gli utenti mancanti nella lista del gruppo
        if missing_in_group:
            if group_id not in manager.groups:
                manager.groups[group_id] = []

            for user in missing_in_group:
                manager.groups[group_id].append(user)
                print(f"Aggiunto {user} a manager.groups[{group_id}]")
                changes_made = True

        # Corregge le associazioni mancanti
        for member in missing_associations:
            manager.chat_groups[member] = group_id
            print(f"Aggiunto associazione per {member} a {group_id}")
            changes_made = True

        # Assicura che gli utenti siano unici
        if group_id in manager.groups:
            unique_members = list(set(manager.groups[group_id]))
            manager.groups[group_id] = [str(m) for m in unique_members if m]

        return {
            "group_id": group_id,
            "changes_made": changes_made,
            "final_members": manager.groups.get(group_id, []),
            "associated_users": associated_users,
            "previous_direct_members": direct_members,
            "missing_in_group_fixed": missing_in_group,
            "missing_associations_fixed": missing_associations
        }
    except Exception as e:
        print(f"Errore durante il controllo dell'integrità del gruppo: {e}")
        import traceback
        print(traceback.format_exc())
        return {"error": str(e)}


# Endpoint per riparare tutti i gruppi
@app.get("/admin/repair_all_groups")
async def repair_all_groups():
    """Ripara l'integrità di tutti i gruppi nel sistema"""
    results = {}

    try:
        # Ottiene tutti gli ID gruppo unici
        all_group_ids = set()

        # Dai gruppi diretti
        for group_id in manager.groups.keys():
            all_group_ids.add(group_id)

        # Dalle associazioni con gli utenti
        for group_id in manager.chat_groups.values():
            all_group_ids.add(group_id)

        # Ripara ogni gruppo
        for group_id in all_group_ids:
            if group_id:  # Assicura che l'ID non sia vuoto
                result = await check_group_integrity(group_id)
                results[group_id] = result

        return {
            "status": "success",
            "groups_checked": len(results),
            "details": results
        }
    except Exception as e:
        print(f"Errore durante la riparazione di tutti i gruppi: {e}")
        import traceback
        print(traceback.format_exc())


@app.post("/update_questionnaire_status")
async def update_questionnaire_status(data: dict):
    """
    Aggiorna lo stato di completamento del questionario di un utente nel gruppo.
    Quando tutti gli utenti hanno completato il questionario, imposta lo stato su True.
    """
    group_id = data.get("group_id")
    username = data.get("username")
    feedback_data = data.get("feedback_data", {})
    average_feedback = data.get("average_feedback", 0)

    if not group_id or not username:
        return {"status": "error", "message": "Parametri mancanti"}

    # Inizializza il contatore di questionari completati per questo gruppo se non esiste
    if 'group_questionnaire_completions' not in manager.__dict__:
        manager.group_questionnaire_completions = {}

    if 'group_feedback' not in manager.__dict__:
        manager.group_feedback = {}

    if 'group_feedback_averages' not in manager.__dict__:
        manager.group_feedback_averages = {}

    # Inizializza la struttura per questo gruppo se non esiste
    if group_id not in manager.group_questionnaire_completions:
        manager.group_questionnaire_completions[group_id] = set()

    if group_id not in manager.group_feedback:
        manager.group_feedback[group_id] = {}

    if group_id not in manager.group_feedback_averages:
        manager.group_feedback_averages[group_id] = {}

    # Aggiunge l'utente al set di completamenti
    manager.group_questionnaire_completions[group_id].add(username)

    # Salva il feedback dell'utente
    manager.group_feedback[group_id][username] = feedback_data
    manager.group_feedback_averages[group_id][username] = average_feedback

    # Ottiene tutti gli utenti del gruppo
    all_users = manager.groups.get(group_id, [])

    # Lista utenti che hanno completato
    completed_users = list(manager.group_questionnaire_completions[group_id])

    # Verifica se tutti gli utenti hanno completato il questionario
    all_completed = False
    if group_id in manager.groups:
        total_members = len(manager.groups[group_id])
        completed_members = len(manager.group_questionnaire_completions[group_id])


        # Se tutti hanno completato, aggiorna lo stato del gruppo
        if completed_members == total_members:
            all_completed = True

            # Calcola la media dei feedback di tutti gli utenti
            combined_feedback = {}
            for user, user_feedback in manager.group_feedback[group_id].items():
                for category, score in user_feedback.items():
                    if category not in combined_feedback:
                        combined_feedback[category] = []
                    combined_feedback[category].append(score)

            # Calcola le medie per categoria
            average_feedback = {}
            for category, scores in combined_feedback.items():
                average_feedback[category] = sum(scores) / len(scores)

            # Salva l'aggregazione
            manager.group_aggregated_feedback = manager.group_aggregated_feedback or {}
            manager.group_aggregated_feedback[group_id] = average_feedback

            # Calcola la media complessiva
            all_scores = []
            for scores in combined_feedback.values():
                all_scores.extend(scores)
            overall_average = sum(all_scores) / len(all_scores) if all_scores else 0

            # Salva la media complessiva
            manager.group_overall_average = manager.group_overall_average or {}
            manager.group_overall_average[group_id] = overall_average

    return {
        "status": "success",
        "all_completed": all_completed,
        "completed_users": completed_users,
        "all_users": all_users
    }


@app.get("/check_questionnaire_status/{group_id}")
async def check_questionnaire_status(group_id: str):
    """
    Verifica lo stato di completamento del questionario per un gruppo.
    Restituisce l'elenco degli utenti che hanno completato e l'elenco di tutti gli utenti.
    """
    # Assicura che la struttura dati esista
    if not hasattr(manager, 'group_questionnaire_completions'):
        manager.group_questionnaire_completions = {}

    # Recupera gli utenti che hanno completato il questionario
    completed_users = list(manager.group_questionnaire_completions.get(group_id, set()))

    # Recupera tutti gli utenti del gruppo
    all_users = manager.groups.get(group_id, [])

    # Controlla se tutti hanno completato
    all_completed = len(completed_users) >= len(all_users) and len(all_users) > 0

    return {
        "completed_users": completed_users,
        "all_users": all_users,
        "all_completed": all_completed
    }


@app.post("/submit_user_feedback")
async def submit_user_feedback(data: dict):
    """
    Salva i dati del feedback di un utente e aggiorna l'aggregazione per il gruppo.
    """
    group_id = data.get("group_id")
    username = data.get("username")
    feedback = data.get("feedback", {})
    average_feedback = data.get("average_feedback", 0)

    if not group_id or not username or not feedback:
        return {"status": "error", "message": "Dati incompleti"}

    # Inizializza le strutture per i feedback del gruppo se non esistono
    if not hasattr(manager, 'group_feedback'):
        manager.group_feedback = {}

    if not hasattr(manager, 'group_feedback_averages'):
        manager.group_feedback_averages = {}

    if not hasattr(manager, 'group_aggregated_feedback'):
        manager.group_aggregated_feedback = {}

    if not hasattr(manager, 'group_overall_average'):
        manager.group_overall_average = {}

    if group_id not in manager.group_feedback:
        manager.group_feedback[group_id] = {}

    if group_id not in manager.group_feedback_averages:
        manager.group_feedback_averages[group_id] = {}

    # Salva il feedback dell'utente
    manager.group_feedback[group_id][username] = feedback
    manager.group_feedback_averages[group_id][username] = average_feedback

    print(f"[{username}] Media feedback individuale: {average_feedback}")

    # Calcola medie aggregate se tutti hanno inviato feedback
    all_submitted = False
    if group_id in manager.groups:
        total_members = len(manager.groups[group_id])
        submitted_members = len(manager.group_feedback[group_id])

        if submitted_members == total_members:
            all_submitted = True

            # Calcola la media dei feedback di tutti gli utenti
            combined_feedback = {}
            for user, user_feedback in manager.group_feedback[group_id].items():
                for category, score in user_feedback.items():
                    if category not in combined_feedback:
                        combined_feedback[category] = []
                    combined_feedback[category].append(float(score))

            # Calcola le medie per categoria
            average_feedback_data = {}
            for category, scores in combined_feedback.items():
                average_feedback_data[category] = sum(scores) / len(scores)

            # Salva l'aggregazione
            if not hasattr(manager, 'group_aggregated_feedback'):
                manager.group_aggregated_feedback = {}
            manager.group_aggregated_feedback[group_id] = average_feedback_data

            # Calcola la media complessiva
            all_scores = []
            for scores in combined_feedback.values():
                all_scores.extend(scores)
            overall_average = sum(all_scores) / len(all_scores) if all_scores else 0

            # Salva la media complessiva
            if not hasattr(manager, 'group_overall_average'):
                manager.group_overall_average = {}
            manager.group_overall_average[group_id] = overall_average

    return {
        "status": "success",
        "message": "Feedback salvato",
        "all_submitted": all_submitted
    }


@app.get("/get_group_feedback/{group_id}")
async def get_group_feedback(group_id: str):
    """
    Recupera i dati aggregati del feedback di tutti i membri del gruppo.
    """

    if not hasattr(manager, 'group_aggregated_feedback'):
        manager.group_aggregated_feedback = {}

    if not hasattr(manager, 'group_overall_average'):
        manager.group_overall_average = {}

    # Verifica se tutti gli utenti hanno inviato feedback
    all_submitted = False
    if hasattr(manager, 'group_feedback') and group_id in manager.group_feedback:
        if group_id in manager.groups:
            total_members = len(manager.groups[group_id])
            submitted_members = len(manager.group_feedback[group_id])
            all_submitted = submitted_members == total_members
        else:
            pass
    else:
        pass

    # Recupera i dati aggregati
    if group_id in manager.group_aggregated_feedback:
        feedback = manager.group_aggregated_feedback[group_id]
        average_feedback = manager.group_overall_average.get(group_id, 0)
        return {
            "status": "success",
            "feedback": feedback,
            "average_feedback": average_feedback
        }
    else:

        # Se non ci sono dati aggregati ma ci sono feedback individuali, calcola la media
        if hasattr(manager, 'group_feedback') and group_id in manager.group_feedback:
            user_feedbacks = manager.group_feedback[group_id]
            if user_feedbacks:
                # Calcola la media dei feedback di tutti gli utenti
                combined_feedback = {}
                for user, user_feedback in user_feedbacks.items():
                    for category, score in user_feedback.items():
                        if category not in combined_feedback:
                            combined_feedback[category] = []
                        combined_feedback[category].append(float(score))

                # Calcola le medie per categoria
                average_feedback_data = {}
                for category, scores in combined_feedback.items():
                    average_feedback_data[category] = sum(scores) / len(scores)

                # Calcola la media complessiva
                all_scores = []
                for scores in combined_feedback.values():
                    all_scores.extend(scores)
                overall_average = sum(all_scores) / len(all_scores) if all_scores else 0

                # Salva i risultati calcolati
                manager.group_aggregated_feedback[group_id] = average_feedback_data
                manager.group_overall_average[group_id] = overall_average

                return {
                    "status": "success",
                    "feedback": average_feedback_data,
                    "average_feedback": overall_average
                }

    return {"status": "error", "message": "Nessun dato aggregato trovato"}

@app.get("/debug_feedback/{group_id}")
async def debug_feedback(group_id: str):
    """Endpoint di debug per verificare lo stato dei feedback di un gruppo"""
    result = {
        "group_exists": group_id in manager.groups if hasattr(manager, 'groups') else False,
        "members": manager.groups.get(group_id, []) if hasattr(manager, 'groups') else [],
        "feedback_exists": group_id in manager.group_feedback if hasattr(manager, 'group_feedback') else False,
        "feedback_data": manager.group_feedback.get(group_id, {}) if hasattr(manager, 'group_feedback') else {},
        "aggregated_exists": group_id in manager.group_aggregated_feedback if hasattr(manager, 'group_aggregated_feedback') else False,
        "aggregated_data": manager.group_aggregated_feedback.get(group_id, {}) if hasattr(manager, 'group_aggregated_feedback') else {},
        "average_exists": group_id in manager.group_overall_average if hasattr(manager, 'group_overall_average') else False,
        "average_value": manager.group_overall_average.get(group_id, None) if hasattr(manager, 'group_overall_average') else None,
        "completion_status": {
            "exists": group_id in manager.group_questionnaire_completions if hasattr(manager, 'group_questionnaire_completions') else False,
            "completed_users": list(manager.group_questionnaire_completions.get(group_id, set())) if hasattr(manager, 'group_questionnaire_completions') else []
        }
    }
    return result


@app.post("/submit_questionnaire_scores")
async def submit_questionnaire_scores(data: dict):
    """
    Riceve i punteggi del questionario di un utente.
    """
    username = data.get("username")
    scores = data.get("scores", {})

    # Calcola la media dei punteggi
    score_values = list(scores.values())
    average_score = sum(score_values) / len(score_values) if score_values else 0

    # Memorizza la media dei punteggi
    manager.questionnaire_scores[username] = average_score

    return {"status": "success", "average_score": average_score}


@app.post("/set_user_intervention_mode")
async def set_user_intervention_mode(data: dict):
    """
    Imposta la modalità di intervento per un utente specifico.
    """
    username = data.get("username")
    average_score = data.get("average_score", 0)

    if not username:
        return {"status": "error", "message": "Username mancante"}

    # Determina la modalità in base alla media dei punteggi
    mode = "accordo" if average_score > 2 else "disaccordo"

    # Memorizza la modalità per questo utente
    if not hasattr(manager, 'user_intervention_modes'):
        manager.user_intervention_modes = {}

    manager.user_intervention_modes[username] = mode

    print(f"Impostata modalità {mode} per {username} con punteggio medio {average_score}")

    return {"status": "success", "mode": mode}


@app.post("/set_intervention_mode")
async def set_intervention_mode(data: dict):
    """
    Imposta la modalità di intervento (accordo/disaccordo) per un utente
    in base alla media dei punteggi del questionario.
    """
    username = data.get("username")
    media_punteggi = data.get("media_punteggi", 0)

    # Determina la modalità in base alla media
    modo = "accordo" if media_punteggi > 2 else "disaccordo"

    # Salva nella struttura dati del manager
    if not hasattr(manager, 'user_modes'):
        manager.user_modes = {}

    manager.user_modes[username] = modo

    return {"status": "success", "modo": modo}


def check_consistency(response, modo, utenti_list):
    """
    Controlla se la risposta è coerente con la modalità specificata.
    Se rileva incoerenze, aggiunge un avviso.
    """
    # Cerca frasi che potrebbero indicare una contraddizione
    contradiction_indicators = [
        "(Ecco il mio intervento",
        "Io non sono d'accordo",
        "In disaccordo con",
        "In accordo con"
    ]

    # Se trova indicatori di contraddizione, aggiunge un avviso
    for indicator in contradiction_indicators:
        if indicator.lower() in response.lower():
            # Tronca la risposta al punto in cui inizia la contraddizione
            index = response.lower().find(indicator.lower())
            if index > 50:  # Assicura di non troncare troppo all'inizio
                return response[:index].strip()

    return response  # Restituisce la risposta originale se non ci sono problemi

@app.get("/debug_list/{group_id}")
async def debug_list(group_id: str):
    """Endpoint di debug per esaminare la lista corrente di un gruppo"""
    try:
        if group_id in manager.shared_lists:
            # Stampa di debug
            print(f"DEBUG: Lista per gruppo {group_id}: {manager.shared_lists[group_id][:3]}")
            return {
                "status": "success",
                "list_available": True,
                "list_length": len(manager.shared_lists[group_id]) if manager.shared_lists[group_id] else 0,
                "list_sample": manager.shared_lists[group_id][:3] if manager.shared_lists[group_id] else [],
                "timestamp": time.time()
            }
        else:
            return {"status": "error", "message": f"Nessuna lista trovata per gruppo {group_id}"}
    except Exception as e:
        print(f"Errore in debug_list: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/sync_list")
async def sync_list(data: SyncListRequest):
    """
    Endpoint per sincronizzare la lista tra gli utenti di un gruppo.
    """
    group_id = data.group_id
    username = data.username
    updated_list = data.list
    if group_id in manager.editing_locks:
        if manager.editing_locks[group_id]["user"] != username:
            return {
                "status": "error",
                "message": "Lista bloccata da un altro utente"
            }

    timestamp = int(time.time() * 1000)

    if not group_id or not username or not updated_list:
        return {"status": "error", "message": "Parametri mancanti"}

    # Verifica se la lista è bloccata
    if hasattr(manager, 'locked_lists') and group_id in manager.locked_lists:
        if manager.locked_lists[group_id]["locked"]:
            print(f"Tentativo di modifica bloccato per gruppo {group_id} da {username}")
            return {
                "status": "error",
                "message": f"La lista è stata bloccata da {manager.locked_lists[group_id]['locked_by']}. Impossibile modificare.",
                "locked": True,
                "locked_by": manager.locked_lists[group_id]['locked_by']
            }

    # Aggiorna i timestamp in tutti gli elementi
    for item in updated_list:
        item['last_modified'] = timestamp

    # Aggiorna la lista nel server
    with manager.lock:
        manager.shared_lists[group_id] = copy.deepcopy(updated_list)

    # Delay per evitare conflitti di stato
    await asyncio.sleep(0.2)

    # Notifica tutti gli altri utenti del gruppo
    notification_count = 0
    if group_id in manager.groups:
        group_members = manager.groups[group_id]

        for member in group_members:
            if member != username and member in manager.usernames:
                try:
                    notification = {
                        "type": "list_sync",
                        "group_id": group_id,
                        "username": username,
                        "list": copy.deepcopy(updated_list),
                        "timestamp": timestamp,
                        "changed": True,
                        "list_hash": hashlib.md5(str([item['id'] for item in updated_list]).encode()).hexdigest()[:8]
                    }
                    await manager.usernames[member].send_text(json.dumps(notification))
                    notification_count += 1
                    print(f"Notifica inviata a {member}")
                except Exception:
                    pass

    return {
        "status": "success",
        "message": "Lista sincronizzata con successo",
        "notifications": notification_count,
        "timestamp": timestamp
    }

async def send_delayed_update_notification(group_id, timestamp):
    """Invia una notifica di verifica aggiornamenti dopo un breve ritardo"""
    try:
        # Attende 2 secondi per assicurarsi che tutti ricevano l'aggiornamento
        await asyncio.sleep(2)

        if group_id in manager.groups:
            # Invia una notifica a tutti i membri per verificare di avere l'ultima versione
            for member in manager.groups[group_id]:
                if member in manager.usernames:
                    try:
                        check_message = {
                            "type": "check_list_updates",
                            "group_id": group_id,
                            "timestamp": timestamp
                        }
                        await manager.usernames[member].send_text(json.dumps(check_message))
                    except Exception as e:
                        print(f"Errore nell'invio della notifica di verifica a {member}: {e}")
    except Exception as e:
        print(f"Errore nel task di notifica ritardata: {e}")

@app.get("/sync_list/{group_id}")
async def get_sync_list(group_id: str):
    """
    Endpoint per ottenere la lista aggiornata dal server.
    """
    try:
        if group_id in manager.shared_lists:
            current_list = manager.shared_lists[group_id]
            return {
                "status": "success",
                "list": current_list,
                "timestamp": int(time.time() * 1000)
            }
        else:
            return {"status": "error", "message": "Lista non trovata"}
    except Exception as e:
        print(f"Errore nel recupero della lista: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/debug_user_modes")
async def debug_user_modes():
    """Endpoint di debug per vedere tutte le modalità utente impostate"""
    if hasattr(manager, 'user_modes'):
        return {"user_modes": manager.user_modes}
    else:
        return {"user_modes": "Non inizializzato"}


@app.post("/lock_shared_list")
async def lock_shared_list(data: dict):
    """
    Blocca la lista condivisa quando il primo utente conferma
    """
    group_id = data.get("group_id")
    username = data.get("username")

    if not group_id or not username:
        return {"status": "error", "message": "Parametri mancanti"}

    # Inizializza la struttura per le liste bloccate se non esiste
    if not hasattr(manager, 'locked_lists'):
        manager.locked_lists = {}

    # Blocca la lista per questo gruppo
    manager.locked_lists[group_id] = {
        "locked": True,
        "locked_by": username,
        "timestamp": int(time.time() * 1000)
    }

    # Notifica tutti i membri del gruppo che la lista è stata bloccata
    if group_id in manager.groups:
        for member in manager.groups[group_id]:
            if member != username and member in manager.usernames:
                try:
                    await manager.safe_send_notification(member, {
                        "type": "list_locked",
                        "group_id": group_id,
                        "locked_by": username,
                        "message": f"La lista è stata bloccata da {username}. Non è più possibile modificarla."
                    })
                except Exception as e:
                    print(f"Errore nell'invio della notifica di blocco a {member}: {e}")

    return {"status": "success", "message": "Lista bloccata con successo"}


@app.get("/check_list_locked/{group_id}")
async def check_list_locked(group_id: str):
    """
    Verifica se una lista è bloccata
    """

    if hasattr(manager, 'locked_lists'):
        if group_id in manager.locked_lists:
            result = {
                "locked": True,
                "locked_by": manager.locked_lists[group_id]["locked_by"],
                "timestamp": manager.locked_lists[group_id]["timestamp"]
            }
            return result

    result = {"locked": False}
    return result


@app.post("/submit_demographics")
async def submit_demographics(data: dict):
    """Riceve e memorizza i dati demografici di un utente"""
    username = data.get("username")
    demographics = data.get("demographics", {})

    if not username:
        return {"status": "error", "message": "Username mancante"}

    # Inizializza la struttura se non esiste
    if not hasattr(manager, 'user_demographics'):
        manager.user_demographics = {}

    # Salva i dati demografici
    manager.user_demographics[username] = demographics

    # Stampa i dati demografici nel terminale
    print(f"=== DATI DEMOGRAFICI per {username} ===")
    print(f"Età: {demographics.get('eta', 'N/A')}")
    print(f"Sesso: {demographics.get('sesso', 'N/A')}")
    print(f"Professione: {demographics.get('professione', 'N/A')}")
    print(f"Esperienza LLM: {demographics.get('esperienzaLLM', 'N/A')}")
    print("=====================================")

    return {"status": "success"}


@app.post("/editing_lock")
async def handle_editing_lock(request: EditingLockRequest):
    """
    Gestisce i lock di editing per prevenire modifiche simultanee
    """
    group_id = request.group_id
    username = request.username
    action = request.action

    current_time = time.time()

    if action == "start":
        # Controlla se qualcun altro sta modificando
        if group_id in manager.editing_locks:
            existing_lock = manager.editing_locks[group_id]
            # Timeout di trenta secondi per lock scaduti
            if current_time - existing_lock["timestamp"] < 30:
                if existing_lock["user"] != username:
                    return {
                        "status": "locked",
                        "locked_by": existing_lock["user"],
                        "message": f"{existing_lock['user']} sta modificando la lista"
                    }

        # Acquisisce il lock
        manager.editing_locks[group_id] = {
            "user": username,
            "timestamp": current_time
        }

        # Notifica tutti gli altri membri del gruppo
        if group_id in manager.groups:
            for member in manager.groups[group_id]:
                if member != username and member in manager.usernames:
                    try:
                        await manager.safe_send_notification(member, {
                            "type": "editing_lock_start",
                            "group_id": group_id,
                            "editing_user": username
                        })
                    except Exception as e:
                        print(f"Errore notifica lock start a {member}: {e}")

        return {"status": "lock_acquired"}

    elif action == "end":
        # Rilascia il lock solo se appartiene all'utente
        if group_id in manager.editing_locks:
            if manager.editing_locks[group_id]["user"] == username:
                del manager.editing_locks[group_id]

                # Notifica tutti i membri che il lock è stato rilasciato
                if group_id in manager.groups:
                    for member in manager.groups[group_id]:
                        if member != username and member in manager.usernames:
                            try:
                                await manager.safe_send_notification(member, {
                                    "type": "editing_lock_end",
                                    "group_id": group_id,
                                    "editing_user": username
                                })
                            except Exception as e:
                                print(f"Errore notifica lock end a {member}: {e}")

                return {"status": "lock_released"}

        return {"status": "no_lock_to_release"}
