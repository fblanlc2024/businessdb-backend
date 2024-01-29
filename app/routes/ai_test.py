import time
from openai import OpenAI

client = OpenAI()

# Create a thread and store its ID
message_thread = client.beta.threads.create(
    messages=[
        {"role": "user", "content": "Hello, what is AI?"},
        {"role": "user", "content": "How does AI work? Explain it in simple terms."}
    ]
)
thread_id = message_thread.id
print(f"THREAD ID: {thread_id}")

# Create a run for the assistant to process the message
run = client.beta.threads.runs.create(
    thread_id=thread_id,
    assistant_id="asst_chhg0NIxpNlVi2NS9H4I3LMI"
)
print(f"Created run with ID: {run.id}")

# Function to poll for the run's status
def poll_for_run_status(thread_id, run_id):
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run_id
        )
        if run.status == 'completed':
            break
        else:
            print(f"Run status: {run.status}. Polling again in 3 seconds.")
            time.sleep(3)
    return run

# Poll for the run's status until it is 'completed'
run_status = poll_for_run_status(thread_id, run.id)

# Retrieve and print all messages from the completed thread
thread_messages = client.beta.threads.messages.list(thread_id)
for message in thread_messages.data:
    print(f"{message.role.title()}'s Message: {message.content}")