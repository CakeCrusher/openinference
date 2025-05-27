import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Iterator,
    Mapping,
    Tuple,
)

from opentelemetry.util.types import AttributeValue

from openinference.semconv.trace import (
    MessageAttributes,
    SpanAttributes,
    ToolCallAttributes,
)

if TYPE_CHECKING:
    from mistralai.models import ChatCompletionResponse
    from mistralai.models.ocrresponse import OCRResponse

__all__ = (
    "_ResponseAttributesExtractor",
    "_OCRResponseAttributesExtractor",
)

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class _ResponseAttributesExtractor:
    def get_attributes_from_response(
        self,
        response: Any,
        request_parameters: Mapping[str, Any],
    ) -> Iterator[Tuple[str, AttributeValue]]:
        yield from _get_attributes_from_chat_completion_response(response)


def _get_attributes_from_chat_completion_response(
    response: "ChatCompletionResponse",
) -> Iterator[Tuple[str, AttributeValue]]:
    if model := getattr(response, "model", None):
        yield SpanAttributes.LLM_MODEL_NAME, model
    if usage := getattr(response, "usage", None):
        yield from _get_attributes_from_completion_usage(usage)
    if (choices := getattr(response, "choices", None)) and isinstance(choices, Iterable):
        for choice in choices:
            if (index := _get_attribute_or_value(choice, "index")) is None:
                continue
            if message := _get_attribute_or_value(choice, "message"):
                for key, value in _get_attributes_from_chat_completion_message(message):
                    yield f"{SpanAttributes.LLM_OUTPUT_MESSAGES}.{index}.{key}", value


class _StreamResponseAttributesExtractor:
    def get_attributes_from_response(
        self,
        response: Any,
        request_parameters: Mapping[str, Any],
    ) -> Iterator[Tuple[str, AttributeValue]]:
        yield from _get_attributes_from_stream_chat_completion_response(response)


def _get_attributes_from_stream_chat_completion_response(
    response: Any,
) -> Iterator[Tuple[str, AttributeValue]]:
    data = response.data
    if model := data.get("model", None):
        yield SpanAttributes.LLM_MODEL_NAME, model
    if usage := data.get("usage", None):
        yield from _get_attributes_from_completion_usage(usage)
    if (choices := data.get("choices", None)) and isinstance(choices, Iterable):
        for choice in choices:
            if (index := _get_attribute_or_value(choice, "index")) is None:
                continue
            if message := _get_attribute_or_value(choice, "message"):
                for key, value in _get_attributes_from_chat_completion_message(message):
                    yield f"{SpanAttributes.LLM_OUTPUT_MESSAGES}.{index}.{key}", value


def _get_attributes_from_chat_completion_message(
    message: "ChatCompletionResponse",
) -> Iterator[Tuple[str, AttributeValue]]:
    if role := _get_attribute_or_value(message, "role"):
        yield MessageAttributes.MESSAGE_ROLE, role
    if content := _get_attribute_or_value(message, "content"):
        yield MessageAttributes.MESSAGE_CONTENT, content
    if (tool_calls := _get_attribute_or_value(message, "tool_calls")) and isinstance(
        tool_calls, Iterable
    ):
        for index, tool_call in enumerate(tool_calls):
            if function := _get_attribute_or_value(tool_call, "function"):
                if name := _get_attribute_or_value(function, "name"):
                    yield (
                        (
                            f"{MessageAttributes.MESSAGE_TOOL_CALLS}.{index}."
                            f"{ToolCallAttributes.TOOL_CALL_FUNCTION_NAME}"
                        ),
                        name,
                    )
                if arguments := _get_attribute_or_value(function, "arguments"):
                    yield (
                        f"{MessageAttributes.MESSAGE_TOOL_CALLS}.{index}."
                        f"{ToolCallAttributes.TOOL_CALL_FUNCTION_ARGUMENTS_JSON}",
                        arguments,
                    )


def _get_attributes_from_completion_usage(
    usage: object,
) -> Iterator[Tuple[str, AttributeValue]]:
    # openai.types.CompletionUsage
    # See https://github.com/openai/openai-python/blob/f1c7d714914e3321ca2e72839fe2d132a8646e7f/src/openai/types/completion_usage.py#L8  # noqa: E501
    if (total_tokens := _get_attribute_or_value(usage, "total_tokens")) is not None:
        yield SpanAttributes.LLM_TOKEN_COUNT_TOTAL, total_tokens
    if (prompt_tokens := _get_attribute_or_value(usage, "prompt_tokens")) is not None:
        yield SpanAttributes.LLM_TOKEN_COUNT_PROMPT, prompt_tokens
    if (completion_tokens := _get_attribute_or_value(usage, "completion_tokens")) is not None:
        yield SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, completion_tokens


def _get_attribute_or_value(
    obj: Any,
    attribute_name: str,
) -> Any:
    if (value := getattr(obj, attribute_name, None)) is not None or (
        hasattr(obj, "get") and callable(obj.get) and (value := obj.get(attribute_name)) is not None
    ):
        return value
    return None


class _OCRResponseAttributesExtractor:
    def get_attributes_from_response(
        self,
        response: Any,
        request_parameters: Mapping[str, Any],
    ) -> Iterator[Tuple[str, AttributeValue]]:
        yield from _get_attributes_from_ocr_response(response)


def _get_attributes_from_ocr_response(
    response: "OCRResponse",
) -> Iterator[Tuple[str, AttributeValue]]:
    if model := getattr(response, "model", None):
        yield SpanAttributes.LLM_MODEL_NAME, model

    # Extract usage information
    if usage_info := getattr(response, "usage_info", None):
        if total_tokens := _get_attribute_or_value(usage_info, "total_tokens"):
            yield SpanAttributes.LLM_TOKEN_COUNT_TOTAL, total_tokens
        if prompt_tokens := _get_attribute_or_value(usage_info, "prompt_tokens"):
            yield SpanAttributes.LLM_TOKEN_COUNT_PROMPT, prompt_tokens

    # Extract document annotation if available
    if doc_annotation := getattr(response, "document_annotation", None):
        yield "ocr.document_annotation", doc_annotation

    # Extract pages information
    if (pages := getattr(response, "pages", None)) and isinstance(pages, Iterable):
        for idx, page in enumerate(pages):
            if page_index := _get_attribute_or_value(page, "index"):
                yield f"ocr.pages.{idx}.index", page_index
            if markdown := _get_attribute_or_value(page, "markdown"):
                yield f"ocr.pages.{idx}.markdown", markdown
            if dimensions := _get_attribute_or_value(page, "dimensions"):
                if width := _get_attribute_or_value(dimensions, "width"):
                    yield f"ocr.pages.{idx}.dimensions.width", width
                if height := _get_attribute_or_value(dimensions, "height"):
                    yield f"ocr.pages.{idx}.dimensions.height", height
            # Don't extract images as they can be numerous and contribute to attribute limits
