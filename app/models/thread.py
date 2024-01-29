class Thread:
    def __init__(self):
        self.thread = None

    def add_thread(self, thread_id, user_id, last_message, metadata):
        self.thread = {
            "user_id": user_id,
            "thread_id": thread_id,
            "last_message": last_message,
            "metadata": metadata
        }

    def to_dict(self):
        return self.thread if self.thread else {}