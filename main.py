import markdown
import uuid
import asyncio
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from langchain_core.messages import HumanMessage

from model_with_memory import react_graph, config, get_tools

app = FastAPI()

templates = Jinja2Templates(directory="templates")

from langchain_core.messages import AIMessage


async def process_text(text: str):
    thread_id = str(uuid.uuid4())
    # Conversation configuration
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    messages = [
        HumanMessage(content=text)
    ]

    result = await asyncio.to_thread(
        react_graph.invoke,
        {"messages": messages},
        config,
    )

    for message in reversed(result["messages"]):

        if isinstance(message, AIMessage):

            content = message.content

            print("\n==============================")
            print("AI MESSAGE CONTENT TYPE:")
            print(type(content))

            print("\nAI MESSAGE CONTENT repr():")
            print(repr(content))

            print("\nAI MESSAGE CONTENT:")
            print(content)

            print("==============================\n")

            if isinstance(content, str):
                return content

            if isinstance(content, list):

                text_parts = []

                for block in content:

                    if isinstance(block, dict):

                        if block.get("type") == "text":
                            text_parts.append(
                                block.get("text", "")
                            )

                    elif isinstance(block, str):
                        text_parts.append(block)

                final_text = "\n".join(text_parts)

                print("\n==============================")
                print("FINAL TEXT repr():")
                print(repr(final_text))
                print("==============================\n")

                return final_text

    return "No response from assistant."

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tools = get_tools()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"result": "", "tools": tools},
    )

@app.get("/example", response_class=HTMLResponse)
async def example(request: Request):
    # Example tools – replace with your real list
    #tools = get_tools()
    return templates.TemplateResponse(
        request=request,
        name="example.html",
        context={"result": "", "tools": []},
    )

@app.post("/", response_class=HTMLResponse)
async def submit(request: Request, text: str = Form(...)):
    timeout = 3000.0
    try:
        result = await asyncio.wait_for(
            process_text(text),
            timeout = timeout,
        )

        result_html = markdown.markdown(
            result,
            extensions=[
                "tables",
                "fenced_code",
            ],
        )

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="The request timed out after {} seconds.".format(timeout)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {e}"
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "result": result_html,
        },
    )
