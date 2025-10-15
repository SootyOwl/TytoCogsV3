from letta_client import AsyncLetta
import logging

log = logging.getLogger("red.tyto.aurora.utils")


async def attach_blocks(
    letta: AsyncLetta, agent_id: str, block_names: list[str]
) -> tuple[bool, set[str]]:
    """Attach blocks to the Letta client."""
    try:
        attached_labels = set()
        current_blocks = await letta.agents.blocks.list(agent_id=agent_id)
        current_block_labels = {block.label for block in current_blocks}
        current_block_ids = {block.id for block in current_blocks}

        for label in block_names:
            try:
                # Skip if already attached
                if label in current_block_labels:
                    log.debug(
                        f"Block '{label}' already attached to agent '{agent_id}'. Skipping."
                    )
                    attached_labels.add(label)
                    continue

                # Check if block exists globally
                existing_blocks = await letta.blocks.list(label=label)
                if existing_blocks and len(existing_blocks) > 0:
                    block = existing_blocks[0]
                    if block.id in current_block_ids:
                        log.debug(
                            f"Block '{label}' already attached to agent '{agent_id}'. Skipping."
                        )
                        attached_labels.add(label)
                        continue
                else:
                    # Create new block
                    block = await letta.blocks.create(label=label, value="", limit=5000)
                    log.info(f"Created new block '{label}' with ID '{block.id}'.")

                # Attach block to agent
                if not block or not block.id:
                    log.error(
                        f"Block '{label}' has no ID. Cannot attach to agent '{agent_id}'."
                    )
                    continue
                await letta.agents.blocks.attach(agent_id=agent_id, block_id=block.id)
                log.info(f"Attached block '{label}' to agent '{agent_id}'.")
                attached_labels.add(label)
            except Exception as e:
                # check for duplicate block error
                if "duplicate key value" in str(e).lower():
                    log.warning(
                        f"Block '{label}' already attached to agent '{agent_id}'. Skipping."
                    )
                    attached_labels.add(label)
                else:
                    log.error(
                        f"Error attaching block '{label}' to agent '{agent_id}': {e}"
                    )
        if attached_labels:
            log.info(
                f"Successfully attached blocks to agent '{agent_id}': {', '.join(attached_labels)}"
            )
        return True, attached_labels
    except Exception as e:
        log.error(f"Error in attach_blocks for agent '{agent_id}': {e}")
        return False, set()


async def detach_blocks(
    letta: AsyncLetta, agent_id: str, block_names: list[str]
) -> tuple[bool, set[str]]:
    """Detach blocks from the Letta client."""
    try:
        detached_labels = set()
        current_blocks = await letta.agents.blocks.list(agent_id=agent_id)
        current_block_map = {block.label: block.id for block in current_blocks}

        for label in block_names:
            try:
                if label not in current_block_map:
                    log.debug(
                        f"Block '{label}' not attached to agent '{agent_id}'. Skipping."
                    )
                    continue
                block_id = current_block_map[label]
                await letta.agents.blocks.detach(agent_id=agent_id, block_id=block_id)
                log.info(f"Detached block '{label}' from agent '{agent_id}'.")
                detached_labels.add(label)
            except Exception as e:
                log.error(
                    f"Error detaching block '{label}' from agent '{agent_id}': {e}"
                )
        if detached_labels:
            log.info(
                f"Successfully detached blocks from agent '{agent_id}': {', '.join(detached_labels)}"
            )
        return True, detached_labels
    except Exception as e:
        log.error(f"Error in detach_blocks for agent '{agent_id}': {e}")
        return False, set()
