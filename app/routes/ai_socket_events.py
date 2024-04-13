from flask import current_app, Blueprint, jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_socketio import emit
from openai import OpenAI
import base64, subprocess, io, base64, httpx, time, uuid
from io import BytesIO
from ..models.thread import Thread
from ..classes.business.data_handling import DataHandler
from ..classes.email.email import Email
import json
import requests
import re
from app import db, redis_client
from .util_routes import is_user_admin
client = OpenAI()
ai_routes_bp = Blueprint('ai_routes', __name__)

audio_buffer = io.BytesIO()
threads_collection = db.threads
accounts_collection = db.accounts
google_accounts_collection = db.google_accounts

def setup_socket_events(socketio):
    # Incoming assistant request - checking if there are files and processing the request to call the appropriate chain of methods
    @socketio.on('assistant-request')
    def handle_assistant_request(data):
        user_id = data['user_id']
        thread_id = data.get('thread_id', None)
        user_input = data['message']
        current_app.logger.info(f"Received user input from thread ID {thread_id}: {user_input}")

        file_ids = []
        if 'files' in data and data['files']:
            for file_info in data['files']:
                file_content = base64.b64decode(file_info['content'])
                file_stream = BytesIO(file_content)
                file_stream.name = file_info['name']
                file_response = client.files.create(
                    file=file_stream,
                    purpose='assistants'
                )
                current_app.logger.info(f"file response from openai: {file_response}")
                file_ids.append(file_response.id)
                current_app.logger.info(f"file id that was transferred in: {file_response.id}")
                current_app.logger.info(f"file ids repo: {file_ids}")

        assistant_id = current_app.config['ASSISTANT_ID']
        response_data = get_response_from_openai(user_id, user_input, assistant_id, file_ids, thread_id)

        response_text = response_data.get('message') if response_data.get('message') else "No response from assistant."
        thread_id = response_data.get('thread_id')
        title = response_data.get('title')
        current_app.logger.info(f"Emitting response to user: {response_text}")
        socketio.emit('assistant-response', {'content': response_text, 'thread_id': thread_id, 'title': title})

        if response_data.get('thread_id'):
            update_result = threads_collection.update_one(
                {'thread_id': response_data.get('thread_id')},
                {'$set': {'last_message': user_input, 'last_response': response_text}}
            )
            current_app.logger.info(f"Database update result: {update_result.modified_count} documents modified")

    # Socket event listener for GPT 3.5
    @socketio.on('text-generator')
    def handle_message(data):
        user_input = data['message']
        system_role = 'You are a friendly assistant providing details about a business application.'

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

    # Incoming audio data is written to a buffer, continuously written to until user hits the stop button
    @socketio.on('audio_data')
    def handle_audio_data(json):
        current_app.logger.info("Received audio data event")
        base64_data = json['data']
        audio_data = base64.b64decode(base64_data.split(',')[1])

        audio_buffer.write(audio_data)
        current_app.logger.info(f"Size of received audio data: {len(audio_data)} bytes")

    # Ends the audio stream and then converts to a .wav file for the Whisper API to transcribe it
    @socketio.on('end_audio_stream')
    def handle_end_audio_stream():
        audio_buffer.seek(0)
        if len(audio_buffer.getvalue()) == 0:
            print("Error: No data received in buffer")
            return

        try:
            wav_buffer = convert_to_wav(audio_buffer)

            current_app.logger.info(f"Size of audio buffer for Whisper: {len(wav_buffer.getvalue())} bytes")

            transcription = process_with_whisper(wav_buffer)
            emit('transcription_result', {'transcript': transcription})

            process_with_gpt(transcription)
        except Exception as e:
            current_app.logger.error(f"Error processing audio data: {e}")

        audio_buffer.truncate(0)
        audio_buffer.seek(0)

