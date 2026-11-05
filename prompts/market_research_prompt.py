from langchain_core.prompts import ChatPromptTemplate

market_research_prompt = ChatPromptTemplate.from_template("""
Give me a basic market research overview of {company}.

Cover:

1. Company overview
2. Main products/services
3. Target customers
4. Business model
5. Main competitors
6. How the company uses AI
7. Key strengths
8. Key risks
""")