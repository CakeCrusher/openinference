from mistralai import Mistral
from mistralai.models.responseformat import ResponseFormat
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from openinference.instrumentation import using_attributes
from openinference.instrumentation.mistralai import MistralAIInstrumentor

tracer_provider = trace_sdk.TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

MistralAIInstrumentor().instrument(tracer_provider=tracer_provider)


if __name__ == "__main__":
    client = Mistral(api_key="your-api-key-here")
    with using_attributes(
        session_id="my-ocr-test-session",
        user_id="my-ocr-test-user",
        metadata={
            "document_type": "pdf",
            "test-int": 1,
            "test-str": "string",
        },
        tags=["ocr", "document-processing"],
    ):
        # Example with a document URL
        document = {
            "url": "https://example.com/sample.pdf",  # Replace with actual URL to PDF
        }

        # Define annotation formats for bounding boxes and full document
        bbox_format = ResponseFormat(
            type="json_schema", 
            schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "confidence": {"type": "number"},
                }
            }
        )
        
        document_format = ResponseFormat(
            type="json_schema",
            schema={
                "type": "object",
                "properties": {
                    "document_type": {"type": "string"},
                    "title": {"type": "string"},
                    "author": {"type": "string"},
                    "summary": {"type": "string"},
                }
            }
        )
        
        # Process the document
        try:
            response = client.ocr.process(
                model="mistral-large-latest",  # Use OCR-capable model
                document=document,
                pages=[0, 1],  # Process first two pages
                bbox_annotation_format=bbox_format,
                document_annotation_format=document_format,
            )
            
            print(f"Model used: {response.model}")
            print(f"Pages processed: {len(response.pages)}")
            
            # Print the markdown content from the first page
            if response.pages:
                print(f"\nFirst page content:\n{response.pages[0].markdown[:300]}...")
                
            # Print document annotation if available
            if hasattr(response, "document_annotation") and response.document_annotation:
                print(f"\nDocument annotation: {response.document_annotation}")
                
        except Exception as e:
            print(f"Error processing document: {e}")