"""GPT response service extracted from admin.py."""

from __future__ import annotations

import asyncio
import queue
import json
import time

try:
    from deva.llm.worker_runtime import submit_ai_coro
except Exception:
    submit_ai_coro = None

from ..llm.config_utils import (
    build_model_config_example,
    build_model_config_message,
    get_model_config_status,
)


async def get_gpt_response(ctx, prompt, session=None, scope=None, model_type="deepseek", flush_interval=3):
    NB = ctx["NB"]
    warn = ctx["warn"]
    log = ctx["log"]
    requests = ctx["requests"]
    AsyncOpenAI = ctx["AsyncOpenAI"]
    put_out = ctx["put_out"]
    toast = ctx["toast"]
    run_ai_in_worker = ctx.get("run_ai_in_worker")

    status = get_model_config_status(NB, model_type)
    config = status["config"]
    if not status["ready"]:
        message = build_model_config_message(model_type, status["missing"])
        message >> warn
        build_model_config_example(model_type, status["missing"]) >> warn
        if session:
            try:
                toast(f"{message} 请先在 NB 中完成配置。", color="warning")
            except Exception:
                pass
        return ""

    api_key = config.get("api_key")
    base_url = config.get("base_url")
    model = config.get("model")
    messages = [{"role": "user", "content": prompt}]

    async def diagnose_backend_error():
        try:
            url = base_url.rstrip("/") + "/chat/completions"
            payload = {"model": model, "messages": messages, "stream": False, "max_tokens": 64}
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            resp = await asyncio.to_thread(requests.post, url, headers=headers, data=json.dumps(payload), timeout=15)
            text = (resp.text or "").strip()
            try:
                data = resp.json()
            except Exception:
                data = None
            if isinstance(data, dict):
                code = data.get("code")
                message = data.get("message")
                if code not in (None, 0):
                    return f"上游接口错误(code={code}, message={message})"
                if message and not data.get("choices"):
                    return f"上游接口返回异常消息(message={message})"
            return f"上游返回异常响应(status={resp.status_code}, body={text[:300]})"
        except Exception as probe_error:
            return f"上游诊断失败({type(probe_error).__name__}: {probe_error})"

    def safe_toast(message, color="error"):
        if not session:
            return
        try:
            toast(message, color=color)
        except RuntimeError as e:
            (f"toast skipped(no task context): {e}") >> log
        except Exception as e:
            (f"toast failed: {e}") >> log

    start_time = time.time()
    if session:
        def logfunc(output_text):
            put_out(output_text, type="markdown", scope=scope, session=session)
    else:
        def logfunc(output_text):
            output_text >> log

    async def _worker_non_stream_call():
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                max_tokens=8192,
            )
            return (completion.choices[0].message.content or "").strip()
        finally:
            await client.close()

    # Unified AI execution model: prefer dedicated worker loop (streaming in worker).
    if run_ai_in_worker is not None and submit_ai_coro is not None:
        SENTINEL = object()
        q = queue.Queue()

        async def _worker_stream_call():
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            text = ""
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=True,
                    max_tokens=8192,
                )
                async for chunk in response:
                    content = ""
                    if getattr(chunk, "choices", None):
                        delta = getattr(chunk.choices[0], "delta", None)
                        content = getattr(delta, "content", "") or ""
                    if content and not content.startswith("检索"):
                        text += content
                        q.put(content)
                return text
            finally:
                q.put(SENTINEL)
                await client.close()

        try:
            worker_future = submit_ai_coro(_worker_stream_call())
            buffer = ""
            accumulated_text = ""
            last_flush_ts = time.time()

            while True:
                try:
                    item = await asyncio.to_thread(q.get, True, 0.2)
                except queue.Empty:
                    if buffer.strip() and (time.time() - last_flush_ts >= flush_interval):
                        logfunc(buffer)
                        accumulated_text += buffer
                        buffer = ""
                        last_flush_ts = time.time()
                    if worker_future.done():
                        break
                    continue

                if item is SENTINEL:
                    break

                buffer += item
                paragraph_end_markers = (".", "?", "!", "。", "？", "！")
                is_paragraph_end = len(buffer) >= 2 and buffer[-2] in paragraph_end_markers and buffer[-1] == "\n"
                if is_paragraph_end or (time.time() - last_flush_ts >= flush_interval):
                    if buffer.strip():
                        logfunc(buffer)
                        accumulated_text += buffer
                        buffer = ""
                        last_flush_ts = time.time()

            worker_text = await asyncio.wrap_future(worker_future)
            if buffer.strip():
                logfunc(buffer)
                accumulated_text += buffer

            if worker_text and not accumulated_text:
                logfunc(worker_text)
                accumulated_text = worker_text

            if accumulated_text.strip():
                return accumulated_text

            backend_error = await diagnose_backend_error()
            (f"GPT空响应(model={model_type}/{model}): {backend_error}") >> warn
            safe_toast("模型返回空内容: " + backend_error, color="error")
            return f"[GPT_EMPTY] {backend_error}"
        except Exception as worker_error:
            (f"worker loop stream call failed, fallback local stream path: {worker_error}") >> log

    # Backward fallback: worker available but no submit helper.
    if run_ai_in_worker is not None and submit_ai_coro is None:
        try:
            one_shot_text = await run_ai_in_worker(_worker_non_stream_call())
            if one_shot_text:
                logfunc(one_shot_text)
                return one_shot_text
            backend_error = await diagnose_backend_error()
            (f"GPT空响应(model={model_type}/{model}): {backend_error}") >> warn
            safe_toast("模型返回空内容: " + backend_error, color="error")
            return f"[GPT_EMPTY] {backend_error}"
        except Exception as worker_error:
            (f"worker loop one-shot call failed, fallback local stream path: {worker_error}") >> log

    gpt_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        response = await gpt_client.chat.completions.create(model=model, messages=messages, stream=True, max_tokens=8192)
    except Exception as e:
        backend_error = await diagnose_backend_error()
        (f"请求失败: {ctx['traceback'].format_exc()} | {backend_error}") >> log
        (f"GPT请求失败(model={model_type}/{model}): {backend_error}") >> warn
        safe_toast("请求失败: " + backend_error, color="error")
        return f"[GPT_ERROR] {backend_error}"

    buffer = ""
    accumulated_text = ""

    async def process_chunk(chunk, buf, text, ts):
        content = ""
        if getattr(chunk, "choices", None):
            delta = getattr(chunk.choices[0], "delta", None)
            content = getattr(delta, "content", "") or ""
        if content:
            if content.startswith("检索"):
                return buf, text, ts
            buf += content
            paragraph_end_markers = (".", "?", "!", "。", "？", "！")
            is_paragraph_end = len(buf) >= 2 and buf[-2] in paragraph_end_markers and buf[-1] == "\n"
            if (is_paragraph_end or time.time() - ts >= flush_interval) and buf.strip():
                if is_paragraph_end:
                    last_paragraph_end = max((buf.rfind(marker) for marker in paragraph_end_markers), default=-1)
                    if last_paragraph_end != -1:
                        output_text = buf[: last_paragraph_end + 1]
                        buf = buf[last_paragraph_end + 1 :]
                    else:
                        output_text = buf
                        buf = ""
                else:
                    last_sentence_end = max((buf.rfind(marker) for marker in paragraph_end_markers), default=-1)
                    if last_sentence_end != -1:
                        output_text = buf[: last_sentence_end + 1]
                        buf = buf[last_sentence_end + 1 :]
                    else:
                        output_text = buf
                        buf = ""
                if output_text.strip():
                    text += output_text
                    logfunc(output_text)
                    ts = time.time()
        if buf and not content:
            text += buf
            logfunc(buf)
            ts = time.time()
            buf = ""
        return buf, text, ts

    try:
        async for chunk in response:
            buffer, accumulated_text, start_time = await process_chunk(chunk, buffer, accumulated_text, start_time)
        if buffer.strip():
            accumulated_text += buffer
            logfunc(buffer)
            buffer = ""
        if not accumulated_text.strip():
            backend_error = await diagnose_backend_error()
            (f"GPT空响应(model={model_type}/{model}): {backend_error}") >> warn
            safe_toast("模型返回空内容: " + backend_error, color="error")
            return f"[GPT_EMPTY] {backend_error}"
        return accumulated_text
    finally:
        await gpt_client.close()
