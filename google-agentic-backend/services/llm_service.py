from pydantic_ai.models.openai import OpenAIModel
from openai import OpenAI, AsyncOpenAI
from configs.config import get_settings
import os
settings = get_settings()

api_key=settings.agent_creds.llm_api_key.get_secret_value()
openai_api_key=settings.agent_creds.openai_api_key.get_secret_value()

def get_async_openai_llm_client():
    return AsyncOpenAI(
        api_key=openai_api_key,
        base_url="https://api.openai.com/v1"
    )

def get_async_llm_client():
    return AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.theagentic.ai/v1"
    )


def get_model_client():
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = "https://api.theagentic.ai/v1"
    return OpenAIModel(
        model_name="agentic-large",
    )