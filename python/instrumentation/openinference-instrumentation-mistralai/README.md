# OpenInference Mistral AI Instrumentation
[![PyPI Version](https://img.shields.io/pypi/v/openinference-instrumentation-mistralai.svg)](https://pypi.python.org/pypi/openinference-instrumentation-mistralai) 

Python autoinstrumentation library for MistralAI's Python SDK.

The traces emitted by this instrumentation are fully OpenTelemetry compatible and can be sent to an OpenTelemetry collector for viewing, such as [`arize-phoenix`](https://github.com/Arize-ai/phoenix)

## Installation

```shell
pip install openinference-instrumentation-mistralai
```

## Quickstart

In this example we will instrument a small program that uses the MistralAI chat completions API and observe the traces via [`arize-phoenix`](https://github.com/Arize-ai/phoenix).

Install packages.

```shell
pip install openinference-instrumentation-mistralai mistralai arize-phoenix opentelemetry-sdk opentelemetry-exporter-otlp
```

Start the phoenix server so that it is ready to collect traces.
The Phoenix server runs entirely on your machine and does not send data over the internet.

```shell
python -m phoenix.server.main serve
```

In a python file, setup the `MistralAIInstrumentor` and configure the tracer to send traces to Phoenix.

```python
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from openinference.instrumentation.mistralai import MistralAIInstrumentor
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

endpoint = "http://127.0.0.1:6006/v1/traces"
tracer_provider = trace_sdk.TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint)))
# Optionally, you can also print the spans to the console.
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace_api.set_tracer_provider(tracer_provider)

MistralAIInstrumentor().instrument()


if __name__ == "__main__":
    client = MistralClient()
    response = client.chat(
        model="mistral-large-latest",
        messages=[
            ChatMessage(
                content="Who won the World Cup in 2018?",
                role="user",
            )
        ],
    )
    print(response.choices[0].message.content)

```

Since we are using MistralAI, we must set the `MISTRAL_API_KEY` environment variable to authenticate with the MistralAI API.

```shell
export MISTRAL_API_KEY=[your_key_here]
```

Now simply run the python file and observe the traces in Phoenix.

```shell
python your_file.py
```

## Supported Features

The instrumentation supports the following Mistral AI features:

- Chat Completions (synchronous and asynchronous)
- Streaming Chat Completions (synchronous and asynchronous)
- Agent API (synchronous and asynchronous)
- OCR Document Processing (synchronous and asynchronous)

### OCR Support

The instrumentation now supports Mistral AI's OCR (Optical Character Recognition) capabilities, allowing you to trace and monitor document processing tasks. Here's a simple example:

```python
from mistralai import Mistral
from mistralai.models.responseformat import ResponseFormat
from openinference.instrumentation.mistralai import MistralAIInstrumentor

# Setup instrumentation (tracer setup omitted for brevity)
MistralAIInstrumentor().instrument()

client = Mistral(api_key="your-api-key")

# Process a document with OCR
document = {"url": "https://example.com/sample.pdf"}

response = client.ocr.process(
    model="mistral-large-latest",
    document=document,
    pages=[0, 1],  # Process first two pages
    bbox_annotation_format=ResponseFormat(
        type="json_schema", 
        schema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "confidence": {"type": "number"},
            }
        }
    )
)

print(f"Pages processed: {len(response.pages)}")
```

For more examples, see the [examples directory](./examples/) in the repository.

## More Info

* [More info on OpenInference and Phoenix](https://docs.arize.com/phoenix)
* [How to customize spans to track sessions, metadata, etc.](https://github.com/Arize-ai/openinference/tree/main/python/openinference-instrumentation#customizing-spans)
* [How to account for private information and span payload customization](https://github.com/Arize-ai/openinference/tree/main/python/openinference-instrumentation#tracing-configuration)
* [Mistral AI OCR Documentation](https://docs.mistral.ai/capabilities/OCR/basic_ocr/)
