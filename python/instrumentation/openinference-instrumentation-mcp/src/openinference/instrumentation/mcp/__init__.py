from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Collection, Tuple, cast

from opentelemetry import context, propagate
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  # type: ignore
from opentelemetry.instrumentation.utils import unwrap
from wrapt import ObjectProxy, register_post_import_hook, wrap_function_wrapper

from openinference.instrumentation.mcp.package import _instruments


import logging
# create a logger that saves the logs to a file
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler("mcp.log")
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


class MCPInstrumentor(BaseInstrumentor):  # type: ignore
    """
    An instrumenter for MCP.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        logger.debug("INSIDE MCP INSTRUMENT")
        logger.debug(f"Registering post-import hook for mcp.client.sse")

        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.client.sse", "sse_client", self._transport_wrapper
            ),
            "mcp.client.sse",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.sse", "SseServerTransport.connect_sse", self._transport_wrapper
            ),
            "mcp.server.sse",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.client.stdio", "stdio_client", self._transport_wrapper
            ),
            "mcp.client.stdio",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.stdio", "stdio_server", self._transport_wrapper
            ),
            "mcp.server.stdio",
        )

        # While we prefer to instrument the lowest level primitive, the transports above, it doesn't
        # mean context will be propagated to handlers automatically. Notably, the MCP SDK passes
        # server messages to a handler with a separate stream in between, losing context. We go
        # ahead and instrument this second stream just to propagate context so transports can still
        # be used independently while also supporting the major usage of the MCP SDK. Notably, this
        # may be a reasonable generic instrumentation for anyio itself to allow its streams to
        # propagate context broadly.
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.session", "ServerSession.__init__", self._base_session_init_wrapper
            ),
            "mcp.server.session",
        )

        # import sys
        # for module_name, func_name in [
        #     ("mcp.client.sse", "sse_client"),
        #     ("mcp.server.sse", "SseServerTransport.connect_sse"),
        #     ("mcp.client.stdio", "stdio_client"),
        #     ("mcp.server.stdio", "stdio_server")
        # ]:
        #     if module_name in sys.modules:
        #         logger.debug(f"Direct patching {module_name}.{func_name}")
        #         try:
        #             wrap_function_wrapper(
        #                 module_name, func_name, self._transport_wrapper
        #             )
        #             logger.debug(f"Successfully patched {module_name}.{func_name}")
        #         except Exception as e:
        #             logger.error(f"Failed to patch {module_name}.{func_name}: {e}")

        # # Try to instrument agents.mcp as well
        # try:
        #     logger.debug("Attempting to instrument agents.mcp")
        #     import agents.mcp
        #     if hasattr(agents.mcp, "MCPServerStdio"):
        #         logger.debug("Found MCPServerStdio in agents.mcp")
        #         # Check what transport it uses
        #         for attr_name in dir(agents.mcp.MCPServerStdio):
        #             if "transport" in attr_name.lower() or "stdio" in attr_name.lower():
        #                 logger.debug(f"Found potential transport attribute: {attr_name}")
        # except ImportError:
        #     logger.debug("Could not import agents.mcp")


        # try:
        #     logger.debug("Attempting to instrument agents.mcp")
        #     import agents.mcp.server
            
        #     # Patch MCPServerStdio.__aenter__
        #     wrap_function_wrapper(
        #         "agents.mcp.server", "MCPServerStdio.__aenter__", 
        #         self._agents_mcp_aenter_wrapper
        #     )
        #     logger.debug("Successfully patched agents.mcp.server.MCPServerStdio.__aenter__")
            
        #     # Check for _MCPServerWithClientSession as well
        #     if hasattr(agents.mcp.server, "_MCPServerWithClientSession"):
        #         wrap_function_wrapper(
        #             "agents.mcp.server", "_MCPServerWithClientSession.__aenter__", 
        #             self._agents_mcp_aenter_wrapper
        #         )
        #         logger.debug("Successfully patched agents.mcp.server._MCPServerWithClientSession.__aenter__")
            
        # except ImportError:
        #     logger.debug("Could not import agents.mcp")
        # except Exception as e:
        #     logger.error(f"Error instrumenting agents.mcp: {e}")
        

    def _uninstrument(self, **kwargs: Any) -> None:
        unwrap("mcp.client.stdio", "stdio_client")
        unwrap("mcp.server.stdio", "stdio_server")

    @asynccontextmanager
    async def _transport_wrapper(
        self, wrapped: Callable[..., Any], instance: Any, args: Any, kwargs: Any
    ) -> AsyncGenerator[Tuple["InstrumentedStreamReader", "InstrumentedStreamWriter"], None]:
        logger.debug("INSIDE TRANSPORT WRAPPER")
        async with wrapped(*args, **kwargs) as (read_stream, write_stream):
            yield InstrumentedStreamReader(read_stream), InstrumentedStreamWriter(write_stream)

    def _base_session_init_wrapper(
        self, wrapped: Callable[..., None], instance: Any, args: Any, kwargs: Any
    ) -> None:
        logger.debug("INSIDE BASE SESSION INIT WRAPPER")
        wrapped(*args, **kwargs)
        reader = getattr(instance, "_incoming_message_stream_reader", None)
        writer = getattr(instance, "_incoming_message_stream_writer", None)
        if reader and writer:
            setattr(
                instance, "_incoming_message_stream_reader", ContextAttachingStreamReader(reader)
            )
            setattr(instance, "_incoming_message_stream_writer", ContextSavingStreamWriter(writer))


class InstrumentedStreamReader(ObjectProxy):  # type: ignore
    # ObjectProxy missing context manager - https://github.com/GrahamDumpleton/wrapt/issues/73
    async def __aenter__(self) -> Any:
        return await self.__wrapped__.__aenter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return await self.__wrapped__.__aexit__(exc_type, exc_value, traceback)

    async def __aiter__(self) -> AsyncGenerator[Any, None]:
        from mcp.types import JSONRPCMessage, JSONRPCRequest

        async for item in self.__wrapped__:
            request = cast(JSONRPCMessage, item).root

            if not isinstance(request, JSONRPCRequest):
                yield item
                continue

            if request.params:
                meta = request.params.get("_meta")
                if meta:
                    ctx = propagate.extract(meta)
                    restore = context.attach(ctx)
                    try:
                        yield item
                        continue
                    finally:
                        context.detach(restore)
            yield item


class InstrumentedStreamWriter(ObjectProxy):  # type: ignore
    # ObjectProxy missing context manager - https://github.com/GrahamDumpleton/wrapt/issues/73
    async def __aenter__(self) -> Any:
        return await self.__wrapped__.__aenter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return await self.__wrapped__.__aexit__(exc_type, exc_value, traceback)

    async def send(self, item: Any) -> Any:
        logger.debug("INSIDE INSTRUMENTED STREAM WRITER")
        
        # First check the type of item
        item_type = type(item).__name__
        logger.debug(f"Message type: {item_type}")
        
        # Handle different message types
        if hasattr(item, "root"):
            # Original JSONRPCMessage case
            from mcp.types import JSONRPCMessage, JSONRPCRequest
            
            request = cast(JSONRPCMessage, item).root
            if not isinstance(request, JSONRPCRequest):
                return await self.__wrapped__.send(item)
            meta = None
            if not request.params:
                request.params = {}
            meta = request.params.setdefault("_meta", {})
            propagate.get_global_textmap().inject(meta)
        elif hasattr(item, "params") and isinstance(item.params, dict):
            # For SessionMessage or other similar types
            logger.debug("Processing message with params attribute")
            if not hasattr(item.params, "_meta"):
                item.params["_meta"] = {}
            propagate.get_global_textmap().inject(item.params["_meta"])
        elif hasattr(item, "__dict__"):
            # Generic fallback for other object types
            logger.debug(f"Unknown message type with attributes: {dir(item)}")
            if not hasattr(item, "_meta"):
                setattr(item, "_meta", {})
            propagate.get_global_textmap().inject(item._meta)
        
        return await self.__wrapped__.send(item)


@dataclass(slots=True, frozen=True)
class ItemWithContext:
    item: Any
    ctx: context.Context


class ContextSavingStreamWriter(ObjectProxy):  # type: ignore
    # ObjectProxy missing context manager - https://github.com/GrahamDumpleton/wrapt/issues/73
    async def __aenter__(self) -> Any:
        return await self.__wrapped__.__aenter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return await self.__wrapped__.__aexit__(exc_type, exc_value, traceback)

    async def send(self, item: Any) -> Any:
        ctx = context.get_current()
        return await self.__wrapped__.send(ItemWithContext(item, ctx))


class ContextAttachingStreamReader(ObjectProxy):  # type: ignore
    # ObjectProxy missing context manager - https://github.com/GrahamDumpleton/wrapt/issues/73
    async def __aenter__(self) -> Any:
        return await self.__wrapped__.__aenter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return await self.__wrapped__.__aexit__(exc_type, exc_value, traceback)

    async def __aiter__(self) -> AsyncGenerator[Any, None]:
        from mcp.types import JSONRPCMessage, JSONRPCRequest

        async for item in self.__wrapped__:
            item_type = type(item).__name__
            logger.debug(f"Received message type: {item_type}")
            
            # For JSONRPCMessage type
            if hasattr(item, "root"):
                request = cast(JSONRPCMessage, item).root
                
                if not isinstance(request, JSONRPCRequest):
                    yield item
                    continue

                if request.params:
                    meta = request.params.get("_meta")
                    if meta:
                        ctx = propagate.extract(meta)
                        restore = context.attach(ctx)
                        try:
                            yield item
                            continue
                        finally:
                            context.detach(restore)
            # For SessionMessage or similar types
            elif hasattr(item, "params") and isinstance(item.params, dict):
                logger.debug("Processing received message with params attribute")
                meta = item.params.get("_meta")
                if meta:
                    ctx = propagate.extract(meta)
                    restore = context.attach(ctx)
                    try:
                        yield item
                        continue
                    finally:
                        context.detach(restore)
            # For other types, just pass through
            yield item
