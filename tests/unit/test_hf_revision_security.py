import types

from largestack._guard.nli_hallucination import NLIHallucinationGuard
from largestack._guard.prompt_guard import PromptGuard2


def test_nli_guard_does_not_load_model_by_default(monkeypatch):
    monkeypatch.delenv("LARGESTACK_ENABLE_NLI_GUARD", raising=False)
    guard = NLIHallucinationGuard()
    assert guard._nli_model is None
    assert guard._nli_tokenizer is None


def test_prompt_guard_does_not_load_model_by_default(monkeypatch):
    monkeypatch.delenv("LARGESTACK_ENABLE_PROMPT_GUARD_ML", raising=False)
    guard = PromptGuard2()
    assert guard._model is None
    assert guard._tokenizer is None


def test_nli_guard_passes_revision_to_hf(monkeypatch):
    calls = []

    class FakeTokenizer:
        @staticmethod
        def from_pretrained(model_name, revision=None):
            calls.append(("tokenizer", model_name, revision))
            return object()

    class FakeModel:
        @staticmethod
        def from_pretrained(model_name, revision=None):
            calls.append(("model", model_name, revision))

            class M:
                def eval(self):
                    return None

            return M()

    fake_transformers = types.SimpleNamespace(
        AutoTokenizer=FakeTokenizer,
        AutoModelForSequenceClassification=FakeModel,
    )

    monkeypatch.setitem(__import__("sys").modules, "transformers", fake_transformers)
    monkeypatch.setitem(__import__("sys").modules, "torch", types.SimpleNamespace())
    monkeypatch.setenv("LARGESTACK_ENABLE_NLI_GUARD", "1")

    NLIHallucinationGuard(revision="test-revision")

    assert ("tokenizer", "microsoft/deberta-v3-large-mnli", "test-revision") in calls
    assert ("model", "microsoft/deberta-v3-large-mnli", "test-revision") in calls


def test_prompt_guard_passes_revision_to_hf(monkeypatch):
    calls = []

    class FakeTokenizer:
        @staticmethod
        def from_pretrained(model_name, revision=None):
            calls.append(("tokenizer", model_name, revision))
            return object()

    class FakeModel:
        @staticmethod
        def from_pretrained(model_name, revision=None):
            calls.append(("model", model_name, revision))

            class M:
                def eval(self):
                    return None

            return M()

    fake_transformers = types.SimpleNamespace(
        AutoTokenizer=FakeTokenizer,
        AutoModelForSequenceClassification=FakeModel,
    )

    monkeypatch.setitem(__import__("sys").modules, "transformers", fake_transformers)
    monkeypatch.setitem(__import__("sys").modules, "torch", types.SimpleNamespace())
    monkeypatch.setenv("LARGESTACK_ENABLE_PROMPT_GUARD_ML", "1")

    PromptGuard2(revision="test-revision")

    assert ("tokenizer", "meta-llama/Prompt-Guard-2-86M", "test-revision") in calls
    assert ("model", "meta-llama/Prompt-Guard-2-86M", "test-revision") in calls
