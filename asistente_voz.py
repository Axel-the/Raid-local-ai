import asyncio
import ollama
import threading
import queue
import re
import time
import io
import speech_recognition as sr
import win32com.client
import pythoncom
from mss import mss
from PIL import Image

# --- CONFIGURACIÓN ---
MODELO_OLLAMA = "moondream:1.8b" # El modelo con "ojos" que tienes instalado
NOMBRE_IA = "Ojo Local"
IDIOMA = "es-ES"

# --- ESTADO GLOBAL ---
cola_voz = queue.Queue()
esta_hablando = threading.Event()

# --- FUNCION: CAPTURA DE PANTALLA RAPIDA ---
def capturar_pantalla():
    """Captura la pantalla principal y la devuelve como bytes JPG comprimidos"""
    try:
        with mss() as sct:
            # Capturar monitor 1
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            
            # Convertir a imagen de Pillow para comprimir y redimensionar (ahorra mucha velocidad)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Opcional: Redimensionar si quieres más velocidad (ej. a 720p)
            img.thumbnail((1280, 720))
            
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=70)
            return img_byte_arr.getvalue()
    except Exception as e:
        print(f"\n[Error Captura]: {e}")
        return None

# --- PROCESADOR DE VOZ (SAPI5 NATIVO) ---
def procsador_voz():
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
                speaker.Speak(frase)
            except: pass
            finally:
                cola_voz.task_done()
                if cola_voz.empty():
                    esta_hablando.clear()
    except Exception as e:
        print(f"Error en voz: {e}")

threading.Thread(target=procsador_voz, daemon=True).start()

def escuchar_usuario(recognizer, microphone):
    while esta_hablando.is_set():
        time.sleep(0.1)

    print(f"\r🎤 TE ESCUCHO...               ", end="", flush=True)
    try:
        with microphone as source:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
        print(f"\r⏳ ANALIZANDO PANTALLA...     ", end="", flush=True)
        texto = recognizer.recognize_google(audio, language=IDIOMA)
        print(f"\n🗣️ TÚ: {texto}")
        return texto
    except:
        return None

async def main():
    print(f"\n================================")
    print(f"   {NOMBRE_IA} CON VISIÓN ACTIVADA")
    print(f"================================\n")
    print(f"La IA está viendo tu pantalla en vivo.")
    
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        recognizer.pause_threshold = 0.8

    while True:
        # 1. ESCUCHAR
        loop = asyncio.get_event_loop()
        prompt = await loop.run_in_executor(None, escuchar_usuario, recognizer, mic)
        
        if not prompt or len(prompt.strip()) < 2:
            continue
        
        # 2. CAPTURAR LO QUE ESTÁ VIENDO EL USUARIO EN ESE MOMENTO
        imagen_bytes = await loop.run_in_executor(None, capturar_pantalla)

        # 3. GENERAR RESPUESTA CON VISIÓN
        print(f"🤖 {NOMBRE_IA}: ", end="", flush=True)
        
        full_response = ""
        sentence_buffer = ""
        
        try:
            # Enviamos el texto + la imagen a moondream
            # Nota: Moondream es mejor con descripciones cortas sobre la imagen
            stream = ollama.chat(
                model=MODELO_OLLAMA, 
                messages=[{
                    'role': 'user', 
                    'content': f'Mira la imagen de mi pantalla y responde brevemente en español a: {prompt}',
                    'images': [imagen_bytes] if imagen_bytes else []
                }], 
                stream=True
            )
            
            for chunk in stream:
                text_chunk = chunk['message']['content']
                full_response += text_chunk
                sentence_buffer += text_chunk
                print(text_chunk, end="", flush=True)

                if any(p in text_chunk for p in ['.', '!', '?', '\n']):
                    parts = re.split(r'([.!?\n])', sentence_buffer)
                    for i in range(0, len(parts) - 1, 2):
                        sentence = parts[i] + parts[i+1]
                        if sentence.strip():
                            cola_voz.put(sentence.strip())
                    sentence_buffer = parts[-1]

            if sentence_buffer.strip():
                cola_voz.put(sentence_buffer.strip())
            
            print() 

        except Exception as e:
            print(f"\n[Error Visión]: {e}")
            cola_voz.put("Vaya, me ha costado ver eso.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCerrando visión...")
