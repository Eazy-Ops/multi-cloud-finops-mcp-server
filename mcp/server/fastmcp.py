from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from clouds.aws.tools import get_cost as get_aws_cost, run_finops_audit as run_aws_finops_audit
from clouds.gcp.tools import get_gcp_cost, run_gcp_finops_audit
from clouds.azure.tools import get_azure_cost, run_azure_finops_audit


class AgentState(TypedDict):
    messages: list
    output: str

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro-latest",
    temperature=0.8,
    top_p=0.9,
    max_output_tokens=4096,
    google_api_key="AIzaSyA_HbDQe67F7az98YYfOXHTQ_h39Qqvp-E"
)

tools = [
    get_aws_cost, run_aws_finops_audit,
    get_gcp_cost, run_gcp_finops_audit,
    get_azure_cost, run_azure_finops_audit
]

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a Multi-Cloud FinOps assistant. You can help users:\n"
               "- Get cost breakdowns for AWS, GCP, Azure\n"
               "- Run FinOps audits for cost-saving insights\n"
               "Decide which cloud's tool to invoke based on user input."),
    MessagesPlaceholder(variable_name="messages")
])


agent_executor = create_react_agent(
    model=llm,
    tools=tools,
    prompt=prompt
)

workflow = StateGraph(state_schema=AgentState)
workflow.add_node("run_agent", agent_executor)
workflow.set_entry_point("run_agent")
workflow.add_edge("run_agent", END)
graph_executor = workflow.compile()

import asyncio
import nest_asyncio
nest_asyncio.apply()

def run():
    while True:
        try:
            user_input = input("Ask me your Multi-Cloud FinOps question (or 'exit'): ")
            if user_input.strip().lower() in ["exit", "quit"]:
                break
            print("SENDING PROMPT:", user_input)
            result = asyncio.run(graph_executor.ainvoke({
                "messages": [{"role": "user", "content": user_input}],
                "output": ""
            }))
            messages = result.get("messages", [])
            ai_responses = [msg for msg in messages if msg.type == "ai"]
            if ai_responses:
                print(ai_responses[-1].content)
            else:
                print("No response from the assistant.")
        except Exception as e:
            print("Error: due to this exception", e)