# Gets the user ID for the various threads linked with the respective user ID
@ai_routes_bp.route('/get-user-threads/<user_id>', methods=['GET'])
def get_user_threads(user_id):
    try:
        user_threads = threads_collection.find({'user_id': user_id})

        threads_info = []
        for thread in user_threads:
            thread_id = thread.get('thread_id')
            thread_data = {
                'title': thread['metadata'].get('title', 'Untitled'),
                'thread_id': thread_id
            }
            threads_info.append(thread_data)

        current_app.logger.info(f"THREADS_INFO: {threads_info}")
        return jsonify(threads_info), 200
    except Exception as e:
        error_message = f"Error fetching threads for user {user_id}: {e}"
        current_app.logger.error(error_message)
        return jsonify({'error': error_message}), 500

# Loads messages under a certain thread
@ai_routes_bp.route('/load-messages/<thread_id>', methods=['GET'])
def load_message(thread_id):
    try:
        thread_objects = client.beta.threads.messages.list(thread_id)
        current_app.logger.info(f"thread obj list: {thread_objects}")
        thread_messages = extract_messages(thread_objects)
        current_app.logger.info(f"thread msg list: {thread_messages}")
        return jsonify(thread_messages), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching messages for thread ID {thread_id}: {e}")
        return jsonify({'error': 'Unable to fetch messages'}), 500

# Function that the AI can call that automatically adds a business.
@ai_routes_bp.route('/auto_add_business', methods=['POST'])
def auto_add_business_route():
    data = request.json
    current_app.logger.info(f"data received: {data}")
    return DataHandler.add_business(data)

# Uses ffmpeg to convert the audio buffer collected from the frontend into a .wav stream
def convert_to_wav(input_buffer):
    input_buffer.seek(0)

    process = subprocess.Popen(
        ['ffmpeg', '-i', '-', '-ac', '1', '-ar', '16000', '-f', 'wav', '-'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    wav_data, error = process.communicate(input=input_buffer.read())

    if process.returncode != 0:
        raise ValueError(f"FFmpeg error: {error.decode()}")

    return io.BytesIO(wav_data)

# Uses OpenAI's Whisper API to transcribe the .wav file
def process_with_whisper(audio_buffer):
    audio_buffer.seek(0)

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

# Text is passed into a faster GPT 3.5 Turbo version for quicker response time
def process_with_gpt(transcription):
    try:
        system_prompt = current_app.config['VOICE_ASSISTANT_PROMPT']
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcription}
            ],
            stream=True,
        )

        full_response = ""
        for chunk in completion:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content

        if full_response:
            process_with_tts(full_response)

    except Exception as e:
        current_app.logger.error(f"GPT-3.5 Turbo streaming failed: {e}")

# Creates a title for a newly initialized chat
def create_title(message):
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=[
                {"role": "system", "content": "Create a 2-4 word title summarizing this user input."},
                {"role": "user", "content": message}
            ],
            max_tokens=8
        )

        current_app.logger.info(f"the title response: {completion}")

        if completion.choices and completion.choices[0].message and completion.choices[0].message.content:
            title = completion.choices[0].message.content.strip()
            return title
        else:
            return "General Inquiry"
    except Exception as e:
        current_app.logger.error(f"GPT-3.5 Turbo streaming failed: {e}")
        return "General Inquiry"

# Uses Elevenlabs API to convert the GPT 3.5's response into an audio stream
def process_with_tts(text):
    xi_api_key = current_app.config['ELEVENLABS_API_KEY']

    try:
        url = "https://api.elevenlabs.io/v1/text-to-speech/pNInz6obpgDQGcFmaJgB"

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": xi_api_key
        }

        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        response = requests.post(url, json=data, headers=headers)
        
        audio_chunks = [chunk for chunk in response.iter_content(chunk_size=4096) if chunk]
        complete_audio = b''.join(audio_chunks)
        encoded_audio = base64.b64encode(complete_audio).decode('utf-8')
        
        emit('tts_stream_full', {'audio_data': encoded_audio})

    except Exception as e:
        current_app.logger.error(f"Error in TTS streaming: {e}")

