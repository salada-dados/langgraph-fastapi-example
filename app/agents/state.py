from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Graph state: the conversation messages.

    `MessagesState` already gives us a `messages` list with an append reducer.
    Add your own fields here as the agent grows.
    """
