"""Aurora Initialization module."""

from datetime import datetime
import json
import logging
import os
import subprocess
from typing import List

from letta_client import AgentState, AsyncLetta
from letta_client.types.block import Block
from yaml import safe_load

logger = logging.getLogger("red.tyto.aurora.initialize")


def ignore() -> None:
    """
    Not every message warrants a reply (especially if the message isn't directed at you). Call this tool to ignore the message.

    This function does not perform any action.

    Returns:
        None
    """
    return


async def upsert_memory_block(client: AsyncLetta, label: str, value: str, **kwargs):
    """Ensure that a black by this label exists. If the block exists, it will replace content provided
    by kwargs with the values in this function call.

    (Inspired by https://tangled.sh/@cameron.pfiffer.org/void/blob/main/utils.py)

    Args:
        client (AsyncLetta): The Letta client instance.
        label (str): Label for the memory block.
        value (str): Content of the memory block.
    """
    blocks: List[Block] = await client.blocks.list(label=label)

    if len(blocks) == 0:
        # Create a new block if it doesn't exist
        return await client.blocks.create(label=label, value=value, **kwargs)

    elif len(blocks) > 1:
        raise Exception(
            f"{len(blocks)} blocks found with label '{label}'. Please ensure labels are unique."
        )

    # Update the existing block with new content
    block = blocks[0]
    if kwargs.get("update", False) and block.id:
        kwargs_copy = kwargs.copy()
        kwargs_copy.pop("update")
        return await client.blocks.modify(
            block.id, label=label, value=value, **kwargs_copy
        )
    else:
        return block


async def upsert_agent(client: AsyncLetta, name: str, **kwargs) -> AgentState:
    """Ensure that an agent by this name exists. If the agent exists, it will replace content provided
    by kwargs with the values in this function call.

    (Inspired by https://tangled.sh/@cameron.pfiffer.org/void/blob/main/utils.py)

    Args:
        client (AsyncLetta): The Letta client instance.
        name (str): Name of the agent.
    """
    agents = await client.agents.list(name=name)

    if len(agents) == 0:
        # Create a new agent if it doesn't exist
        return await client.agents.create(name=name, **kwargs)

    elif len(agents) > 1:
        raise Exception(
            f"{len(agents)} agents found with name '{name}'. Please ensure names are unique."
        )

    # Update the existing agent with new content
    agent = agents[0]
    if kwargs.get("update", False) and agent.id:
        kwargs_copy = kwargs.copy()
        kwargs_copy.pop("update")
        return await client.agents.modify(agent.id, name=name, **kwargs_copy)
    else:
        # If not updating, just return the existing agent
        return agent


async def load_config_from_yaml(file_path: str) -> dict:
    """Load configuration from a YAML file.

    Args:
        file_path (str): Path to the YAML file.

    Returns:
        dict: Configuration data loaded from the YAML file.
    """
    with open(file_path, "r") as file:
        config = safe_load(file)
    return config


def export_agent_state(client, agent, skip_git=False):
    """Export agent state to agent_archive/ (timestamped) and agents/ (current)."""
    try:
        # Confirm export with user unless git is being skipped
        if not skip_git:
            response = (
                input("Export agent state to files and stage with git? (y/n): ")
                .lower()
                .strip()
            )
            if response not in ["y", "yes"]:
                logger.info("Agent export cancelled by user.")
                return
        else:
            logger.info("Exporting agent state (git staging disabled)")

        # Create directories if they don't exist
        os.makedirs("agent_archive", exist_ok=True)
        os.makedirs("agents", exist_ok=True)

        # Export agent data
        logger.info(f"Exporting agent {agent.id}. This takes some time...")
        agent_data = client.agents.export_file(agent_id=agent.id)

        # Save timestamped archive copy
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = os.path.join("agent_archive", f"void_{timestamp}.af")
        with open(archive_file, "w", encoding="utf-8") as f:
            json.dump(agent_data, f, indent=2, ensure_ascii=False)

        # Save current agent state
        current_file = os.path.join("agents", "void.af")
        with open(current_file, "w", encoding="utf-8") as f:
            json.dump(agent_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Agent exported to {archive_file} and {current_file}")

        # Git add only the current agent file (archive is ignored) unless skip_git is True
        if not skip_git:
            try:
                subprocess.run(
                    ["git", "add", current_file], check=True, capture_output=True
                )
                logger.info("Added current agent file to git staging")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to git add agent file: {e}")

    except Exception as e:
        logger.error(f"Failed to export agent: {e}")


async def create_letta_agent_instance(
    client: AsyncLetta,
    base_url: str,
    token: str,
    web_search: bool,
    run_code: bool,
    project: str = "AuroraDiscord",
):
    """Initialize the aurora agent."""
    logger.info("Starting aurora agent initialisation...")

    # load the default config from config.yml
    config = await load_config_from_yaml("config.yml")
    logger.info("Loaded configuration from config.yml")
    logger.debug(f"Configuration: {config}")

    # Create or update the memory blocks
    logger.info("Creating/updating memory blocks...")
    blocks = []
    for block in config.get("agent", {}).get("blocks", []):
        logger.info(f"Creating/updating memory block: {block['label']}...")
        block = await upsert_memory_block(
            client,
            **block,
        )
        blocks.append(block)
        logger.info(f"Memory block '{block.label}' created/updated successfully.")
    logger.info("All memory blocks created/updated successfully.")

    # Create or update the agent
    logger.info("Creating/updating agent...")
    agent: AgentState = await upsert_agent(
        client,
        name=config.get("agent", {}).get("name", "Aurora"),
        blocks=[block.id for block in blocks],
        tags=config.get("agent", {}).get("tags", []),
        description=config.get("agent", {}).get(
            "description", "An autonomous Discord agent powered by Letta."
        ),
        base_url=base_url,
        token=token,
        web_search=web_search,
        run_code=run_code,
        project=project,
    )
    logger.info(f"Agent '{agent.name}' created/updated successfully.")

    # export agent state
    logger.info("Exporting agent state...")
    export_agent_state(client, agent, skip_git=config.get("skip_git", False))

    logger.info(f"Aurora agent initialisation complete - ID: {agent.id}")
    logger.info(f"Agent name: {agent.name}")
    if hasattr(agent, "llm_config"):
        logger.info(f"LLM: {agent.llm_config.model}")
    if hasattr(agent, "tools"):
        logger.info(f"Agent has {len(agent.tools)} tools configured.")
        for tool in agent.tools:
            logger.info(f" - Tool: {tool.name} ({tool.tool_type})")
    return agent


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load configuration from config.yml
    config = asyncio.run(load_config_from_yaml("config.yml"))

    # Initialize the Letta client
    base_url = config.get("letta", {}).get("base_url", "https://localhost:8283")
    token = config.get("letta", {}).get("token", "")
    if not token:
        raise ValueError("Letta API token is required in config.yml")

    client = AsyncLetta(base_url=base_url, token=token)

    # Create or update the aurora agent
    agent = asyncio.run(
        create_letta_agent_instance(
            client,
            base_url=base_url,
            token=token,
            web_search=config.get("agent", {}).get("web_search", False),
            run_code=config.get("agent", {}).get("run_code", False),
            project="AuroraDiscord",
        )
    )
