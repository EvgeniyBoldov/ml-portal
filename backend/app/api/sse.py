from starlette.responses import StreamingResponse
def sse_response(source):
    def gen():
        for item in source:
            yield (item.get("data","") + "\n\n")
    return StreamingResponse(gen(), media_type="text/event-stream")
