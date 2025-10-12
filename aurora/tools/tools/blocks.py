from letta_client import AgentState
from . import register_tool


@register_tool
def detach_user_blocks(user_ids: list, agent_state: "AgentState") -> str:
    """
    Detach user-specific memory blocks from the agent. Blocks are preserved for later use.

    Args:
        user_ids: List of user Discord user IDs (e.g., ['123456789012345678', '987654321098765432'])
        agent_state: The agent state object containing agent information

    Returns:
        String with detachment results for each ID
    """

    try:
        # Try to get client the local way first, fall back to inline for self-hosted
        try:
            client = get_letta_client()
        except (ImportError, NameError):
            # Create Letta client inline for self-hosted execution
            import os
            from letta_client import Letta

            client = Letta(
                base_url=os.getenv("LETTA_BASE_URL", "https://api.letta.ai"),
                token=os.getenv("LETTA_API_TOKEN"),
            )
        results = []

        # Build mapping of block labels to IDs using the API
        current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
        block_label_to_id = {}

        for block in current_blocks:
            block_label_to_id[block.label] = str(block.id)

        # Process each ID and detach atomically
        for user_id in user_ids:
            block_label = f"user_{user_id}"

            if block_label in block_label_to_id:
                try:
                    # Detach block atomically
                    client.agents.blocks.detach(
                        agent_id=str(agent_state.id),
                        block_id=block_label_to_id[block_label],
                    )
                    results.append(f"✓ {user_id}: Detached")
                except Exception as e:
                    results.append(f"✗ {user_id}: Error during detachment - {str(e)}")
            else:
                results.append(f"✗ {user_id}: Not attached")

        return "Detachment results:\n" + "\n".join(results)

    except Exception as e:
        raise Exception(f"Error detaching user blocks: {str(e)}")


@register_tool
def attach_user_blocks(user_ids: list, agent_state: "AgentState") -> str:
    """
    Attach user-specific memory blocks to the agent. Creates blocks if they don't exist.

    Args:
        user_ids: List of user Discord IDs (e.g., ['123456789012345678', '987654321098765432'])
        agent_state: The agent state object containing agent information

    Returns:
        String with attachment results for each ID
    """

    user_ids = list(set(user_ids))

    try:
        # Try to get client the local way first, fall back to inline for self-hosted
        try:
            client = get_letta_client()
        except (ImportError, NameError):
            # Create Letta client inline for self-hosted execution
            import os
            from letta_client import Letta

            client = Letta(
                base_url=os.getenv("LETTA_BASE_URL", "https://api.letta.ai"),
                token=os.getenv("LETTA_API_TOKEN"),
            )
        results = []

        # Get current blocks using the API
        current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
        current_block_labels = set()
        current_block_ids = set()

        for block in current_blocks:
            current_block_labels.add(block.label)
            current_block_ids.add(str(block.id))

        for user_id in user_ids:
            block_label = f"user_{user_id}"

            # Skip if already attached
            if block_label in current_block_labels:
                results.append(f"✓ {user_id}: Already attached")
                continue

            # Check if block exists or create new one
            try:
                blocks = client.blocks.list(label=block_label)
                if blocks and len(blocks) > 0:
                    block = blocks[0]

                    # Double-check if this block is already attached by ID
                    if str(block.id) in current_block_ids:
                        results.append(f"✓ {user_id}: Already attached (by block ID)")
                        continue
                else:
                    block = client.blocks.create(
                        label=block_label,
                        value=f"# User: {user_id}\n\nNo information about this user yet.",
                        limit=5000,
                    )

                # Attach block atomically
                try:
                    client.agents.blocks.attach(
                        agent_id=str(agent_state.id), block_id=str(block.id)
                    )
                    results.append(f"✓ {user_id}: Block attached")
                except Exception as attach_error:
                    # Check if it's a duplicate constraint error
                    error_str = str(attach_error)
                    if (
                        "duplicate key value violates unique constraint" in error_str
                        and "unique_label_per_agent" in error_str
                    ):
                        # Block is already attached, possibly with this exact label
                        results.append(f"✓ {user_id}: Already attached (verified)")
                    else:
                        # Re-raise other errors
                        raise attach_error

            except Exception as e:
                results.append(f"✗ {user_id}: Error - {str(e)}")

        return f"Attachment results:\n" + "\n".join(results)

    except Exception as e:
        raise Exception(f"Error attaching user blocks: {str(e)}")
