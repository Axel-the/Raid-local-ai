import asyncio
import ollama
import threading
import queue
import re
import time
import io
import base64
import speech_recognition as sr
import win32com.client
import pythoncom
from mss import mss
from PIL import Image
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from flask_cors import CORS

import json
import os

# --- CONFIGURACIÓN ---
MODELO_VISION = "moondream:1.8b"   # El que tiene ojos
MODELO_CHAT = "llama3.2:3b"        # El que habla bien español
NOMBRE_IA = "Ojo Local"
IDIOMA = "es-ES"

# --- INICIALIZACIÓN WEB ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- PERSISTENCIA DE MEMORIA ---
ARCHIVO_MEMORIA = "memoria_ia.json"

def cargar_memoria():
    if os.path.exists(ARCHIVO_MEMORIA):
        with open(ARCHIVO_MEMORIA, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "perfil_usuario": "Usuario nuevo",
        "historial_corto": [],
        "datos_aprendidos": []
    }

def guardar_memoria(memoria):
    with open(ARCHIVO_MEMORIA, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, ensure_ascii=False, indent=4)

memoria_global = cargar_memoria()

# --- ESTADO GLOBAL ---
cola_voz = queue.Queue()
esta_hablando = threading.Event()

def update_ui(state=None, msg=None, role='ai', image=None, is_partial=False):
    """Envia actualizaciones en tiempo real a la interfaz web"""
    try:
        socketio.emit('update_status', {
            'state': state,
            'msg': msg,
            'role': role,
            'image': image,
            'is_partial': is_partial
        })
    except: pass

# --- FUNCION: CAPTURA DE PANTALLA ---
def capturar_pantalla_b64():
    """Captura y devuelve la imagen optimizada"""
    try:
        with mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Alta calidad para Ollama (Pero no gigante)
            img_ollama = img.copy()
            img_ollama.thumbnail((800, 450))
            buffer_ollama = io.BytesIO()
            img_ollama.save(buffer_ollama, format='JPEG', quality=85)
            raw_bytes = buffer_ollama.getvalue()
            
            # Baja calidad para UI (Velocidad)
            img.thumbnail((450, 250))
            buffer_ui = io.BytesIO()
            img.save(buffer_ui, format='JPEG', quality=50)
            b64_str = base64.b64encode(buffer_ui.getvalue()).decode('utf-8')
            
            return raw_bytes, b64_str
    except Exception as e:
        print(f"Error captura: {e}")
        return None, None

# --- PROCESADOR DE VOZ ---
def procsador_voz_thread():
    pythoncom.CoInitialize()
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        voices = speaker.GetVoices()
        for i in range(voices.Count):
            if "Spanish" in voices.Item(i).GetDescription():
                speaker.Voice = voices.Item(i)
                break
        
        while True:
            frase = cola_voz.get()
            if frase is None: break
            try:
                esta_hablando.set()
                update_ui(state='speaking')
                speaker.Speak(frase)
            except: pass
            finally:
                cola_voz.task_done()
                if cola_voz.empty():
                    time.sleep(0.4)
                    esta_hablando.clear()
                    update_ui(state='idle')
    except Exception as e:
        print(f"Error voz: {e}")

# --- TRABAJADOR DE IA CON MEMORIA ---
def ai_worker():
    global memoria_global
    print("Iniciando IA Híbrida con Memoria...")
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
    
    while True:
        while esta_hablando.is_set(): time.sleep(0.1)
        
        update_ui(state='listening')
        try:
            with mic as source:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            
            update_ui(state='thinking')
            prompt = recognizer.recognize_google(audio, language=IDIOMA)
            
            # Pasos de procesamiento
            img_raw, img_b64 = capturar_pantalla_b64()
            
            # 1. Mostrar prompt del usuario inmediatamente con la imagen
            update_ui(msg=prompt, role='user', image=img_b64)

            # PASO 1: Analizar imagen (Visión)
            update_ui(state='thinking')
            print("Analizando imagen...")
            vision_resp = ollama.chat(
                model=MODELO_VISION,
                messages=[{'role': 'user', 'content': 'Describe briefly the key elements on screen.', 'images': [img_raw]}]
            )
            contexto_visual = vision_resp['message']['content']

            # PASO 2: Generar respuesta con Contexto Histórico
            update_ui(state='remembering') # Nuevo estado para la UI
            print("Generando respuesta contextual con Llama...")
            
            system_prompt = (
                f"Eres un amigo español llamado {NOMBRE_IA}. Tienes memoria a largo plazo. "
                f"Lo que has aprendido del usuario: {memoria_global['perfil_usuario']}. "
                f"Datos adicionales: {', '.join(memoria_global['datos_aprendidos'])}. "
                f"Contexto visual actual: {contexto_visual}. "
                f"Responde de forma muy natural y breve (máximo 1 frase)."
            )

            stream = ollama.chat(
                model=MODELO_CHAT,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    *memoria_global['historial_corto'][-6:], # Últimos 6 mensajes
                    {'role': 'user', 'content': prompt}
                ],
                stream=True,
                options={'num_predict': 80}
            )
            
            full_response = ""
            sentence_buffer = ""
            
            # Iniciamos el stream en el frontend
            update_ui(state='thinking', msg="", role='ai', is_partial=True)

            for chunk in stream:
                text_chunk = chunk['message']['content']
                full_response += text_chunk
                sentence_buffer += text_chunk
                
                # Actualizar el mismo mensaje en la UI
                update_ui(msg=full_response, role='ai', is_partial=True)

                if any(p in text_chunk for p in ['.', '!', '?', ',', '\n']):
                    if len(sentence_buffer.strip()) > 1:
                        cola_voz.put(sentence_buffer.strip())
                        sentence_buffer = ""

            if sentence_buffer.strip():
                cola_voz.put(sentence_buffer.strip())
            
            # --- APRENDIZAJE POST-INTERACCIÓN ---
            memoria_global['historial_corto'].append({'role': 'user', 'content': prompt})
            memoria_global['historial_corto'].append({'role': 'assistant', 'content': full_response})
            
            # Pedir a Llama que extraiga algo nuevo sobre el usuario (en segundo plano)
            if len(memoria_global['historial_corto']) % 4 == 0:
                print("Aprendiendo sobre el usuario...")
                resp_aprendizaje = ollama.chat(
                    model=MODELO_CHAT,
                    messages=[{'role': 'user', 'content': f"Basado en esta charla: '{prompt}', ¿qué aprendiste del usuario en 3 palabras? Ej: 'Le gusta Python'."}]
                )
                memoria_global['datos_aprendidos'].append(resp_aprendizaje['message']['content'].strip())
            
            guardar_memoria(memoria_global)
            update_ui(msg=full_response, role='ai', is_partial=False)

        except sr.UnknownValueError:
            update_ui(state='idle')
        except Exception as e:
            print(f"Error bucle: {e}")
            update_ui(state='idle')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    # Iniciar hilos
    threading.Thread(target=procsador_voz_thread, daemon=True).start()
    threading.Thread(target=ai_worker, daemon=True).start()
    
    socketio.run(app, debug=False, port=5000)
