from typing import List
import os
import openai
import cohere
from abc import ABC

from .message import Message

# from .utils import register_backend

openai.api_key = os.environ.get("OPENAI_API_KEY")


class IntelligenceBackend(ABC):
    """An abstraction of the intelligence source of the agents."""

    def query(self, agent_name: str, role_desc: str, env_desc: str,
              history_messages: List[Message], request_msg: Message = None,
              *args, **kwargs) -> str:
        pass

    @classmethod
    def from_config(cls, config: dict):
        pass

    def to_config(self) -> dict:
        pass


# An Error class for the human backend
class HumanBackendError(Exception):
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        super().__init__(f"Human backend requires a UI to get input from {agent_name}.")


class Human(IntelligenceBackend):

    def query(self, agent_name: str, *args, **kwargs) -> str:
        # ui = kwargs.get("ui", None)
        # if ui is None:
        #     raise ValueError("ui is not specified")
        # elif ui == "cli":
        #     user_input = input(f"[{agent_name}]: ")
        #     return user_input
        # elif ui == "gradio":
        #     return ""
        # else:
        #     raise NotImplementedError
        raise HumanBackendError(agent_name)

    @classmethod
    def from_config(cls, config: dict):
        assert config["backend_type"] == "human"
        return cls()

    def to_config(self) -> dict:
        return {"backend_type": "human"}


class RemoteAPI(IntelligenceBackend):

    def __init__(self, temperature, max_tokens):
        self.temperature = temperature
        self.max_tokens = max_tokens

    # @staticmethod
    # def get_components(config):
    #     temperature = gr.Slider(minimum=0, maximum=2.0, step=0.1, interactive=True,
    #                             label=f"temperature", value=config["temperature"])
    #     max_tokens = gr.Slider(minimum=10, maximum=500, step=10, interactive=True,
    #                            label=f"max tokens per response", value=config["max_tokens"])
    #
    #     return [temperature, max_tokens]
    #
    # @classmethod
    # def parse_components(cls, components, start_idx):
    #     temperature = components[start_idx]
    #     max_tokens = components[start_idx + 1]
    #     return cls(temperature, max_tokens)


DEFAULT_OPENAI_MODEL = "gpt-3.5-turbo"


class OpenAIChat(RemoteAPI):
    """
    Interface to the ChatGPT style model with system, user, assistant roles separation
    """
    stateful = False

    def __init__(self, temperature, max_tokens, model_name=DEFAULT_OPENAI_MODEL):
        super().__init__(temperature, max_tokens)
        self.model = model_name
        self.stop = ("<EOS>", "[EOS]", "(EOS)")  # End of sentence token

    @classmethod
    def from_config(cls, config):
        assert config["backend_type"] == "openai-chat"
        return cls(config["temperature"], config["max_tokens"], config.get("model", DEFAULT_OPENAI_MODEL))

    def to_config(self):
        return {
            "backend_type": "openai-chat",
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "model": self.model
        }

    def _get_response(self, messages, temperature=None, max_tokens=None):
        if temperature is None:
            temperature = self.temperature
        if max_tokens is None:
            max_tokens = self.max_tokens

        completion = openai.ChatCompletion.create(
            model=self.model,
            messages=messages,
            temperature=temperature, max_tokens=max_tokens, stop=self.stop)

        response = completion.choices[0]['message']['content']
        response = response.strip()
        return response

    def query(self, agent_name: str, role_desc: str, env_desc: str,
              history_messages: List[Message], request_msg: Message = None,
              *args, **kwargs) -> str:
        """
        format the input and call the ChatGPT/GPT-4 API
        args:
            agent_name: the name of the agents
            role_desc: the description of the role of the agents
            env_desc: the description of the environment
            history_messages: the history of the conversation, or the observation for the agents
            request_msg: the request for the chatGPT
        """
        conversations = []
        for i, message in enumerate(history_messages):
            if message.agent_name == agent_name:
                conversations.append({"role": "assistant", "content": message.content})
            else:
                # Since there are more than one player, we need to distinguish between the players
                conversations.append({"role": "user", "content": f"[{message.agent_name}]: {message.content}"})

        system_prompt = [
            {"role": "system", "content": env_desc},
            {"role": "system", "content": role_desc},
        ]

        if request_msg:
            request_prompt = [{"role": "system", "content": request_msg.content}]
        else:
            request_prompt = []

        # To make ChatGPT be aware of its own role, append a message with its own name
        prefix = f"[{agent_name}]:"
        # request_prompt.append({"role": "assistant", "content": prefix})

        response = self._get_response(system_prompt + conversations + request_prompt,
                                      temperature=kwargs.get("temperature", None),
                                      max_tokens=kwargs.get("max_tokens", None))

        # Remove the prefix if the response starts with it
        if response.strip().startswith(prefix):
            response = response.strip()[len(prefix):].strip()

        return response