# Creates a new thread or adds to an existing one, depending on whether a thread_id is passed into the function or not
def create_or_add_to_thread(user_id, message, file_ids, thread_id=None):
    current_app.logger.info(f"Creating or retrieving thread for User ID: {user_id}, Thread ID: {thread_id}")
    current_app.logger.info(f"file ids in create or retrieve thread: {file_ids}")

    if thread_id and not thread_id.startswith('temp_'):
        existing_thread = threads_collection.find_one({'thread_id': thread_id})
        existing_title = existing_thread['metadata']['title'] if existing_thread else None
        if existing_thread:
            current_app.logger.info(f"Existing thread found: {thread_id}")
            try:
                if file_ids:
                    current_app.logger.info(f"message file id param: {file_ids}")
                    response = client.beta.threads.messages.create(
                        thread_id=thread_id,
                        role="user",
                        content=message,
                        file_ids=file_ids
                    )
                else:
                    response = client.beta.threads.messages.create(
                        thread_id=thread_id,
                        role="user",
                        content=message
                    )
                current_app.logger.info(f"response from openai with file?? {response}")
                current_app.logger.info(f"New message added to existing thread: {thread_id}")
                return thread_id, existing_title
            except Exception as e:
                current_app.logger.error(f"Error adding message to existing thread: {e}")
                return None
        else:
            current_app.logger.info(f"No existing thread found with ID: {thread_id}")

    title = create_title(message)
    metadata = {"uuid": str(uuid.uuid4()), "title": title}

    messages_content = {"role": "user", "content": message}
    if file_ids:
        messages_content["file_ids"] = file_ids

    try:
        message_thread = client.beta.threads.create(
            messages=[messages_content],
            metadata=metadata
        )
        new_thread_id = message_thread.id
        current_app.logger.info(f"New thread created with ID: {new_thread_id}")

        new_thread = Thread()
        new_thread.add_thread(new_thread_id, user_id, message, metadata)
        threads_collection.insert_one(new_thread.to_dict())
        current_app.logger.info(f"new thread id: {new_thread_id}")
        return new_thread_id, title
    except Exception as e:
        current_app.logger.error(f"Error creating new thread: {e}")
        return None
    
def create_run(thread_id, assistant_id):
    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
    return run

# Periodically polls (every 3 seconds) for the run status. If it requires action, then it calls the respective function and submits the tool call to garner a response from the assistant.
def poll_for_run_status(thread_id, run_id, user_id):
    tool_call_id = None
    function_output = None
    arguments_section = None

    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        current_app.logger.debug(f"Polling for Run Status - Run ID: {run_id}, Run Status: {run}")

        if run.status == 'completed':
            break
        elif run.status == 'requires_action':
            current_app.logger.info(f"Action required for Run ID: {run_id}")

            if run.required_action and run.required_action.submit_tool_outputs:
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                if tool_calls and len(tool_calls) > 0:
                    tool_call_id = tool_calls[0].id
                    current_app.logger.info(f"Extracted tool_call_id: {tool_call_id}")
                    function_arguments = tool_calls[0].function.arguments

                    if function_arguments:
                        try:
                            formatted_arguments = re.sub(r'\\n', '\\n', function_arguments)
                            arguments_section = json.loads(formatted_arguments)

                            current_app.logger.info(f"Extracted arguments section: {arguments_section}")
                            if 'business_data' in arguments_section:
                                try:
                                    current_app.logger.info(f"Calling auto_add_business now...")
                                    response, status_code = auto_add_business(arguments_section['business_data'], user_id)
                                    submit_tool_output(thread_id, run_id, tool_call_id, True if status_code == 201 else False)
                                except Exception as e:
                                    current_app.logger.error(f"Error adding business: {e}")
                                    submit_tool_output(thread_id, run_id, tool_call_id, False)
                            elif 'businesses_data' in arguments_section:
                                try:
                                    current_app.logger.info(f"Calling auto_add_multiple_businesses now...")
                                    response, status_code = auto_add_multiple_businesses(arguments_section['businesses_data'], user_id)
                                    submit_tool_output(thread_id, run_id, tool_call_id, True if status_code == 201 else False)
                                except Exception as e:
                                    current_app.logger.error(f"Error adding multiple businesses: {e}")
                                    submit_tool_output(thread_id, run_id, tool_call_id, False)
                            elif 'issue_description' in arguments_section:
                                try:
                                    current_app.logger.info(f"email service lol here is the issue description: {arguments_section['issue_description']}")
                                    send_ai_email(arguments_section, thread_id)
                                    submit_tool_output(thread_id, run_id, tool_call_id, True)
                                except Exception as e:
                                    current_app.logger.error(f"email encountered an error: {e}")
                                    submit_tool_output(thread_id, run_id, tool_call_id, False)

                        except json.JSONDecodeError as e:
                            current_app.logger.error(f"Error decoding arguments section: {e}")
                            submit_tool_output(thread_id, run_id, tool_call_id, False)

                    break
            else:
                current_app.logger.error("Unable to extract tool_call_id")
                break

        else:
            current_app.logger.info(f"Run status: {run.status}. Polling again in 3 seconds.")
            steps = client.beta.threads.runs.steps.list(run_id=run_id, thread_id=thread_id)
            for step in steps.data:
                current_app.logger.info(f"step (check for code interpreter!) {step}")
            time.sleep(3)

    return run, tool_call_id, function_output, arguments_section

