"""DSPy LM adapter for OpenAI Responses API or Chat Completions API."""

import json
import time
from typing import Any

import dspy


class _MockMessage:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _MockChoice:
    def __init__(self, content):
        self.message = _MockMessage(content)
        self.logprobs = None


class _MockUsage(dict):
    def __init__(self):
        super().__init__(prompt_tokens=0, completion_tokens=0, total_tokens=0)


class _MockChatCompletion:
    def __init__(self, text, model):
        self.choices = [_MockChoice(text)]
        self.usage = _MockUsage()
        self.model = model
        self._hidden_params = {}


class ResponsesAPILM(dspy.BaseLM):
    """DSPy LM adapter for OpenAI Responses API or Chat Completions API.

    Supports:
    - infiniteai Responses API (streaming SSE)
    - NVIDIA NIM Chat Completions API (with reasoning_content capture)
    """
    def __init__(self, model, api_key, api_base, reasoning_effort='low',
                 max_tokens=16000, timeout=600, num_retries=2,
                 use_chat_completions=False,
                 chat_template_kwargs: dict[str, Any] | None = None):
        """
        Args:
            use_chat_completions: If True, use /v1/chat/completions endpoint (NVIDIA).
                                  If False, use /v1/responses endpoint (infiniteai).
        """
        super().__init__(model=model, model_type='chat', temperature=1.0, max_tokens=max_tokens)
        self.api_key = api_key
        self.api_base = api_base.rstrip('/')
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self.num_retries = num_retries
        self.use_chat_completions = use_chat_completions
        self.chat_template_kwargs = chat_template_kwargs or {}
        self._last_reasoning_content = None  # Store reasoning for logging
        self._last_output_text = None  # Store raw model output text for audit

    def _messages_to_input(self, messages):
        """Convert DSPy message list to Responses API format.

        Returns (input_items, instructions) where instructions collects all
        system-role content (infiniteai does not support system role in input[]).
        """
        input_items = []
        system_parts = []
        for m in messages:
            role = m.get('role', 'user')
            content = m.get('content', '')
            if isinstance(content, str):
                content_list = [{'type': 'input_text', 'text': content}]
            else:
                content_list = content
            if role == 'system':
                for part in content_list:
                    text = part.get('text', '') if isinstance(part, dict) else str(part)
                    if text:
                        system_parts.append(text)
            else:
                input_items.append({'type': 'message', 'role': role, 'content': content_list})
        instructions = '\n\n'.join(system_parts) if system_parts else None
        return input_items, instructions

    @staticmethod
    def _extract_system_parts(content):
        """Extract text fragments from system message content."""
        if isinstance(content, str):
            return [content]
        if not isinstance(content, list):
            return []
        return [part['text'] for part in content if isinstance(part, dict) and 'text' in part]

    def _build_chat_messages(self, messages):
        """Build chat-completions messages and fold system text into first user turn."""
        chat_messages = []
        system_content = []

        for message in messages:
            role = message.get('role', 'user')
            content = message.get('content', '')
            if role == 'system':
                system_content.extend(self._extract_system_parts(content))
            else:
                chat_messages.append({'role': role, 'content': content})

        if system_content:
            system_prefix = '\n\n'.join(system_content)
            if chat_messages:
                first_content = str(chat_messages[0]['content'])
                chat_messages[0]['content'] = f"{system_prefix}\n\n{first_content}"
            else:
                chat_messages.append({'role': 'user', 'content': system_prefix})
        return chat_messages

    @staticmethod
    def _raise_response_error(data):
        """Raise normalized RuntimeError for Responses API failure payload."""
        error = data.get('error', {})
        code = error.get('code', 'unknown')
        message = error.get('message', 'unknown error')
        raise RuntimeError(f"ResponsesAPI error: {code} - {message}")

    def _call_once_chat_completions(self, messages):
        """Call Chat Completions API (NVIDIA style) with streaming."""
        import requests

        url = f'{self.api_base}/chat/completions'
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        chat_messages = self._build_chat_messages(messages)

        payload = {
            'model': self.model,
            'messages': chat_messages,
            'max_tokens': self.kwargs.get('max_tokens', 16000),
            'temperature': self.kwargs.get('temperature', 1.0),
            'top_p': 1.0,
            'stream': True,
        }
        if self.chat_template_kwargs:
            payload['chat_template_kwargs'] = self.chat_template_kwargs

        # For reasoning models, add reasoning_effort if supported
        if self.reasoning_effort:
            # NVIDIA uses reasoning_effort parameter
            payload['reasoning_effort'] = self.reasoning_effort

        resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=self.timeout)
        resp.raise_for_status()

        self._last_reasoning_content = None
        self._last_output_text = None
        reasoning_parts = []
        content_parts = []

        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode('utf-8') if isinstance(line, bytes) else line
            if not line.startswith('data: '):
                continue
            if line == 'data: [DONE]':
                break

            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            choices = data.get('choices', [])
            if not choices:
                continue

            delta = choices[0].get('delta', {})

            # Capture reasoning_content (NVIDIA format)
            if delta.get('reasoning_content') is not None:
                reasoning_parts.append(delta['reasoning_content'])

            # Capture content
            if delta.get('content'):
                content_parts.append(delta['content'])

        self._last_reasoning_content = ''.join(reasoning_parts)
        self._last_output_text = ''.join(content_parts)
        return self._last_output_text

    def _call_once(self, input_items, instructions=None):
        """Call Responses API (infiniteai style)."""
        import requests

        url = f'{self.api_base}/responses'
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.model,
            'input': input_items,
            'reasoning': {'effort': self.reasoning_effort},
            'max_output_tokens': self.kwargs.get('max_tokens', 16000),
            'store': False,
            'stream': False,
        }
        if instructions:
            payload['instructions'] = instructions
        self._last_reasoning_content = None
        self._last_output_text = None
        resp = requests.post(url, json=payload, headers=headers,
                             stream=False, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        # Check for error in response
        if data.get('status') == 'failed' or 'error' in data:
            self._raise_response_error(data)

        # Extract text from response
        output = data.get('output', [])
        for item in reversed(output):
            if item.get('type') == 'message':
                for part in item.get('content', []):
                    if part.get('type') == 'output_text':
                        # Responses API doesn't return reasoning separately.
                        self._last_reasoning_content = None
                        self._last_output_text = part['text']
                        return part['text']

        if 'response' in data:
            output = data['response'].get('output', [])
            for item in reversed(output):
                if item.get('type') == 'message':
                    for part in item.get('content', []):
                        if part.get('type') == 'output_text':
                            self._last_reasoning_content = None
                            self._last_output_text = part['text']
                            return part['text']

        raise RuntimeError('ResponsesAPILM: no output_text found in response')

    def forward(self, prompt=None, messages=None, **kwargs):
        if prompt is not None:
            messages = [{'role': 'user', 'content': prompt}]

        if self.use_chat_completions:
            # Use Chat Completions API (NVIDIA style)
            last_err = None
            for attempt in range(self.num_retries):
                try:
                    text = self._call_once_chat_completions(messages)
                    return _MockChatCompletion(text, self.model)
                except Exception as e:
                    last_err = e
                    time.sleep(2 ** attempt)
            raise last_err
        else:
            # Use Responses API (infiniteai style)
            input_items, instructions = self._messages_to_input(messages or [])
            last_err = None
            for attempt in range(self.num_retries):
                try:
                    text = self._call_once(input_items, instructions)
                    return _MockChatCompletion(text, self.model)
                except Exception as e:
                    last_err = e
                    time.sleep(2 ** attempt)
            raise last_err
