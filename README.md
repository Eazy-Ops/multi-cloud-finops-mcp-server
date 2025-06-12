🌐 **FastMCP - Multi-Cloud FinOps Copilot**

An MCP (Model Context Protocol) server that connects Gemini-powered assistants with FinOps insights across AWS, GCP, and Azure. Perform natural language-based cost breakdowns, audits, and usage summaries — all locally and securely.

---

## 📌 Why Use FastMCP?

Managing multi-cloud costs is complex. FastMCP allows you to:

* Ask AI "How much did we spend on Azure last month?"
* Run a cost-saving audit across AWS and GCP in one prompt
* Receive budget summaries from all major cloud providers

Powered by **LangChain**, **LangGraph**, and **Gemini Pro**, this tool makes FinOps conversational and cross-platform.

---

## 🚀 Features

* 🌍 Supports AWS, GCP, Azure
* 🧠 Natural language queries via Gemini Pro
* 🧰 Cost breakdowns, FinOps audits, budget status
* ⚙️ CLI or FastAPI-compatible architecture
* 🛡️ Credentials never leave your machine (uses local SDK/CLI auth)

---

## 🧱 Installation

### 1. Prerequisites

* Python 3.11+
* poetry
* CLI tools:

  * aws CLI (for AWS)
  * gcloud CLI (for GCP)
  * az CLI (for Azure)

### 2. Clone & Setup

```bash
git clone https://github.com/Eazy-Ops/multi-cloud-finops-mcp-server.git
cd multi-cloud-finops-mcp-server

# Install dependencies
poetry install
```

---

## 🔐 Authentication Setup

### 🔹 AWS

```bash
aws configure --profile your-profile
```

You'll be prompted for:

* Access Key ID
* Secret Access Key
* Region
* Output format (e.g. json)

### 🔹 GCP

**Option 1: Use Application Default Credentials (ADC)**

```bash
gcloud auth application-default login
```

**Option 2: Use Service Account JSON**

Pass the file path to `service_account_key_path` when calling GCP functions.

### 🔹 Azure

```bash
az login
```

**For service principal auth (optional):**

```bash
export AZURE_TENANT_ID=your-tenant-id
export AZURE_CLIENT_ID=your-client-id
export AZURE_CLIENT_SECRET=your-client-secret
```

---

## 🧪 Usage

### CLI Entry Point

```bash
poetry run python -m mcp.server.fastmcp
```

Then ask questions in Claude Desktop, Amazon Q, or any MCP-compatible client:

* "Run a FinOps audit for AWS us-east-1 profile"
* "Get last 30 days GCP cost breakdown for my service account"
* "How many stopped Azure VMs in west-europe?"

---

## 💬 Example Prompts

### 📊 Audit Azure for idle VMs and unattached disks

```json
{
  "audit": {
    "stopped_vms": [
      {"name": "vm-dev-1", "region": "eastus", "status": "Stopped"}
    ],
    "unattached_disks": [
      {"id": "disk-abc", "size_gb": 100}
    ]
  }
}
```

### 💸 Get AWS cost grouped by service for last 15 days

```json
{
  "total_cost": 124.50,
  "grouped_by_service": {
    "Amazon EC2": 78.23,
    "Amazon S3": 32.91,
    "CloudWatch": 13.36
  }
}
```

### ☁️ Break down GCP spend in last 7 days

```json
{
  "project_id": "my-gcp-project",
  "cost_breakdown": {
    "Compute Engine": 41.50,
    "BigQuery": 88.75
  }
}
```

---

