"""Tests for durable WebUI conversation storage."""

import json

import pytest
from src.agent.conversations import ConversationStore, conversation_title


def test_conversation_title_uses_first_user_text():
    messages = [
        {"role": "assistant", "content": "ignored"},
        {"role": "user", "content": [{"text": "  跨境   税务问题  "}, {"file": "/x"}]},
    ]
    assert conversation_title(messages) == "跨境 税务问题"


def test_store_round_trip_and_updates_without_changing_created_at(tmp_path):
    store = ConversationStore(tmp_path)
    messages = [{"role": "user", "content": [{"text": "你好"}], "name": "user"}]
    conversation_id = store.create(messages)
    first = store.load(conversation_id)

    messages.append({"role": "assistant", "content": "你好，有什么可以帮你？"})
    second = store.save(conversation_id, messages)

    assert second["messages"] == messages
    assert second["title"] == "你好"
    assert second["created_at"] == first["created_at"]
    assert store.list()[0]["id"] == conversation_id


def test_store_ignores_invalid_files_and_rejects_path_traversal(tmp_path):
    store = ConversationStore(tmp_path)
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert store.list() == []
    with pytest.raises(ValueError):
        store.load("../outside")


def test_store_serializes_model_dump_values(tmp_path):
    class ModelLike:
        def model_dump(self, **_kwargs):
            return {"role": "assistant", "content": "done"}

    store = ConversationStore(tmp_path)
    conversation_id = store.create([ModelLike()])
    payload = json.loads((tmp_path / f"{conversation_id}.json").read_text(encoding="utf-8"))
    assert payload["messages"] == [{"role": "assistant", "content": "done"}]


def test_deleted_history_stays_hidden_after_restart_and_restore_preserves_both_histories(tmp_path):
    store = ConversationStore(tmp_path)
    deleted = store.create([{'role': 'assistant', 'content': 'PRIVATE_TOOL_CONTEXT'}])
    record = store.save(deleted, [{'role': 'assistant', 'content': 'PRIVATE_TOOL_CONTEXT'}],
                        public_messages=[{'role': 'assistant', 'content': '公开结论'}])
    other = store.create([{'role': 'user', 'content': '另一个对话'}])
    other_bytes = (tmp_path / f'{other}.json').read_bytes()
    store.delete(deleted)
    restarted = ConversationStore(tmp_path)
    assert [item['id'] for item in restarted.list()] == [other]
    with pytest.raises(FileNotFoundError):
        restarted.load(deleted)
    restarted.restore(deleted)
    assert restarted.load(deleted) == record
    assert (tmp_path / f'{other}.json').read_bytes() == other_bytes


def test_history_mutations_reject_invalid_ids_and_missing_records(tmp_path):
    store = ConversationStore(tmp_path)
    for operation in (store.delete, store.restore):
        with pytest.raises(ValueError):
            operation('../outside')
        with pytest.raises(FileNotFoundError):
            operation('a' * 32)
