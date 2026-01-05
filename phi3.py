import ollama

# Definimos el modelo que instalaste
MODELO = "phi3" 

print(f"--- Conectando con {MODELO} ---")
print("Enviando mensaje de prueba...")

try:
    # Enviamos un mensaje simple
    respuesta = ollama.chat(model=MODELO, messages=[
        {
            'role': 'user',
            'content': 'Hola, ¿puedes escucharme? Responde con una frase corta y divertida.'
        },
    ])

    # Mostramos la respuesta
    print("\nAI Dice:")
    print(respuesta['message']['content'])
    print("\n--- ¡ÉXITO! La conexión funciona ---")

except Exception as e:
    print(f"\nError: No se pudo conectar con Ollama.")
    print(f"Detalle: {e}")
    print("Asegúrate de que la aplicación de Ollama esté ejecutándose en segundo plano.")