# Main function to chain the series of assistant thread calls. Returns an updated list of messages and title if applicable.
def get_response_from_openai(user_id, user_input, assistant_id, file_ids, thread_id=None):
    thread_id, title = create_or_add_to_thread(user_id, user_input, file_ids, thread_id)
    current_app.logger.info(f"Using thread ID: {thread_id} for response retrieval")

    run = create_run(thread_id, assistant_id)
    run_id = run.id
    current_app.logger.debug(f"Created Run - Run ID: {run_id}, Run Details: {run}")

    run_status, tool_call_id, function_output, arguments_section = poll_for_run_status(thread_id, run_id, user_id)

    thread_messages = client.beta.threads.messages.list(thread_id)
    current_app.logger.debug(f"Thread Messages: {thread_messages}")

    assistant_message = None

    for message in reversed(thread_messages.data):
        if message.role == 'assistant' and message.run_id == run_id:
            assistant_message = message.content[0].text.value if message.content else None
            break

    current_app.logger.info(f"Assistant's response: {assistant_message}")
    if thread_id:
        update_result = threads_collection.update_one(
            {'thread_id': thread_id},
            {'$set': {'last_message': user_input, 'last_response': assistant_message}}
        )
        current_app.logger.debug(f"Database update result: {update_result}")

    response = {'message': assistant_message, 'tool_call_id': tool_call_id, 'thread_id': thread_id, 'run_id': run_id, 'title': title}
    current_app.logger.info(f"RESPONSE FROM MAIN OPENAI METHOD: {response}")
    return response

def extract_messages(data):
    extracted_messages = []
    message_list = list(data)

    for message in reversed(message_list):
        role = message.role
        text_content = None

        if message.content and len(message.content) > 0:
            for content_item in message.content:
                if content_item.type == 'text':
                    text_content = content_item.text.value
                    break

        extracted_messages.append({'role': role, 'text': text_content})

    return extracted_messages

# Function that the AI calls to automatically add a singular business.
def auto_add_business(business_data, user_id):
    current_app.logger.info(f"Received business data: {business_data} and user_id: {user_id}")
    admin_status = check_admin_status(user_id)
    current_app.logger.info(f"Admin status at the time of requesting the add_business endpoint: {admin_status}")
    if not admin_status:
        return {"error": "User not authenticated or not an admin"}, 403

    try:
        if business_data:
            current_app.logger.info(f"main business data: {business_data}")
            response, status_code = DataHandler.add_business(business_data)
            return response, status_code
        else:
            current_app.logger.error("Missing 'business_data' key in the provided data")
            return {"error": "Invalid data format: Missing 'business_data' key"}, 400
    except Exception as e:
        current_app.logger.error(f"Error in adding business: {e}")
        return {"error": str(e)}, 500

