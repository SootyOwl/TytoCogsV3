import json
import logging
import os
from typing import List, Optional, Dict

from pydantic import Field, BaseModel

log = logging.getLogger("red.tytocogsv3.gpt3chatbot.personalities")
log.setLevel(os.getenv("TYTOCOGS_LOG_LEVEL", "INFO"))


class OpenAIConfig(BaseModel):
    max_tokens: int = 200
    temperature: float = 0.9
    top_p: float = 1
    best_of: int = 1
    presence_penalty: float = Field(0.1, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(0.1, ge=-2.0, le=2.0)

    class Config:
        validate_assignment = True


class QnAResponse(BaseModel):
    input: str
    reply: str


class Persona(BaseModel):
    name: str
    description: str
    initial_chat_log: List[QnAResponse]
    meta_comments: List[str] = Field(default_factory=list)

    openai: OpenAIConfig = OpenAIConfig()


def load_from_file(json_fp: str) -> List[Persona]:
    """Loads personalities from json."""
    with open(json_fp, "r") as f_in:
        personas_list = json.load(f_in)
    if isinstance(personas_list, dict):
        # super hacky
        personas_list = [personas_list]
    # convert to dataclasses and return
    return [Persona(**p) for p in personas_list]


def config_to_personas(persona_config: List[Dict]) -> List[Persona]:
    # log.info(persona_config)
    return [Persona(**p) for p in persona_config]


def personas_to_config(personas_list: List[Persona]) -> List[Dict]:
    # log.info(personas_list)
    return [p.dict() for p in personas_list]


if __name__ == "__main__":
    personas = load_from_file("./data/message.json")
    dictrep = personas_to_config(personas)
    print(type(dictrep), type(dictrep[0]))
    perrep = config_to_personas(dictrep)
    print(type(perrep), type(perrep[0]))
    print(json.loads(json.dumps(dictrep)))
