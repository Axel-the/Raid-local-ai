import asyncio
import ollama
import pyttsx3
import threading
import time
import speech_recognition as sr

# --- CONFIGURACIÓN ---
MODELO_OLLAMA = "llama3.2:3b" # El modelo que tienes instalado
NOMBRE_IA = "Ollama-Assistant"
IDIOMA = "es-ES"

# --- INICIALIZAR VOZ (TTS) ---
engine = pyttsx3.init()
engine.setProperty('rate', 160) # Velocidad de habla
voices = engine.getProperty('voices')
# Intentamos encontrar una voz en español
for voice in voices:
    if "spanish" in voice.name.lower() or "es-es" in voice.id.lower():
        engine.setProperty('voice', voice.id)
        break

def hablar_tts(texto):
    """Función para que la IA hable usando TTS"""
    try:
        print(f"🤖 {NOMBRE_IA}: {texto}")
        engine.say(texto)
        engine.runAndWait()
    except Exception as e:
        print(f"Error en TTS: {e}")

def escuchar_usuario(recognizer, microphone):
    """Función para capturar voz y convertirla a texto"""
    print(f"\r🎤 {NOMBRE_IA} escuchando...      ", end="", flush=True)
    
    try:
        with microphone as source:
            # Calibrar un poco el ruido si es necesario, pero lo ideal es hacerlo una vez al inicio
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        
        print(f"\r⏳ Procesando audio...          ", end="", flush=True)
        texto = recognizer.recognize_google(audio, language=IDIOMA)
        print(f"\n🗣️ TÚ: {texto}")
        return texto

    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except Exception as e:
        print(f"\n⚠️ Error de micro: {e}")
        return None

async def main():
    print(f"--- INICIANDO {NOMBRE_IA} ---")
    print(f"Modelo: {MODELO_OLLAMA}")
    
    # Setup del Micrófono
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    
    with mic as source:
        print("Calibrando ruido de fondo (1 segundo)...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        recognizer.dynamic_energy_threshold = True
    
    print("\n¡Sistema Activo! Háblame cuando quieras.")
    print("Di 'salir' o 'adiós' para terminar.")
    
    while True:
        # 1. ESCUCHAR
        loop = asyncio.get_event_loop()
        prompt = await loop.run_in_executor(None, escuchar_usuario, recognizer, mic)
        
        if not prompt:
            # Si no se detectó nada, volvemos a escuchar
            continue
            
        # 2. PROCESAR SALIDA / COMANDOS
        if prompt.lower() in ["salir", "exit", "adiós", "terminar"]:
            hablar_tts("¡Hasta luego! Fue un placer ayudarte.")
            break

        # 3. PENSAR (OLLAMA)
        try:
            # Usamos el modelo llama3.2:3b que el usuario confirmó tener
            resp = ollama.chat(model=MODELO_OLLAMA, messages=[
                {'role': 'system', 'content': 'Eres un asistente de voz inteligente y amable. Responde de forma clara y concisa en español.'},
                {'role': 'user', 'content': prompt}
            ])
            texto_ia = resp['message']['content']
        except Exception as e:
            print(f"\n❌ Error al conectar con Ollama: {e}")
            texto_ia = "Lo siento, tuve un problema al procesar tu petición."

        # 4. HABLAR
        hablar_tts(texto_ia)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPrograma terminado por el usuario.")
    except Exception as e:
        print(f"\nOcurrió un error inesperado: {e}")
