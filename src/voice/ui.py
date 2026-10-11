"""Gradio adapters keep errors friendly and raw recordings out of agent history."""
from . import client
from .config import settings, VoiceError


def recognize_into_input(audio, current):
    from qwen_agent.gui.gradio_dep import gr
    text, status = recognize(audio)
    if not isinstance(text, str) or not text.strip():
        return gr.update(), status, gr.update()
    value, status = insert_text(text, current)
    return value, status, gr.update(visible=False)


def speak_inline(turn, history):
    from qwen_agent.gui.gradio_dep import gr
    yield None, '正在准备首句…'
    try:
        from .prepared import prepare, synthesize_chunk
        chunks, voice, first_audio = prepare(history, int(turn))
        yield first_audio, f"正在朗读结论 · {voice['name']} · 第 1 段"
        # Nothing after the first sentence is synthesized until playback is requested.
        for index, chunk in enumerate(chunks[1:], start=2):
            audio = synthesize_chunk(chunk, voice)
            yield audio, f"正在朗读结论 · {voice['name']} · 第 {index} 段"
        yield None, '结论语音已生成，可暂停或重放。'
    except VoiceError as error:
        yield None, error.message
    except Exception:
        yield None, '朗读未完成，请稍后重试。'


def recognize(audio):
    from qwen_agent.gui.gradio_dep import gr
    try:
        text = client.transcribe(audio)
        return text, '已转写，请核对后填入输入框。' if text else '没有识别到讲话，请重新录音。'
    except VoiceError as error:
        return gr.update(), error.message
    except Exception:
        return gr.update(), '无法读取或识别录音，请换用 WAV、MP3 或 M4A。'


def insert_text(text, current):
    from qwen_agent.gui.gradio_dep import gr
    if not text or not text.strip():
        return gr.update(), '请先识别并核对文字。'
    if isinstance(current, dict):
        value = dict(current)
    elif current is not None:
        value = {'text': current.text, 'files': list(current.files or [])}
    else:
        value = {'text': '', 'files': []}
    value['files'] = [gr.data_classes.FileData(**item) if isinstance(item, dict) else item
                      for item in value.get('files', [])]
    value['text'] = '\n'.join(x for x in (value.get('text', '').strip(), text.strip()) if x)
    return value, '已填入输入框，点击发送即可。'


def read_reply(history):
    from qwen_agent.gui.gradio_dep import gr
    try:
        return client.latest_reply(history), '可编辑朗读内容后点击合成。'
    except VoiceError as error:
        return gr.update(), error.message


def speak(text, rate):
    try:
        audio = client.synthesize(text, rate)
        return audio, f"合成完成 · {settings()['voice_name']}；播放器支持暂停和重放。"
    except VoiceError as error:
        return None, error.message
    except Exception:
        return None, '语音合成失败，请检查配置或缩短文本后重试。'
