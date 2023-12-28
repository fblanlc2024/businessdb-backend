from flask import current_app, Blueprint
from flask_socketio import emit
from openai import OpenAI
import base64
import subprocess
import io
import base64
import httpx

client = OpenAI()
ai_routes_bp = Blueprint('ai_routes', __name__)

audio_buffer = io.BytesIO()

def setup_socket_events(socketio):

    @socketio.on('text-generator')
    def handle_message(data):
        user_input = data['message']
        system_role = 'You are a friendly assistant providing details about a business application.'

        # Call OpenAI's GPT-3.5 model
        completion = client.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        messages=[
            {"role": "system", "content": system_role},
            {"role": "user", "content": user_input}
        ],
        stream=True,
        )

        for chunk in completion:
            if chunk.choices[0].delta.content:
                emit('stream_chunk', {'content': chunk.choices[0].delta.content})


    @socketio.on('audio_data')
    def handle_audio_data(json):
        current_app.logger.info("Received audio data event")
        base64_data = json['data']
        audio_data = base64.b64decode(base64_data.split(',')[1])

        # Append the audio data to the buffer
        audio_buffer.write(audio_data)
        current_app.logger.info(f"Size of received audio data: {len(audio_data)} bytes")


    @socketio.on('end_audio_stream')
    def handle_end_audio_stream():
        # Reset buffer to the beginning
        audio_buffer.seek(0)
        if len(audio_buffer.getvalue()) == 0:
            print("Error: No data received in buffer")
            return  # Exit if buffer is empty

        try:
            # Convert the audio in the buffer to WAV format using FFmpeg
            wav_buffer = convert_to_wav(audio_buffer)

            current_app.logger.info(f"Size of audio buffer for Whisper: {len(wav_buffer.getvalue())} bytes")
            
            # Process the WAV audio data with Whisper
            transcription = process_with_whisper(wav_buffer)
            emit('transcription_result', {'transcript': transcription})

            # Process transcription with GPT-3.5 Turbo
            process_with_gpt(transcription)
        except Exception as e:
            current_app.logger.error(f"Error processing audio data: {e}")

        # Clear the buffer for next use
        audio_buffer.truncate(0)
        audio_buffer.seek(0)

def convert_to_wav(input_buffer):
    # Ensure the buffer's read pointer is at the start
    input_buffer.seek(0)

    # Use FFmpeg to convert the audio data to WAV format
    process = subprocess.Popen(
        ['ffmpeg', '-i', '-', '-ac', '1', '-ar', '16000', '-f', 'wav', '-'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    wav_data, error = process.communicate(input=input_buffer.read())

    if process.returncode != 0:
        raise ValueError(f"FFmpeg error: {error.decode()}")

    # Return the wav data as a BytesIO object
    return io.BytesIO(wav_data)


def process_with_whisper(audio_buffer):
    # Ensure the buffer's read pointer is at the start
    audio_buffer.seek(0)

    # Naming the BytesIO object as required
    named_audio_buffer = io.BytesIO(audio_buffer.getvalue())
    named_audio_buffer.name = 'audio.wav'

    try:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=named_audio_buffer
        )

        transcription = response.text
        current_app.logger.info(f"Transcription result: {transcription}")
        return transcription
    except Exception as e:
        current_app.logger.error(f"Error in Whisper transcription: {e}")
        return ""

def process_with_gpt(transcription):
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=[
                {"role": "system", "content": "You are a friendly assistant helping with my business application."},
                {"role": "user", "content": transcription}
            ],
            stream=True,
        )

        # Accumulate all response chunks into a single string
        full_response = ""
        for chunk in completion:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content.strip()

        if full_response:
            # Once all chunks are accumulated, process the complete response with TTS
            process_with_tts(full_response)

    except Exception as e:
        current_app.logger.error(f"GPT-3.5 Turbo streaming failed: {e}")


def process_with_tts(text):
    openai_api_key = current_app.config['OPENAI_API_KEY']

    try:
        url = "https://api.openai.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "tts-1",
            "voice": "shimmer",
            "input": text
        }

        with httpx.stream("POST", url, headers=headers, json=data) as response:
            audio_chunks = [chunk for chunk in response.iter_bytes(chunk_size=4096) if chunk]
            complete_audio = b''.join(audio_chunks)
            encoded_audio = base64.b64encode(complete_audio).decode('utf-8')
            emit('tts_stream_full', {'audio_data': encoded_audio})

    except Exception as e:
        current_app.logger.error(f"Error in TTS streaming: {e}")