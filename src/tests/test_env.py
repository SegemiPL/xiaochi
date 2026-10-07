"""Private dotenv loading and deployment-environment precedence."""

from pathlib import Path

from src.config.env import PROJECT_ENV_PATH, load_project_env
from src.config.llm import load_llm_config
from src.websearch.deepseek import DeepSeekSearchClient


def test_repo_env_path_is_anchored_to_code_not_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert PROJECT_ENV_PATH == Path(__file__).resolve().parents[2] / '.env'


def test_dotenv_key_used_by_chat_and_search_without_overwriting_environment(monkeypatch, tmp_path):
    path = tmp_path / '.env'
    path.write_text('DEEPSEEK_API_KEY=synthetic-file-key\n')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    load_project_env(path)
    assert load_llm_config(provider='deepseek')['api_key'] == 'synthetic-file-key'
    headers = []

    def transport(request, timeout):
        headers.append(dict(request.header_items()))
        return 200, b'{"content":[{"type":"web_search_tool_result","content":[]}]}'

    DeepSeekSearchClient(transport=transport).search('test')
    assert headers[0]['X-api-key'] == 'synthetic-file-key'
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'synthetic-process-key')
    load_project_env(path)
    assert load_llm_config(provider='deepseek')['api_key'] == 'synthetic-process-key'


def test_missing_env_file_does_not_fail_startup(tmp_path):
    assert load_project_env(tmp_path / 'absent.env') is False
