import enum


class VoteType(str, enum.Enum):
    UP = "за"
    DOWN = "против"
    ABSTAIN = "воздержаться"
