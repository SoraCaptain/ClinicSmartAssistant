"""Shared fakes: scripted chains patched at their consumer modules (LedgerMind lesson —
patching the underlying LLM factory leaves stale chains)."""

import pytest
from langchain_core.messages import AIMessage

from app.agent.nodes.classifier import ClassifierOutput


class FakeClassifierChain:
    def __init__(self, intent: str):
        self.intent = intent
        self.prompts: list[str] = []

    def invoke(self, prompt: str, config=None) -> ClassifierOutput:
        self.prompts.append(prompt)
        return ClassifierOutput(intent=self.intent)


class FakeGeneralChain:
    def __init__(self, reply: str):
        self.reply = reply

    def invoke(self, prompt: str, config=None) -> AIMessage:
        return AIMessage(content=self.reply)


@pytest.fixture()
def fake_chains(monkeypatch):
    """install(intent, general_reply=...) → patches classifier + general chains,
    returns the installed fakes (classifier records every prompt it sees)."""

    def install(intent: str, general_reply: str = "General reply."):
        classifier = FakeClassifierChain(intent)
        general = FakeGeneralChain(general_reply)
        monkeypatch.setattr(
            "app.agent.nodes.classifier.get_classifier_chain", lambda: classifier
        )
        monkeypatch.setattr("app.agent.nodes.general.get_general_chain", lambda: general)
        return {"classifier": classifier, "general": general}

    return install