# Function that the AI calls to automatically add multiple businesses.
def auto_add_multiple_businesses(businesses_data, user_id):
    current_app.logger.info(f"Received businesses data for user_id: {user_id}")
    current_app.logger.info(f"received data in multiple businesses method: {businesses_data}")
    admin_status = check_admin_status(user_id)
    current_app.logger.info(f"Admin status at the time of requesting the add_multiple_businesses endpoint: {admin_status}")
    if not admin_status:
        return jsonify({"error": "User not authenticated or not an admin"}), 403

    if not isinstance(businesses_data, list):
        current_app.logger.error("Invalid data format: 'businesses_data' should be a list of business data objects.")
        return jsonify({"error": "Invalid data format: 'businesses_data' should be a list of business data objects."}), 400
    
    try:
        response = DataHandler.add_multiple_businesses(businesses_data)
        return response
    except Exception as e:
        current_app.logger.error(f"Error in adding multiple businesses: {e}")
        return jsonify({"error": str(e)}), 500

# Checks admin status for authentication to add multiple businesses via a Redis memory cache server
def check_admin_status(user_id):
    current_app.logger.info(f"received user_id for admin status checking: {user_id}")
    cache_key = f"admin_status:{user_id}"
    is_admin_bytes = redis_client.get(cache_key)

    if is_admin_bytes is None:
        is_admin = is_user_admin(user_id, accounts_collection, google_accounts_collection)
        current_app.logger.info(f"{user_id} admin's status is.... {is_admin}")
        redis_client.setex(cache_key, 3600, 'True' if is_admin else 'False')
    else:
        is_admin_str = is_admin_bytes.decode('utf-8')
        is_admin = is_admin_str == 'True'
    
    current_app.logger.info(f"{user_id} admin status in check_admin_status: {is_admin}")
    return is_admin
# Submits tool output and broadcasts to user whether there was a success or not.
def submit_tool_output(thread_id, run_id, tool_call_id, output):
    current_app.logger.info(f"Submitting tool output - Thread ID: {thread_id}, Run ID: {run_id}, Tool Call ID: {tool_call_id}, Output: {output}")
    try:
        run = client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=[{"tool_call_id": tool_call_id, "output": output}]
        )
        current_app.logger.info(f"new run message: {run}")
        current_app.logger.debug(f"Tool output submitted successfully.")
    except Exception as e:
        current_app.logger.error(f"Error submitting tool output: {e}")

def send_ai_email(email_info, thread_id):
    from_email = current_app.config['SENDING_EMAIL']
    password = current_app.config['SENDING_EMAIL_PASSWORD']
    to_email = current_app.config['RECEIVING_EMAIL']
    subject = f"Someone reported an issue with your business application!"
    message_result = fetch_messages(thread_id)
    body = f"Issue Description:\n{email_info['issue_description']}\n\nThread Messages:\n{message_result}"

    current_app.logger.info(f"Sending email with subject: {subject}")
    return Email.send_email(from_email, password, to_email, subject, body)


def format_messages(messages):
    formatted_text = ""
    for msg in messages:
        role = msg['role'].capitalize()
        text = msg['text']
        formatted_text += f"{role}: {text}\n\n"
    return formatted_text.strip()

def fetch_messages(thread_id):
    try:
        response, status_code = load_message(thread_id)
        if status_code == 200:
            messages = response.get_json()
            return format_messages(messages)
        else:
            current_app.logger.info(f"Failed to fetch messages with status code: {status_code}")
            return "Unable to fetch messages due to an error."
    except Exception as e:
        current_app.logger.info(f"Failed to fetch messages: {e}")
        return "Failed to fetch messages due to an exception."