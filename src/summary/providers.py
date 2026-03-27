from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

import httpx

from ..exceptions import SummaryProviderError


SKIP_PREFIX = "AI Summary can't be generated:"


class SummaryProvider(Protocol):
    name: str

    def summarize_many(
        self,
        section_text: str,
        *,
        file_path: str,
        top_title: str,
        id_to_title: dict[str, str],
    ) -> dict[str, str]:
        ...


@dataclass
class SkippedSummaryProvider:
    reason: str
    name: str = "summary-skipped"

    def summarize_many(
        self,
        section_text: str,
        *,
        file_path: str,
        top_title: str,
        id_to_title: dict[str, str],
    ) -> dict[str, str]:
        msg = f"{SKIP_PREFIX} {self.reason}"
        return {sec_id: msg for sec_id in id_to_title}


@dataclass
class OpenAICompatibleSummaryProvider:
    base_url: str
    api_key: str
    model: str
    system_prompt: str
    user_prompt: str
    timeout_seconds: float = 30.0
    max_retries: int = 2
    name: str = "openai-compatible"

    def summarize_many(
        self,
        section_text: str,
        *,
        file_path: str,
        top_title: str,
        id_to_title: dict[str, str],
    ) -> dict[str, str]:
        mapping_lines = "\n".join(
            [f"{idx}. id={sec_id} => title={title}" for idx, (sec_id, title) in enumerate(id_to_title.items(), 1)]
        )
        prompt_values = {
            "title": top_title,
            "top_title": top_title,
            "TOP_LEVEL_TITLE": top_title,
            "file_path": file_path,
            "FILE_PATH": file_path,
            "content": section_text,
            "MARKDOWN_SUBTREE": section_text,
            "SECTION_ID_MAP_TEXT": mapping_lines,
        }
        try:
            prompt = self.user_prompt.format(**prompt_values)
        except KeyError as exc:
            missing = str(exc).strip("'")
            raise SummaryProviderError(
                f"Invalid user_prompt placeholder: '{missing}'. "
                "Supported placeholders: {title}, {top_title}, {TOP_LEVEL_TITLE}, "
                "{file_path}, {FILE_PATH}, {content}, {MARKDOWN_SUBTREE}, {SECTION_ID_MAP_TEXT}."
            ) from exc
        last_error: Exception | None = None
        for _ in range(self.max_retries + 1):
            try:
                return self._request_summary_map(prompt, id_to_title)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise SummaryProviderError(f"Summary API failed after retries: {last_error}") from last_error

    def _request_summary_map(self, prompt: str, id_to_title: dict[str, str]) -> dict[str, str]:
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        schema = {
            "type": "object",
            "properties": {sec_id: {"type": "string"} for sec_id in id_to_title},
            "required": list(id_to_title.keys()),
            "additionalProperties": False,
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "section_summaries",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        try:
            msg = data["choices"][0]["message"]
            content = msg["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise SummaryProviderError("Invalid JSON schema response format.") from exc

        out: dict[str, str] = {}
        for sec_id in id_to_title:
            value = parsed.get(sec_id, "")
            text = str(value).strip()
            if not text:
                raise SummaryProviderError(f"Missing summary for id '{sec_id}' in JSON schema response.")
            out[sec_id] = text
        return out


def provider_from_name(
    provider: str,
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
) -> SummaryProvider:
    if provider != "openai-compatible":
        return SkippedSummaryProvider(reason=f"unsupported provider '{provider}'")

    missing: list[str] = []
    if not api_base:
        missing.append("api_base")
    if not api_key:
        missing.append("api_key")
    if not model:
        missing.append("model")
    if not system_prompt:
        missing.append("system_prompt")
    if not user_prompt:
        missing.append("user_prompt")
    if missing:
        return SkippedSummaryProvider(reason=f"missing required AI config: {', '.join(missing)}")

    return OpenAICompatibleSummaryProvider(
        base_url=api_base,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