class CohereChat(RemoteAPI):
    """
    Interface to the Cohere API
    """

    stateful = True

    def __init__(self, temperature, max_tokens):
        super().__init__(temperature, max_tokens)

        self.api_key = os.environ.get('COHEREAI_API_KEY')
        self.client = cohere.Client(self.api_key)

        # Stateful variables
        self.session_id = None  # The session id for the last conversation
        self.last_msg_hash = None  # The hash of the last message of the last conversation

    @classmethod
    def from_config(cls, config):
        assert config["backend_type"] == "cohere-chat"
        return cls(config["temperature"], config["max_tokens"])

    def to_config(self):
        return {
            "backend_type": "cohere-chat",
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    def _get_response(self, new_message: str, persona_prompt: str, temperature=None, max_tokens=None):
        if temperature is None:
            temperature = self.temperature
        if max_tokens is None:
            max_tokens = self.max_tokens

        response = self.client.chat(new_message, persona_prompt=persona_prompt,
                                    temperature=temperature, max_tokens=max_tokens,
                                    session_id=self.session_id)

        self.session_id = response.session_id  # Update the session id
        return response.reply

    def query(self, agent_name: str, role_desc: str, env_desc: str,
              history_messages: List[Message], request_msg: Message = None,
              *args, **kwargs) -> str:
        """
        format the input and call the Cohere API
        args:
            agent_name: the name of the agents
            role_desc: the description of the role of the agents
            env_desc: the description of the environment
            history_messages: the history of the conversation, or the observation for the agents
            request_msg: the request for the chatGPT
        """

        # Find the index of the last message of the last conversation
        new_message_start_idx = 0
        if self.last_msg_hash is not None:
            for i, message in enumerate(history_messages):
                if message.msg_hash == self.last_msg_hash:
                    new_message_start_idx = i + 1
                    break
        new_messages = history_messages[new_message_start_idx:]
        assert len(new_messages) > 0, "No new messages found (this should not happen)"
        self.last_msg_hash = new_messages[-1].msg_hash

        new_conversations = []
        for message in new_messages:
            if message.agent_name != agent_name:
                # Since there are more than one player, we need to distinguish between the players
                new_conversations.append(f"[{message.agent_name}]: {message.content}")

        if request_msg:
            new_conversations.append(f"[{request_msg.agent_name}]: {request_msg.content}")

        # Concatenate all new messages into one message because the Cohere API only accepts one message
        new_message = "\n".join(new_conversations)
        persona_prompt = f"Environment:\n{env_desc}\n\nRole:\n{role_desc}"

        response = self._get_response(new_message, persona_prompt,
                                      temperature=kwargs.get("temperature", None),
                                      max_tokens=kwargs.get("max_tokens", None))

        return response


BACKEND_REGISTRY = {
    "openai-chat": OpenAIChat,
    "cohere-chat": CohereChat,
    "human": Human,
}


# Load a backend from a config dictionary
def load_backend(config):
    backend_cls = BACKEND_REGISTRY[config["backend_type"]]
    backend = backend_cls.from_config(config)
    return backend
