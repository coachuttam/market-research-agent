from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

from prompts.market_research_prompt import market_research_prompt

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini")

company = input("Enter company name: ")

messages = market_research_prompt.invoke({
    "company": company
})

result = llm.invoke(messages)

print(result.content)