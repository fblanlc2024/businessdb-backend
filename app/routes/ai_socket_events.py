from flask import current_app, Blueprint, jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_socketio import emit
from openai import OpenAI
import base64, subprocess, io, base64, httpx, time, uuid
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
assistant_id = 'asst_chhg0NIxpNlVi2NS9H4I3LMI'
threads_collection = db.threads
accounts_collection = db.accounts
google_accounts_collection = db.google_accounts

def setup_socket_events(socketio):
    @socketio.on('assistant-request')
    def handle_assistant_request(data):
        user_id = data['user_id']
        thread_id = data.get('thread_id', None)
        user_input = data['message']
        current_app.logger.info(f"Received user input from thread ID {thread_id}: {user_input}")

        response_data = get_response_from_openai(user_id, user_input, assistant_id, thread_id)

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

@ai_routes_bp.route('/get-user-threads/<user_id>', methods=['GET'])
def get_user_threads(user_id):
    try:
        verify_jwt_in_request()
        current_user = get_jwt_identity()
    except Exception as jwt_error:
        current_app.logger.warning(f"JWT authentication failed: {jwt_error}")

        # Fallback to OAuth token
        oauth_token = request.cookies.get('access_token_cookie')
        current_app.logger.info(f"OAuth token from cookie: {oauth_token}")
        if oauth_token:
            current_user = oauth_token
        else:
            current_app.logger.error("User not authenticated")
            return jsonify({"error": "User not authenticated"}), 401

    # Check if the user is an admin
    is_admin = is_user_admin(current_user, accounts_collection, google_accounts_collection)
    check_admin_status(current_user)

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
        current_app.logger.error(f"Error fetching threads for user {user_id}: {e}")
        return jsonify({'error': 'Unable to fetch threads'}), 500

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

@ai_routes_bp.route('/auto_add_business', methods=['POST'])
def auto_add_business_route():
    data = request.json
    current_app.logger.info(f"data received: {data}")
    return DataHandler.add_business(data)

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

def create_title(message):
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=[
                {"role": "system", "content": "Create a 2-4 word title summarizing this user input."},
                {"role": "user", "content": message}
            ],
            max_tokens=10
        )

        current_app.logger.info(f"the title response: {completion}")

        # Extracting the title from the completion response
        if completion.choices and completion.choices[0].message and completion.choices[0].message.content:
            title = completion.choices[0].message.content.strip()
            return title
        else:
            return "General Inquiry"
    except Exception as e:
        current_app.logger.error(f"GPT-3.5 Turbo streaming failed: {e}")
        return "General Inquiry"

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

def create_or_retrieve_thread(user_id, message, thread_id=None):
    current_app.logger.info(f"Creating or retrieving thread for User ID: {user_id}, Thread ID: {thread_id}")

    # Check if the provided thread_id is an existing one and not a temporary ID
    if thread_id and not thread_id.startswith('temp_'):
        existing_thread = threads_collection.find_one({'thread_id': thread_id})
        existing_title = existing_thread['metadata']['title'] if existing_thread else None
        if existing_thread:
            current_app.logger.info(f"Existing thread found: {thread_id}")
            try:
                # Add the new message to the existing thread
                response = client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=message
                )
                current_app.logger.info(f"New message added to existing thread: {thread_id}")
                return thread_id, existing_title
            except Exception as e:
                current_app.logger.error(f"Error adding message to existing thread: {e}")
                return None  # Return None if error occurs
        else:
            current_app.logger.info(f"No existing thread found with ID: {thread_id}")

    # Create a new thread if no existing thread found or thread_id is 'temp_'
    title = create_title(message)
    metadata = {"uuid": str(uuid.uuid4()), "title": title}
    try:
        message_thread = client.beta.threads.create(
            messages=[{"role": "user", "content": message}],
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

def poll_for_run_status(thread_id, run_id, user_id):
    tool_call_id = None
    function_output = None
    arguments_section = None  # Initialize arguments_section variable

    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        current_app.logger.debug(f"Polling for Run Status - Run ID: {run_id}, Run Status: {run}")

        if run.status == 'completed':
            break
        elif run.status == 'requires_action':
            current_app.logger.info(f"Action required for Run ID: {run_id}")

            # Extracting tool_call_id when action is required
            if run.required_action and run.required_action.submit_tool_outputs:
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                if tool_calls and len(tool_calls) > 0:
                    tool_call_id = tool_calls[0].id
                    current_app.logger.info(f"Extracted tool_call_id: {tool_call_id}")

                    # Extract the "arguments" section from the function's arguments
                    function_arguments = tool_calls[0].function.arguments
                    if function_arguments:
                        try:
                            # Replace escape characters and convert to valid JSON
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
                    
                    # Retrieve the run steps to get the function output
                    steps = client.beta.threads.runs.steps.list(run_id=run_id, thread_id=thread_id)
                    for step in steps.data:
                        if step.type == 'tool_calls' and step.status == 'completed':
                            function_output = step.step_details.tool_calls[0].function.output
                            current_app.logger.debug(f"Function output: {function_output}")
                    break
            else:
                current_app.logger.error("Unable to extract tool_call_id")
                break

        else:
            current_app.logger.info(f"Run status: {run.status}. Polling again in 3 seconds.")
            time.sleep(3)

    return run, tool_call_id, function_output, arguments_section

def get_response_from_openai(user_id, user_input, assistant_id, thread_id=None):
    thread_id, title = create_or_retrieve_thread(user_id, user_input, thread_id)
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
    # Convert the data to a list for reversing
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

def auto_add_business(business_data, user_id):
    current_app.logger.info(f"Received business data: {business_data} and user_id: {user_id}")
    admin_status = check_admin_status(user_id)
    current_app.logger.info(f"Admin status at the time of requesting the add_business endpoint: {admin_status}")
    if not admin_status:
        # Admin status check failed
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

def check_admin_status(user_id):
    current_app.logger.info(f"received user_id for admin status checking: {user_id}")
    cache_key = f"admin_status:{user_id}"
    is_admin_bytes = redis_client.get(cache_key)  # Attempt to get the cached value

    if is_admin_bytes is None:
        # If not cached, determine admin status and cache the result
        is_admin = is_user_admin(user_id, accounts_collection, google_accounts_collection)
        current_app.logger.info(f"{user_id} admin's status is.... {is_admin}")
        # Cache the admin status as a string ('True' or 'False')
        redis_client.setex(cache_key, 3600, 'True' if is_admin else 'False')
    else:
        # If cached, decode the bytes to string and convert to boolean
        is_admin_str = is_admin_bytes.decode('utf-8')
        is_admin = is_admin_str == 'True'
    
    current_app.logger.info(f"{user_id} admin status in check_admin_status: {is_admin}")
    return is_admin

def submit_tool_output(thread_id, run_id, tool_call_id, output):
    current_app.logger.info(f"Submitting tool output - Thread ID: {thread_id}, Run ID: {run_id}, Tool Call ID: {tool_call_id}, Output: {output}")
    try:
        # Submitting the tool output back to OpenAI
        run = client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=[{"tool_call_id": tool_call_id, "output": output}]
        )
        current_app.logger.debug(f"Tool output submitted successfully.")
    except Exception as e:
        current_app.logger.error(f"Error submitting tool output: {e}")

def send_ai_email(email_info, thread_id):
    from_email = current_app.config['SENDING_EMAIL']
    password = current_app.config['SENDING_EMAIL_PASSWORD']
    to_email = current_app.config['RECEIVING_EMAIL']
    subject = f"{email_info['username']} reported an issue with your business application!"
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

