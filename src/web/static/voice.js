'use strict';
let voiceEpoch = 0, voiceAbort = null, voiceAudio = null, recorder = null, micTimer = null;
const voiceUrls = new Set();
const speakerIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4zM15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
function stopVoice() {
  voiceEpoch++;
  voiceAbort?.abort(); voiceAbort = null;
  voiceAudio?.pause(); voiceAudio = null;
  for (const url of voiceUrls) URL.revokeObjectURL(url);
  voiceUrls.clear();
  if (recorder?.state === 'recording') recorder.stop();
  clearTimeout(micTimer);
}
function voiceButton(conversationId, turn) {
  const wrap = document.createElement('div'); wrap.className = 'voice-action';
  const button = document.createElement('button'); button.type = 'button'; button.className = 'voice-icon';
  button.title = '朗读结论 / 重新播放'; button.setAttribute('aria-label', '朗读结论'); button.innerHTML = speakerIcon;
  const note = document.createElement('span'); note.className = 'voice-note'; note.setAttribute('role', 'status');
  const audio = document.createElement('audio'); audio.controls = true; audio.hidden = true;
  wrap.append(button, note, audio);
  button.addEventListener('click', async () => {
    stopVoice(); const token = voiceEpoch;
    const controller = new AbortController(); voiceAbort = controller; voiceAudio = audio;
    const signal = controller.signal;
    const body = {conversation_id: conversationId, turn};
    const request = (path, data) => api(path, {method:'POST', signal, headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    note.textContent = '正在准备首句…';
    const segment = async (index) => {
      const response = await fetch('/api/voice/segment', {method:'POST', signal, headers:{'Content-Type':'application/json'}, body:JSON.stringify({...body, segment:index})});
      if (!response.ok) {const data = await response.json(); throw new Error(data.detail || '音频生成失败');}
      const blob = await response.blob();
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const url = URL.createObjectURL(blob); voiceUrls.add(url); return url;
    };
    try {
      const prepared = await request('/api/voice/prepare', body);
      let next = segment(0).then(url => ({url}), error => ({error}));
      for (let index = 0; index < prepared.segments; index++) {
        const result = await next;
        if (token !== voiceEpoch) return;
        if (result.error) throw result.error;
        audio.src = result.url; audio.hidden = false;
        note.textContent = `${prepared.voice} · ${index + 1}/${prepared.segments}`;
        const finished = new Promise((resolve, reject) => {
          const aborted = () => {clean(); reject(new DOMException('Aborted', 'AbortError'));};
          const clean = () => {audio.onended = null; audio.onerror = null; signal.removeEventListener('abort', aborted);};
          audio.onended = () => {clean(); resolve();};
          audio.onerror = () => {clean(); reject(new Error('音频播放失败，请重试。'));};
          signal.addEventListener('abort', aborted, {once:true});
        });
        audio.play().catch(() => {if (!signal.aborted) note.textContent = '请点击播放条开始播放';});
        // One segment ahead, only after the user requested playback.
        if (index + 1 < prepared.segments) next = segment(index + 1).then(url => ({url}), error => ({error}));
        await finished;
      }
      note.textContent = '朗读完成 · 点击声音图标可重放全文';
    } catch (error) {if (token === voiceEpoch && error.name !== 'AbortError') note.textContent = error.message;}
  });
  return wrap;
}
function wavBytes(buffer) {
  const samples = buffer.length, data = new ArrayBuffer(44 + samples * 2), view = new DataView(data);
  const str = (offset, text) => {for (let i=0;i<text.length;i++) view.setUint8(offset+i,text.charCodeAt(i));};
  str(0,'RIFF'); view.setUint32(4,36+samples*2,true); str(8,'WAVE'); str(12,'fmt ');
  view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
  view.setUint32(24,buffer.sampleRate,true); view.setUint32(28,buffer.sampleRate*2,true);
  view.setUint16(32,2,true); view.setUint16(34,16,true); str(36,'data'); view.setUint32(40,samples*2,true);
  const channels = Array.from({length:buffer.numberOfChannels},(_,i)=>buffer.getChannelData(i));
  for(let i=0;i<samples;i++) {const value=Math.max(-1,Math.min(1,channels.reduce((sum,c)=>sum+c[i],0)/channels.length));view.setInt16(44+i*2,value<0?value*32768:value*32767,true);}
  return new Blob([data], {type:'audio/wav'});
}
async function toggleMicrophone() {
  if (recorder?.state === 'recording') {recorder.stop(); return;}
  if (state.busy) return;
  stopVoice(); const token = voiceEpoch, button = $('mic-button');
  button.disabled = true;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
    if (token !== voiceEpoch) {stream.getTracks().forEach(track=>track.stop()); return;}
    const parts = [], current = new MediaRecorder(stream); recorder = current;
    current.ondataavailable = event => {if(event.data.size) parts.push(event.data);};
    current.onstop = async () => {
      clearTimeout(micTimer); stream.getTracks().forEach(track=>track.stop()); recorder = null;
      button.classList.remove('recording'); button.setAttribute('aria-label','语音输入'); button.title='语音输入';
      if (token !== voiceEpoch) return;
      let context;
      button.disabled = true;
      try {
        context = new AudioContext();
        const buffer = await context.decodeAudioData(await new Blob(parts).arrayBuffer());
        if (buffer.duration > 60.5) throw new Error('请录制 60 秒以内的音频。');
        const body = new FormData(); body.append('file',wavBytes(buffer),'recording.wav');
        const result = await api('/api/voice/asr',{method:'POST',body});
        if (token === voiceEpoch && !state.busy) {
          $('question').value = [$('question').value.trim(),result.text].filter(Boolean).join('\n');
          $('question').dispatchEvent(new Event('input')); $('question').focus();
        }
      } catch(error) {if(token===voiceEpoch) showError(error.message);}
      finally {await context?.close(); button.disabled=state.busy;}
    };
    current.start(); button.classList.add('recording'); button.setAttribute('aria-label','停止录音'); button.title='停止录音';
    micTimer=setTimeout(()=>{if(current.state==='recording') current.stop();},59000);
  } catch(error) {stream?.getTracks().forEach(track=>track.stop()); showError('无法使用麦克风，请检查浏览器权限。');}
  finally {button.disabled=state.busy;}
}
window.addEventListener('pagehide', stopVoice);
