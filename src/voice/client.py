"""Plain ASR/TTS operations consumed by the Gradio callbacks."""
import io
import json
import re
import wave
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, build_opener

import numpy as np
import soundfile as sf

from .config import VoiceError, settings
from .fish import FishSpeechEngine, NoRedirect

engine = FishSpeechEngine()


def transcribe(path):
    if not path:
        raise VoiceError('NO_AUDIO', '请先录音或选择音频。', 422)
    info = sf.info(path)
    if not 0 < info.duration <= 60 or not 8000 <= info.samplerate <= 96000 or info.channels > 2:
        raise VoiceError('INVALID_AUDIO', '请使用 60 秒以内的单声道或双声道录音。', 422)
    samples, rate = sf.read(path, dtype='float32', always_2d=True)
    mono = np.mean(samples, axis=1)
    output = io.BytesIO()
    sf.write(output, mono, rate, format='WAV', subtype='PCM_16')
    base = settings()['asr_url'].rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise VoiceError('INVALID_CONFIG', 'ASR 地址必须是本机 HTTP 服务。')
    request = Request(base + '/api/asr', data=output.getvalue(), headers={
        'Content-Type': 'audio/wav', 'X-Voice-Lab': '1'}, method='POST')
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=125) as response:
            result = json.loads(response.read(64_000))
        return result['text']
    except HTTPError as error:
        code = error.code
        error.close()
        raise VoiceError('ASR_FAILED', f'本机识别失败（HTTP {code}），请检查录音或稍后重试。') from None
    except (URLError, TimeoutError, OSError):
        raise VoiceError('ASR_UNAVAILABLE', '本机 ASR 未启动，请运行语音文档中的启动命令。') from None


def plain_text(text):
    text = re.sub(r'<details\b[^>]*>.*?</details>', '', str(text), flags=re.S | re.I)
    text = re.sub(r'<think>.*?</think>', '', str(text), flags=re.S)
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'(?m)^\s*[#>]+\s*', '', text)
    return re.sub(r'[*`_]', '', text).strip()


def final_answer(history, turn, conclusion_only=True):
    """Resolve a completed turn from authoritative history, never rendered DOM."""
    turns = []
    for message in history or []:
        if message.get('role') == 'user':
            turns.append([])
        elif turns:
            turns[-1].append(message)
    if not isinstance(turn, int) or not 0 <= turn < len(turns):
        raise VoiceError('NO_REPLY', '请等待本轮回答完成后再朗读。', 422)
    messages = turns[turn]
    if (not messages or messages[-1].get('role') != 'assistant'
            or messages[-1].get('function_call') or messages[-1].get('tool_calls')
            or messages[-1].get('name') not in (None, '', '3wagent')):
        raise VoiceError('NO_REPLY', '请等待本轮回答完成后再朗读。', 422)
    text = latest_reply(messages)
    if not conclusion_only:
        return text
    # Prefer an explicitly labelled conclusion. Without one, the final answer
    # is the conclusion; never infer a summary from intermediate tool messages.
    raw = messages[-1].get('content', '')
    if isinstance(raw, str):
        lines = raw.splitlines()
        for index, line in enumerate(lines):
            label = re.sub(r'^[#\s*\d.、（）()]+', '', line).strip('* :：')
            if label in {'结论', '核心结论', '最终结论', '简要结论', '结论与建议', '总结'}:
                level = len(line) - len(line.lstrip('#'))
                end = index + 1
                while end < len(lines):
                    heading = re.match(r'^(#{1,6})\s+', lines[end])
                    if heading and (not level or len(heading[1]) <= level):
                        break
                    if not level and re.match(r'^\*\*[^*]+\*\*\s*$', lines[end]):
                        break
                    end += 1
                conclusion = plain_text('\n'.join(lines[index + 1:end]))
                if conclusion:
                    text = conclusion
                    break
    return text


def speech_chunks(text):
    """Keep the first sentence separate so speculative work stops there."""
    text = plain_text(text)
    if not 1 <= len(text) <= 12000 or not any(c.isalnum() for c in text):
        raise VoiceError('INVALID_TEXT', '结论需为 1–12000 字，长回答请让模型简要总结。', 422)
    sentences = re.findall(r'[^。！？!?；;\n]+[。！？!?；;\n]*', text)
    parts = [sentence[offset:offset + 100]
             for sentence in sentences for offset in range(0, len(sentence), 100)]
    chunks = [parts[0]]
    current = ''
    for part in parts[1:]:
        if current and len(current) + len(part) > 120:
            chunks.append(current)
            current = ''
        current += part
    if current:
        chunks.append(current)
    return chunks


def synthesize_segments(text, rate=1.0):
    config = settings()
    voice = {'reference_id': config['voice_id'], 'name': config['voice_name']}
    for chunk in speech_chunks(text):
        audio, _ = engine.synthesize(chunk, rate, voice)
        yield audio


def latest_reply(history):
    for message in reversed(history or []):
        if message.get('role') == 'user':
            break
        if (message.get('role') == 'assistant' and not message.get('function_call')
                and message.get('name') in (None, '', '3wagent')):
            content = message.get('content', '')
            if isinstance(content, list):
                content = '\n'.join(x.get('text', '') for x in content if isinstance(x, dict))
            if plain_text(content):
                return plain_text(content)
    raise VoiceError('NO_REPLY', '还没有已完成的主 Agent 回复。', 422)


def synthesize(text, rate=1.0):
    text = plain_text(text)
    if not 1 <= len(text) <= 2000 or not any(c.isalnum() for c in text):
        raise VoiceError('INVALID_TEXT', '请选择 1–2000 字的内容朗读，长报告请分段。', 422)
    if not 0.75 <= rate <= 1.5:
        raise VoiceError('INVALID_RATE', '语速范围是 0.75–1.5。', 422)
    config = settings()
    voice = {'reference_id': config['voice_id'], 'name': config['voice_name']}
    chunks = []
    current = ''
    for sentence in re.findall(r'[^。！？!?\n]+[。！？!?\n]*', text):
        for offset in range(0, len(sentence), 400):
            part = sentence[offset:offset + 400]
            if len(current) + len(part) > 400:
                chunks.append(current)
                current = ''
            current += part
    if current:
        chunks.append(current)
    pcm = []
    for chunk in chunks:
        audio, _ = engine.synthesize(chunk, float(rate), voice)
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            pcm.append(np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').copy())
    return 24000, np.concatenate(pcm)
