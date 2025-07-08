import asyncio
from typing import TypedDict

import nest_asyncio
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent
from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory
from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from clouds.aws.tools import (analyze_aws_disks, analyze_aws_eks_clusters,
                              analyze_aws_network, analyze_aws_snapshots,
                              analyze_aws_static_ips,
                              analyze_cloudwatch_logs_cost,
                              analyze_ec2_rightsizing, analyze_rds_instances,
                              analyze_s3_optimization)
from clouds.aws.tools import get_cost as get_aws_cost
from clouds.aws.tools import list_aws_profiles
from clouds.aws.tools import run_finops_audit as run_aws_finops_audit
from clouds.azure.tools import (analyze_azure_aks_clusters,
                                analyze_azure_disks, analyze_azure_instances,
                                analyze_azure_network, analyze_azure_snapshots,
                                analyze_azure_static_ips,
                                analyze_azure_storage, get_azure_cost,
                                run_azure_finops_audit)
from clouds.gcp.tools import (analyze_gcp_bigquery, analyze_gcp_disks,
                              analyze_gcp_gke_clusters, analyze_gcp_snapshots,
                              analyze_gcp_static_ips, analyze_gcp_storage,
                              get_gcp_cost, get_gcp_logs, list_gcp_projects,
                              list_gke_clusters, list_sql_instances,
                              run_gcp_finops_audit)
from config import GOOGLE_API_KEY

console = Console()


class AgentState(TypedDict):
    messages: list
    output: str
    last_cloud: str


# Shared chat state across prompts
chat_state = {
    "messages": [],
    "output": "",
    "last_cloud": "",
}

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro-latest",
    temperature=0.8,
    top_p=0.9,
    max_output_tokens=4096,
    google_api_key=GOOGLE_API_KEY,
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
    analyze_aws_snapshots,
    analyze_aws_static_ips,
    analyze_aws_eks_clusters,
    get_gcp_cost,
    run_gcp_finops_audit,
    list_gcp_projects,
    list_gke_clusters,
    list_sql_instances,
    get_gcp_logs,
    analyze_gcp_storage,
    analyze_gcp_disks,
    analyze_gcp_static_ips,
    analyze_gcp_snapshots,
    analyze_gcp_gke_clusters,
    get_azure_cost,
    run_azure_finops_audit,
    analyze_azure_storage,
    analyze_azure_network,
    analyze_azure_disks,
    analyze_azure_instances,
    analyze_azure_snapshots,
    analyze_azure_static_ips,
    analyze_azure_aks_clusters,
    analyze_gcp_bigquery,
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


def extract_cloud_hint(user_input: str) -> str:
    user_input = user_input.lower()
    if "aws" in user_input or "profile" in user_input:
        return "aws"
    elif "gcp" in user_input or "project" in user_input:
        return "gcp"
    elif "azure" in user_input or "subscription" in user_input:
        return "azure"
    return ""




def render_pretty_output(content: str):
    if content.startswith("Total Cost:") or "Cost By Service" in content:
        console.print(
            Panel(
                Markdown(content),
                title="[bold green]Cost Breakdown[/bold green]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                Markdown(content),
                title="[bold cyan]Finops-MCP Assistant[/bold cyan]",
                border_style="cyan",
            )
        )


async def handle_input(user_input):
    global chat_state

    cloud = extract_cloud_hint(user_input) or chat_state["last_cloud"]
    if cloud:
        chat_state["last_cloud"] = cloud
        cloud_hint = {
            "role": "system",
            "content": f"The user is working with the {cloud.upper()} cloud platform.",
        }
    else:
        cloud_hint = {}

    user_msg = {"role": "user", "content": user_input}
    chat_state["messages"].append(user_msg)
    if cloud_hint:
        chat_state["messages"].append(cloud_hint)

    result = await graph_executor.ainvoke(chat_state)
    messages = result.get("messages", [])
    ai_responses = [msg for msg in messages if msg.type == "ai"]

    if ai_responses:
        content = ai_responses[-1].content.strip()
        chat_state["messages"].append({"role": "ai", "content": content})
        render_pretty_output(content)
    else:
        console.print(
            Panel(
                Text("No response from the assistant.", justify="left"),
                title="[red]Finops-MCP Assistant[/red]",
            )
        )


def run():
    console.print(
        Panel(
            "💬 [bold green]Multi-Cloud FinOps CLI Assistant[/bold green]\n(Type 'exit' to quit)",
            border_style="green",
        )
    )
    examples = [
        "[cyan]•[/cyan] What is my AWS cost breakdown for the last 7 days profile prfofile_name",
        "[cyan]•[/cyan] Run a GCP FinOps audit for project project_id for billing account name_of_dataset",
        "[cyan]•[/cyan] Quick Network analysis for Azure subscription subscription_id",
        "[cyan]•[/cyan] Show underutilized EC2 instances in us-west-1.",
        "[cyan]•[/cyan] Find idle disks in GCP for project project_id",
        "[cyan]•[/cyan] Analyze my S3 buckets for optimization.",
    ]

    table = Table.grid(padding=1)
    table.add_column(justify="left")
    for example in examples:
        table.add_row(Text.from_markup(example))

    console.print(
        Panel(
            Align.left(table),
            title="[bold magenta]Example Prompts[/bold magenta]",
            border_style="magenta",
        )
    )

    while True:
        try:
            user_input = prompt(
                "Ask me your Multi-Cloud FinOps question (or 'exit'): ", history=history
            )
            if user_input.strip().lower() in ["exit", "quit"]:
                break
            asyncio.run(handle_input(user_input))
        except Exception as e:
            console.print(
                Panel(
                    Text(f"Error: {e}", justify="left"),
                    title="[bold red]Finops-MCP Assistant[/bold red]",
                    border_style="red",
                )
            )


if __name__ == "__main__":
    run()
