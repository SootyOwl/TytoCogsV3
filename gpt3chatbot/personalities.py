import json
import pickle
from typing import List, Optional

from pydantic import Field, BaseModel


class OpenAIConfig(BaseModel):
    max_tokens: int = 200
    temperature: float = 0.9
    top_p: float = 1
    best_of: float = 1
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

    openai: Optional[OpenAIConfig] = OpenAIConfig()


def load_from_file(json_fp: str) -> List[Persona]:
    """Loads personalities from json."""
    with open(json_fp, "r") as f_in:
        personas_list = json.load(f_in)
    if isinstance(personas_list, dict):
        # super hacky
        personas_list = [personas_list]
    # convert to dataclasses and return
    return [Persona(**p) for p in personas_list]


if __name__ == "__main__":
    personas = load_from_file("./data/message.json")
    print([p.dict() for p in personas])
    pickle.loads(pickle.dumps(personas[0]))
    json.loads(json.dumps(personas[0]))
