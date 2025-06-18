from mcp.server.fastmcp import run

# app = FastAPI()
#
# @app.get("/cost")
# def cost(account_id: str, start_date: str, end_date: str):
#     return get_cost(account_id, start_date, end_date)
#
# @app.get("/audit")
# def audit(account_id: str, regions: str):
#     region_list = regions.split(",")
#     return run_finops_audit(account_id, region_list)


if __name__ == "__main__":
    run()
