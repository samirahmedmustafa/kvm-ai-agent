# kvm-ai-agent

To designate what model you want to use modify the config.yaml as below

provider: claude # ANTHROPIC_API_KEY in systemd service file below needs to be valid
or
provider: local # for local model

- web based access thru http://YOUR_IP:8000/

afterwards:

manual start command

```
  uvicorn main:app --reload --host 0.0.0.0
```

systemd service file

```
cat /etc/systemd/system/agent.service
[Unit]
Description=LangGraph FastAPI Agent
After=network.target

[Service]
Type=simple

User=ansible
Group=ansible

WorkingDirectory=/product/fastapi-app

Environment="PATH=/product/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="ANTHROPIC_API_KEY=anthropic-api-key"

ExecStart=/product/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target

```

