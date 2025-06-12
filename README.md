# 🌐 FastMCP - Multi-Cloud FinOps Copilot


An MCP (Model Context Protocol) server that connects Gemini-powered assistants with FinOps insights across **AWS**, **GCP**, and **Azure**. Perform natural language-based cost breakdowns, audits, and usage summaries — all locally and securely.

---

## 📌 Why Use FastMCP?

Managing multi-cloud costs is complex. FastMCP allows you to:

- Ask AI "How much did we spend on Azure last month?"
- Run a cost-saving audit across AWS and GCP in one prompt
- Receive budget summaries from all major cloud providers

Powered by LangChain, LangGraph, and Gemini Pro, this tool makes **FinOps conversational** and **cross-platform**.

---

## 🚀 Features

- 🌍 Supports AWS, GCP, Azure
- 🧠 Natural language queries via Gemini Pro
- 🧰 Cost breakdowns, FinOps audits, budget status
- ⚙️ CLI or FastAPI-compatible architecture
- 🛡️ Credentials never leave your machine (uses local SDK/CLI auth)

---

## 🧱 Installation

### 1. Prerequisites

- Python 3.11+
- `poetry` for dependency management
- CLI tools:
  - `aws` CLI (for AWS)
  - `gcloud` CLI (for GCP)
  - `az` CLI (for Azure)

### 2. Clone & Setup

```bash
git clone https://github.com/your-org/fastmcp.git
cd fastmcp

# Install Poetry dependencies
poetry install