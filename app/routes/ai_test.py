import time
from openai import OpenAI

client = OpenAI()

from openai import OpenAI
client = OpenAI()

my_assistants = client.beta.assistants.list(
    order="desc",
    limit="2",
)
print(my_assistants.data)