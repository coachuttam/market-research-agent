from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain_core.messages import ToolMessage

from tools.web_search import web_search

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini")

llm_with_tools = llm.bind_tools([web_search])

question = "What is Garmin's latest AI strategy?"

response = llm_with_tools.invoke(question)

print("LLM requested tool:")
print(response.tool_calls)

tool_call = response.tool_calls[0]

tool_result = web_search.invoke(tool_call["args"])

print("\nSearch results:")
print(tool_result)

final_response = llm_with_tools.invoke([
    {
        "role": "user",
        "content": question
    },
    response,
    ToolMessage(
        content=str(tool_result),
        tool_call_id=tool_call["id"]
    )
])

print("\nFinal answer:")
print(final_response.content)