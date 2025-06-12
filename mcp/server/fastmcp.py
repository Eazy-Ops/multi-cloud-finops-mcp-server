from typing import TypedDict
from langchain.agents import initialize_agent, AgentType
from langgraph.graph import StateGraph, END
from langchain.schema import SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from clouds.aws.tools import get_cost as get_aws_cost, run_finops_audit as run_aws_finops_audit
from clouds.gcp.tools import get_gcp_cost, run_gcp_finops_audit
from clouds.azure.tools import get_azure_cost, run_azure_finops_audit

class AgentState(TypedDict):
    input: str
    output: str

# Initialize LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro-latest",
    temperature=0.8,
    top_p=0.9,
    max_output_tokens=4096,
    convert_system_message_to_human=True,
    google_api_key="AIzaSyA_HbDQe67F7az98YYfOXHTQ_h39Qqvp-E"
)

# Register all tools (AWS, GCP, Azure)
agent_executor = initialize_agent(
    tools=[
        get_aws_cost, run_aws_finops_audit,
        get_gcp_cost, run_gcp_finops_audit,
        get_azure_cost, run_azure_finops_audit
    ],
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True,
    agent_kwargs={
        "system_message": SystemMessage(content="""
            You are a Multi-Cloud FinOps assistant. You can help users:
            - Get cost breakdowns for AWS, GCP, Azure
            - Run FinOps audits for cost-saving insights (e.g., unused resources, budget tracking)
            Decide which cloud's tool to invoke based on user input.
        """)
    }
)

# LangGraph execution plan
workflow = StateGraph(state_schema=AgentState)
workflow.add_node("run_agent", agent_executor)
workflow.set_entry_point("run_agent")
workflow.add_edge("run_agent", END)
graph_executor = workflow.compile()

# CLI runner
import asyncio
import nest_asyncio
nest_asyncio.apply()

def run():
    while True:
        try:
            user_input = input("Ask me your Multi-Cloud FinOps question (or 'exit'): ")
            if user_input.strip().lower() in ["exit", "quit"]:
                break
            result = asyncio.run(graph_executor.ainvoke({"input": user_input}))
            print(result.get("output") or result)
        except Exception as e:
            print("Error:", e)

