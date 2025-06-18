import asyncio
from typing import TypedDict

import nest_asyncio
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent
from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory

from clouds.aws.tools import (analyze_aws_disks, analyze_aws_network,
                              analyze_cloudwatch_logs_cost,
                              analyze_ec2_rightsizing, analyze_rds_instances,
                              analyze_s3_optimization)
from clouds.aws.tools import get_cost as get_aws_cost
from clouds.aws.tools import list_aws_profiles
from clouds.aws.tools import run_finops_audit as run_aws_finops_audit
from clouds.azure.tools import (analyze_azure_disks, analyze_azure_network, analyze_azure_storage,
                                get_azure_cost, run_azure_finops_audit, analyze_azure_instances)
from clouds.gcp.tools import (analyze_gcp_disks, analyze_gcp_storage,
                              get_gcp_cost, get_gcp_logs, list_gcp_projects,
                              list_gke_clusters, list_sql_instances,
                              run_gcp_finops_audit)
from config import google_api_key


class AgentState(TypedDict):
    messages: list
    output: str


llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro-latest",
    temperature=0.8,
    top_p=0.9,
    max_output_tokens=4096,
    google_api_key=google_api_key,
)

tools = [
    get_aws_cost,
    run_aws_finops_audit,
    list_aws_profiles,
    analyze_rds_instances,
    analyze_ec2_rightsizing,
    analyze_s3_optimization,
    analyze_aws_network,
    analyze_aws_disks,
    analyze_cloudwatch_logs_cost,
    get_gcp_cost,
    run_gcp_finops_audit,
    list_gcp_projects,
    list_gke_clusters,
    list_sql_instances,
    get_gcp_logs,
    analyze_gcp_storage,
    analyze_gcp_disks,
    get_azure_cost,
    run_azure_finops_audit,
    analyze_azure_storage,
    analyze_azure_network,
    analyze_azure_disks,
    analyze_azure_network,
    analyze_azure_instances,
]


agent_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a Multi-Cloud FinOps assistant. You can help users:\n"
            "- Get cost breakdowns for AWS, GCP, Azure\n"
            "- Run FinOps audits for cost-saving insights\n"
            "- List Projects, Profiles, Subscriptions for AWS, GCP, Azure\n"
            "Decide which cloud's tool to invoke based on user input.",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)

agent_executor = create_react_agent(model=llm, tools=tools, prompt=agent_prompt)

workflow = StateGraph(state_schema=AgentState)
workflow.add_node("run_agent", agent_executor)
workflow.set_entry_point("run_agent")
workflow.add_edge("run_agent", END)
graph_executor = workflow.compile()


nest_asyncio.apply()

history = InMemoryHistory()


async def handle_input(user_input):
    result = await graph_executor.ainvoke(
        {"messages": [{"role": "user", "content": user_input}], "output": ""}
    )
    messages = result.get("messages", [])
    ai_responses = [msg for msg in messages if msg.type == "ai"]
    if ai_responses:
        print(ai_responses[-1].content)
    else:
        print("No response from the assistant.")


def run():
    while True:
        try:
            user_input = prompt(
                "Ask me your Multi-Cloud FinOps question (or 'exit'): ", history=history
            )
            if user_input.strip().lower() in ["exit", "quit"]:
                break
            asyncio.run(handle_input(user_input))
        except Exception as e:
            print("Error: due to this exception", e)
