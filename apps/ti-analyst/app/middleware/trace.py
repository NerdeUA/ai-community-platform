import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_trace_id = request.headers.get("x-trace-id")
        trace_id = incoming_trace_id if incoming_trace_id else str(uuid.uuid4())
        req_id = str(uuid.uuid4())

        trace_id_var.set(trace_id)
        request_id_var.set(req_id)

        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Request-Id"] = req_id

        return response
