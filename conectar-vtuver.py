import asyncio
import ollama
import pyvts
import pyttsx3
import threading
import random
import time

# --- CONFIGURACIÓN ---
MODELO_OLLAMA = "phi3"
NOMBRE_IA = "Neuro-Local"
PUERTO_VTS = 8001
USAR_MICROFONO = True 

# Intentamos importar la librería de reconocimiento de voz
try:
    import speech_recognition as sr
    HAY_MICROFONO = True
except ImportError:
    HAY_MICROFONO = False
    print("⚠️ Librería 'SpeechRecognition' no encontrada. Usando modo TEXTO.")

# --- INICIALIZAR VOZ (TTS) ---
engine = pyttsx3.init()
engine.setProperty('rate', 155) # Un poco más rápido para que hable fluido

voices = engine.getProperty('voices')
for voice in voices:
    if "spanish" in voice.name.lower() or "es-es" in voice.id.lower():
        engine.setProperty('voice', voice.id)
        break

def hablar_tts_thread(texto):
    try:
        engine.say(texto)
        engine.runAndWait()
    except RuntimeError:
        pass

# --- FUNCIÓN: OÍDO MEJORADO (SIN INTERRUPCIONES) ---
def escuchar_usuario(recognizer, microphone):
    # Usamos \r para sobreescribir la linea y no llenar la consola
    print(f"\r🎤 {NOMBRE_IA} escuchando...      ", end="", flush=True)
    
    try:
        with microphone as source:
            # Escucha con tiempos cortos. 
            # timeout=3: Si no hablas en 3 seg, deja de escuchar.
            # phrase_time_limit=5: Si hablas más de 5 seg, corta para procesar.
            audio = recognizer.listen(source, timeout=3, phrase_time_limit=5)
        
        print(f"\r⏳ Procesando audio...          ", end="", flush=True)
        # Usamos Google porque es rápido y ligero
        texto = recognizer.recognize_google(audio, language="es-ES")
        print(f"\n🗣️ TÚ: {texto}")
        return texto

    except sr.WaitTimeoutError:
        # Silencio absoluto, retornamos None para reintentar rápido
        return None
    except sr.UnknownValueError:
        # Ruido que no es voz, retornamos None para reintentar rápido
        return None
    except Exception as e:
        print(f"\n⚠️ Error de micro: {e}")
        return None

async def main():
    # 1. CONEXIÓN AVATAR
    plugin_info = {
        "plugin_name": "Neuro-Local-Controller",
        "developer": "TuNombre",
        "authentication_token_path": "./token.txt"
    }
    myvts = pyvts.vts(plugin_info=plugin_info)
    
    print(f"--- INICIANDO {NOMBRE_IA} (MODO FLUIDO) ---")
    
    # Setup del Micrófono
    recognizer = None
    mic = None
    if USAR_MICROFONO and HAY_MICROFONO:
        recognizer = sr.Recognizer()
        mic = sr.Microphone()
        with mic as source:
            print("Calibrando ruido de fondo (Espere 1 seg)...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            # Ajustes para que detecte mejor el silencio
            recognizer.dynamic_energy_threshold = True 
            recognizer.energy_threshold = 300  # Nivel mínimo de ruido para activar
            recognizer.pause_threshold = 0.6   # Pausa corta marca el fin de la frase
    
    print("Conectando con VTube Studio...")
    try:
        await myvts.connect()
        await myvts.request_authenticate_token()
        await myvts.request_authenticate()
        print("✓ Avatar conectado.")
    except Exception:
        print("❌ Error: Abre VTube Studio primero (Puerto 8001).")
        return

    # 2. BUCLE INFINITO
    print("\n------------------------------------------------")
    print(f"¡Sistema Activo! Simplemente háblale.")
    print("------------------------------------------------")
    
    while True:
        prompt = ""
        
        # A. INPUT (Micro o Texto)
        if USAR_MICROFONO and HAY_MICROFONO:
            # Ejecutamos escucha en segundo plano
            loop = asyncio.get_event_loop()
            prompt = await loop.run_in_executor(None, escuchar_usuario, recognizer, mic)
            
            # ¡LA CLAVE! Si prompt es None (silencio/ruido), volvemos al inicio INMEDIATAMENTE
            if not prompt: 
                print("\r🔇 Silencio detectado... Escribe manualmente o habla: ", end="")
                prompt = input()
        else:
            prompt = input("\nTú: ")
        
        if prompt and prompt.lower() in ["salir", "exit", "adiós"]:
            despedida = "¡Hasta la próxima!"
            print(f"🤖 {NOMBRE_IA}: {despedida}")
            threading.Thread(target=hablar_tts_thread, args=(despedida,)).start()
            break

        # B. PENSAR (OLLAMA)
        # print(f"({NOMBRE_IA} pensando...)") 
        try:
            resp = ollama.chat(model=MODELO_OLLAMA, messages=[
                {'role': 'system', 'content': 'Eres Neuro-Local, una VTuber IA graciosa, un poco loca y sarcástica como Neuro-sama. Habla en español, sé divertida, corta y responde solo 1-2 frases. A veces sé "malvada" y caótica.'},
                {'role': 'user', 'content': prompt}
            ])
            texto_ia = resp['message']['content']
        except Exception:
            texto_ia = "¿Qué?"

        print(f"🤖 {NOMBRE_IA}: {texto_ia}")

        # C. HABLAR Y ANIMAR
        tts_thread = threading.Thread(target=hablar_tts_thread, args=(texto_ia,))
        tts_thread.start()

        # Animación de boca mientras habla
        while tts_thread.is_alive():
            apertura = random.uniform(0.0, 0.6)
            await myvts.request(myvts.vts_request.requestSetParameterValue("MouthOpen", apertura))
            await asyncio.sleep(0.1)
            
        await myvts.request(myvts.vts_request.requestSetParameterValue("MouthOpen", 0.0))
        tts_thread.join()

    await myvts.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass