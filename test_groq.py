from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import os 

load_dotenv()

# Initialize the LLM
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0  # 0 = deterministic output, better for classification tasks
)

# Send a test message
response = llm.invoke([
    HumanMessage(content="Say hello and tell me what model you are. Keep it under 2 sentences.")
])

print("Groq response:", response.content)