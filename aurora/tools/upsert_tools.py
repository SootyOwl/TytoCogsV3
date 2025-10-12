"""Python script to upsert all tools in the ./tools/ directory to the Letta server."""

import logging
import os
import dotenv
from letta_client import Letta

import tools
tools.load_tools()


logger = logging.getLogger('upsert_tools')
logger.setLevel(logging.INFO)

if __name__ == "__main__":
    dotenv.load_dotenv()

    base_url = os.getenv("LETTA_BASE_URL")
    if not base_url:
        raise ValueError("LETTA_BASE_URL environment variable is not set.")
    token = os.getenv("LETTA_TOKEN")
    if not token:
        raise ValueError("LETTA_TOKEN environment variable is not set.")
    
    client = Letta(base_url=base_url, token=token)
    client.tools.list()  # Test connection
    logger.info("Connected to Letta server.")

    for tool_name, tool_function in tools.ALL_TOOLS.items():
        try:
            tool = client.tools.upsert_from_function(func=tool_function)
            logger.info(f"Upserted tool '{tool_name}' with ID: {tool.id}")
        except Exception as e:
            logger.error(f"Failed to upsert tool '{tool_name}': {e}")
    