from .environment import Environment, Conversation, TimeStep
from chat_arena.message import Message, MessagePool
from typing import List, Dict, Union
import random

DEFAULT_TOPIC_CODES = {
    "Fruits": [
        "Apple",
        "Banana",
        "Orange",
        "Grape",
        "Strawberry",
        "Pineapple",
        "Mango",
        "Watermelon",
    ],
    "Animals": [
        "Lion",
        "Elephant",
        "Giraffe",
        "Monkey",
        "Zebra",
        "Tiger",
        "Bear",
        "Kangaroo",
    ],
    "Sports": [
        "Soccer",
        "Basketball",
        "Tennis",
        "Baseball",
        "Swimming",
        "Cycling",
        "Volleyball",
        "Golf",
    ],
    "Countries": [
        "United States",
        "Canada",
        "Brazil",
        "United Kingdom",
        "France",
        "Germany",
        "Japan",
        "Australia",
    ],
}

class Chameleon(Environment):
    def __init__(self, player_names: List[str], env_desc: str,
                 topic_codes: Dict[str,List[str]]=DEFAULT_TOPIC_CODES):
        super().__init__(player_names, env_desc)
        self.topic = None
        self.code = None
        self.message_pool = MessagePool()
        self.topic_codes_dict = topic_codes
        self.chameleon_name = None
        self.non_chameleon_names = None

        self._current_turn = None
        self._next_player_idx = None
        self._current_phase = None # "give clues", "accuse", "guess"

        self.reset()

    @classmethod
    def from_config(cls, config: dict):
        assert config["env_type"] == "chameleon"
        return cls(
            player_names=config["player_names"],
            env_desc=config["env_desc"],
        )

    def get_next_player(self) -> str:
        """
        get the next player
        """
        if self._current_phase != "guess":
            return self.player_names[self._next_player_idx]
        else:
            return self.chameleon_name

    def print(self):
        self.message_pool.print()

    def reset(self):
        """
        sample topic, code and chemeleon code
        """
        self.topic = random.choice(list(self.topic_codes_dict.keys()))
        self.code = random.choice(self.topic_codes_dict[self.topic])
        self.chameleon_name = random.choice(self.player_names)
        self.non_chameleon_names = [name for name in self.player_names if name != self.chameleon_name]

        self._current_turn = 0
        self._next_player_idx = 0
        self._current_phase = "give clues"
        self.message_pool.reset()
        self.moderator_say(f"The game started! Topic: {self.topic}")
        self.moderator_say(f"You are not chameleon. The code is: {self.code}", visible_to=self.non_chameleon_names)
        self.moderator_say(f"You are the chameleon!", visible_to=self.chameleon_name)
        self.moderator_say(f"Now everyone can start giving clues. One can say anything you want but only say once."
                           f"Starting from {self.get_next_player()}.")
        self._current_turn = 1
        return self.get_observation()

    def get_observation(self, player_name=None) -> List[Message]:
        """
        get observation for the player
        """
        if player_name is None:
            return self.message_pool.get_all_messages()
        else:
            return self.message_pool.get_visible_messages(player_name, turn=self._current_turn)

    def text2vote(self, text) -> str:
        """
        convert text to vote, return a player's name
        """
        lower = text.lower().replace("[", "").replace("]", "").replace(".", "")
        for name in self.player_names:
            candidates = [name.lower(), name.lower().replace(" ", ""),
                          name.lower().replace(" ", "_")]
            if lower in candidates:
                return name
        return ""

    def is_true_code(self, text) -> bool:
        """
        weather the text is the true code
        """
        lower = text.lower().replace(" ", "").replace(".", "")
        return lower == self.code.lower().replace(" ", "")

    def moderator_say(self, text:str, visible_to:Union[str, List[str]]="all"):
        """
        moderator say something
        """
        message = Message(agent_name="Moderator",
                          content=text,
                          turn=self._current_turn,
                          visible_to=visible_to)
        self.message_pool.append_message(message)

    def get_rewards(self, chameleon_win: bool) -> List[float]:
        """
        get rewards for each player
        """
        rewards = []
        for name in self.player_names:
            if name == self.chameleon_name:
                if chameleon_win:
                    rewards.append(1)
                else:
                    rewards.append(0)
            else:
                if chameleon_win:
                    rewards.append(0)
                else:
                    rewards.append(1)
        return rewards

    def step(self, player_name: str, action: str) -> TimeStep:
        """
        step function that is called by the arena
        Args:
            player_name: the name of the player that takes the action
            action: the action that the agents wants to take
        """
        self.message_pool.print()
        assert player_name == self.get_next_player(), f"Wrong player! It is {self.get_next_player()} turn."
        if self._current_phase == "give clues":
            message = Message(agent_name=player_name, content=action, turn=self._current_turn)
            self.message_pool.append_message(message)

            # Update the counters
            self._current_turn += 1
            if self._next_player_idx < len(self.player_names) - 1:
                self._next_player_idx += 1
            else:
                self._next_player_idx = 0
                self._current_phase = "accuse"
                self.moderator_say(f"Now vote for the chameleon. You should only output the name of the chameleon.")
                self._current_turn += 1

            timestep = TimeStep(observation=self.get_observation(),
                                reward=self.get_zero_rewards(),
                                terminal=False)  # Return all the messages
        elif self._current_phase == "accuse":
            players_votes = {name: 0 for name in self.player_names}
            message = Message(agent_name=player_name, content=action, turn=self._current_turn,
                              visible_to=[player_name])
            self.message_pool.append_message(message)
            vote = self.text2vote(action)
            if vote in self.player_names:
                players_votes[vote] += 1

            if self._next_player_idx < len(self.player_names) - 1:
                self._next_player_idx += 1
                rewards = self.get_zero_rewards()
                terminal = False
            else:
                accuse_correct = True
                max_vote_player = max(players_votes, key=players_votes.get)
                # detach if other players has the same number of votes
                for name, vote in players_votes.items():
                    if name != max_vote_player and vote == players_votes[max_vote_player]:
                        accuse_correct = False
                if max_vote_player != self.chameleon_name:
                    accuse_correct = False

                if not accuse_correct:
                    self.moderator_say(f"The accusation is wrong! {self.chameleon_name} is the chameleon!")
                    rewards = self.get_rewards(chameleon_win=True)
                    terminal = True
                else:
                    self.moderator_say(f"The accusation is correct! {self.chameleon_name} is the chameleon!"
                                       f"Now {self.chameleon_name} can start guessing the secret code.")
                    self._current_phase = "guess"
                    rewards = self.get_zero_rewards()
                    terminal = False
            timestep = TimeStep(observation=self.get_observation(),
                                reward=rewards,
                                terminal=terminal)
        elif self._current_phase == "guess":
            message = Message(agent_name=player_name, content=action, turn=self._current_turn,
                              visible_to=[player_name])
            self.message_pool.append_message(message)
            if self.is_true_code(action):
                self.moderator_say(f"{player_name} guessed the code! {self.code} is the code!")
                rewards = self.get_rewards(chameleon_win=True)
            else:
                self.moderator_say(f"{player_name} guessed the code wrong! {self.code} is the code!")
                rewards = self.get_rewards(chameleon_win=False)
            timestep = TimeStep(observation=self.get_observation(),
                                reward=rewards,
                                terminal=True)
        else:
            raise ValueError(f"Unknown phase: {self._current_phase}")
        return timestep


