from openai import OpenAI
from dotenv import load_dotenv
import os

# Load .env once here
load_dotenv()

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_openai() -> OpenAI:
    return _client
