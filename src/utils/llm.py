import os

from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from openai import OpenAI


load_dotenv()


llm = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0,
    api_key=os.getenv("OPENAI_API_KEY")
)


embedding_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def create_embedding(text: str):

    response = embedding_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    return response.data[0].embedding