def get_local_model(
    model: str = "gpt-oss:20b",
    ip: str = "192.168.1.100",
    port: str = "8008",
    timeout: int = 120,
    max_retries: int = 2,
):
    from langchain_openai import ChatOpenAI

    print(f"URL: http://{ip}:{port}/v1")
    return ChatOpenAI(
        model=model,
        base_url=f"http://{ip}:{port}/v1",
        api_key="not-needed",
        timeout=timeout,
        max_retries=max_retries,
        temperature=0,
    )


def get_claude_model(
    model: str = "claude-opus-5-5",
    ip: str = None,
    port: str = None,
    timeout: int = 120,
    max_retries: int = 2,
):
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model,
        timeout=timeout,
        max_retries=max_retries,
    )

#def get_local_model(model: str = "gpt-oss:20b", ip: str = "192.168.1.100", port: str = "8008", timeout: int = 120, max_retries: int = 2):
#  from langchain_openai import ChatOpenAI
#  model = ChatOpenAI(
#      model="{}".format(model),                    # must match an ID from /v1/models
#      base_url="http://{}:{}/v1".format(ip, port),
#      api_key="not-needed",                   # placeholder; most local servers ignore it
#      timeout=timeout,
#      temperature=0,
#  )
#
#  print(f"local model: {model}")
#
#  return model
#
## requiredment: export ANTHROPIC_API_KEY="your claude api key"
#def get_claude_model(model: str = "claude-opus-5-5", ip: str = None, port: str = None, timeout: int = 120, max_retries: int = 2):
#  from langchain_anthropic import ChatAnthropic
#  model = ChatAnthropic(
#      model         = "claude-opus-5-5",
#      timeout       = timeout,
#      max_retries   = max_retries,
#  )
#  return model

