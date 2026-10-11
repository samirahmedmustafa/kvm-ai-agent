import subprocess
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from models import *
import paramiko
import json
import os
from pathlib import Path
from typing import Any

def append_inventory_entry(
    ansible_server: str = "192.168.1.10",
    template: str = "/product/ansible/playbook/inventories/templates/inventory.yaml.template",
    group: str = "",
    ansible_all_ipv4_addresses: str = "",
    static_ipv4_addresses: str = "",
    ansible_hostname: str = "",
    inventory: str = "",
    ssh_user: str = "ansible",
    ssh_key: str = "/home/ansible/.ssh/id_ed25519",
):
    """
    Generate an Ansible inventory file remotely on the Ansible server.

    The template is expected to contain uppercase placeholders:

        {{ GROUP }}
        {{ ANSIBLE_AUTO_IPV4_ADDRESSES }}
        {{ STATIC_IPV4_ADDRESSES }}
        {{ ANSIBLE_HOSTNAME }}

    Example:
        {{ GROUP }}:
            hosts:
              {{ ANSIBLE_HOSTNAME }}:
                ansible_host: {{ ANSIBLE_ALL_IPV4_ADDRESSES }}
            vars:
              static_ip_addresses: {{ STATIC_IPV4_ADDRESSES }}
              ports: []
              selinux_state: permissive
              pkgs:
                - wget
                - vim
              templates: []
    """

    if not group:
        raise ValueError("group is required")

    if not ansible_all_ipv4_addresses:
        raise ValueError("ansible_all_ipv4_addresses is required")

    if not static_ipv4_addresses:
        raise ValueError("static_ipv4_addresses is required")

    if not ansible_hostname:
        raise ValueError("ansible_hostname is required")

    if not inventory:
        raise ValueError("inventory is required")

    # Connect to the Ansible server
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=ansible_server,
            username=ssh_user,
            key_filename=ssh_key,
        )

        # Read the template remotely
        stdin, stdout, stderr = ssh.exec_command(
            f"cat '{template}'"
        )

        template_content = stdout.read().decode()

        error = stderr.read().decode()

        if error:
            raise RuntimeError(
                f"Unable to read inventory template: {error}"
            )

        # Replace template variables
        inventory_content = template_content.replace(
            "{{ GROUP }}",
            group,
        ).replace(
            "{{ ANSIBLE_ALL_IPV4_ADDRESSES }}",
            ansible_all_ipv4_addresses,
        ).replace(
            "{{ ANSIBLE_HOSTNAME }}",
            ansible_hostname,
        ).replace(
            "{{ STATIC_IPV4_ADDRESSES }}",
            static_ipv4_addresses,
        )

        # Write generated inventory remotely
        command = f"cat >> '{inventory}'"

        stdin, stdout, stderr = ssh.exec_command(command)

        stdin.write(inventory_content)
        stdin.close()

        exit_status = stdout.channel.recv_exit_status()

        error = stderr.read().decode()

        if exit_status != 0:
            raise RuntimeError(
                f"Unable to write inventory file: {error}"
            )

        return {
            "status": "success",
            "server": ansible_server,
            "template": template,
            "inventory": inventory,
            "group": group,
            "ansible_hostname": ansible_hostname,
            "ansible_all_ipv4_addresses": ansible_all_ipv4_addresses,
            "static_ipv4_addresses": static_ipv4_addresses,
        }

    finally:
        ssh.close() 

def get_vm_bridge_mac(vm: str):
    """Get the MAC address of a bridge-network interface for a VM.

    Args:
        vm: Name of the virtual machine.

    Returns:
        str: JSON containing the VM name and MAC address.
    """

    import json
    import subprocess
    import xml.etree.ElementTree as ET

    connection = "qemu+ssh://ansible@homeserver/system"

    command = [
        "virsh",
        "-c",
        connection,
        "dumpxml",
        vm,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        root = ET.fromstring(result.stdout)

        for interface in root.findall("./devices/interface"):
            if interface.get("type") != "bridge":
                continue

            mac = interface.find("mac")

            if mac is not None:
                address = mac.get("address")

                if address:
                    return json.dumps({
                        "vm": vm,
                        "mac": address,
                    })

        return json.dumps({
            "vm": vm,
            "mac": None,
        })

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Getting MAC address for VM '{vm}' timed out"
        ) from e

    except subprocess.CalledProcessError as e:
        error = e.stderr.strip() if e.stderr else str(e)

        raise RuntimeError(
            f"Failed to get MAC address for VM '{vm}': {error}"
        ) from e

    except ET.ParseError as e:
        raise RuntimeError(
            f"Failed to parse libvirt XML for VM '{vm}': {e}"
        ) from e

    except Exception as e:
        raise RuntimeError(
            f"Unable to get MAC address for VM '{vm}': {e}"
        ) from e

def destroy_vm(vm: str):
    """Destroy a VM definition while preserving its disks and directory.

    If the VM is running, it is forcibly destroyed first.
    The libvirt domain definition is then removed.
    The VM directory and disks are preserved.
    """

    import json
    import subprocess

    connection = "qemu+ssh://ansible@homeserver/system"

    try:
        # Check current state
        state_result = subprocess.run(
            [
                "virsh",
                "-c", connection,
                "domstate",
                vm,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        state = state_result.stdout.strip().lower()

        # Forcefully stop the VM if it is running
        if state == "running":
            subprocess.run(
                [
                    "virsh",
                    "-c", connection,
                    "destroy",
                    vm,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

        # Remove the VM definition, but preserve storage
        subprocess.run(
            [
                "virsh",
                "-c", connection,
                "undefine",
                vm,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return json.dumps({
            "status": "destroyed",
            "vm": vm,
            "storage_preserved": True,
            "directory": f"/product/VMs/{vm}",
        })

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Destroying VM '{vm}' timed out"
        ) from e

    except subprocess.CalledProcessError as e:
        error = e.stderr.strip() if e.stderr else str(e)

        raise RuntimeError(
            f"Failed to destroy VM '{vm}': {error}"
        ) from e

    except Exception as e:
        raise RuntimeError(
            f"Unable to destroy VM '{vm}': {e}"
        ) from e


def delete_vm(vm: str):
    """Delete a VM, its libvirt definition, disks, and VM directory."""

    import json
    import subprocess

    connection = "qemu+ssh://ansible@homeserver/system"
    vm_directory = f"/product/VMs/{vm}"

    try:
        # Check current state
        state_result = subprocess.run(
            [
                "virsh",
                "-c", connection,
                "domstate",
                vm,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        state = state_result.stdout.strip().lower()

        # Forcefully stop the VM if it is running
        if state == "running":
            subprocess.run(
                [
                    "virsh",
                    "-c", connection,
                    "destroy",
                    vm,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

        # Remove the libvirt domain definition.
        #
        # --remove-all-storage is intentionally NOT used because
        # the disks are removed separately below.
        subprocess.run(
            [
                "virsh",
                "-c", connection,
                "undefine",
                vm,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        # Remove the VM directory and everything inside it
        subprocess.run(
            [
                "ssh",
                "ansible@homeserver",
                "rm",
                "-rf",
                "--",
                vm_directory,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return json.dumps({
            "status": "deleted",
            "vm": vm,
            "storage_removed": True,
            "directory": vm_directory,
        })

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Deleting VM '{vm}' timed out"
        ) from e

    except subprocess.CalledProcessError as e:
        error = e.stderr.strip() if e.stderr else str(e)

        raise RuntimeError(
            f"Failed to delete VM '{vm}': {error}"
        ) from e

    except Exception as e:
        raise RuntimeError(
            f"Unable to delete VM '{vm}': {e}"
        ) from e

def create_remote_directory(path: str):
    """Create a directory on the remote KVM host.

    Args:
        path: Absolute path of the directory to create.

    Returns:
        str: JSON describing the result.
    """

    import json
    import subprocess

    host = "ansible@homeserver"

    command = [
        "ssh",
        host,
        "mkdir",
        "-p",
        path,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        return json.dumps({
            "status": "created",
            "host": "homeserver",
            "path": path,
            "message": result.stdout.strip(),
        })

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Creating remote directory '{path}' timed out "
            "after 15 seconds"
        ) from e

    except subprocess.CalledProcessError as e:
        error = e.stderr.strip() if e.stderr else str(e)

        raise RuntimeError(
            f"Failed to create remote directory '{path}': {error}"
        ) from e

    except Exception as e:
        raise RuntimeError(
            f"Unable to create remote directory '{path}': {e}"
        ) from e

def start_vm(vm: str):
    """Start a KVM/libvirt virtual machine.

    Args:
        vm: Name of the virtual machine.

    Returns:
        str: JSON result describing the operation.
    """

    import json
    import subprocess

    connection = "qemu+ssh://ansible@homeserver/system"

    command = [
        "virsh",
        "-c",
        connection,
        "start",
        vm,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return json.dumps({
            "status": "started",
            "vm": vm,
            "message": result.stdout.strip(),
        })

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Starting VM '{vm}' timed out after 30 seconds"
        ) from e

    except subprocess.CalledProcessError as e:
        error = e.stderr.strip() if e.stderr else str(e)

        raise RuntimeError(
            f"Failed to start VM '{vm}': {error}"
        ) from e

    except Exception as e:
        raise RuntimeError(
            f"Unable to start VM '{vm}': {e}"
        ) from e


def shutdown_vm(vm: str):
    """Gracefully shut down a KVM/libvirt virtual machine.

    Args:
        vm: Name of the virtual machine.

    Returns:
        str: JSON result describing the operation.
    """

    import json
    import subprocess

    connection = "qemu+ssh://ansible@homeserver/system"

    command = [
        "virsh",
        "-c",
        connection,
        "shutdown",
        vm,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return json.dumps({
            "status": "shutdown_requested",
            "vm": vm,
            "message": result.stdout.strip(),
        })

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Shutting down VM '{vm}' timed out after 30 seconds"
        ) from e

    except subprocess.CalledProcessError as e:
        error = e.stderr.strip() if e.stderr else str(e)

        raise RuntimeError(
            f"Failed to shutdown VM '{vm}': {error}"
        ) from e

    except Exception as e:
        raise RuntimeError(
            f"Unable to shutdown VM '{vm}': {e}"
        ) from e


def get_vm(vm: str):
    """Get information about a KVM/libvirt virtual machine.

    Args:
        vm: Name of the virtual machine.

    Returns:
        str: JSON containing VM state and IPv4 address.
    """

    import json
    import subprocess

    connection = "qemu+ssh://ansible@homeserver/system"

    try:
        # Get VM state first
        state_result = subprocess.run(
            [
                "virsh",
                "-c", connection,
                "domstate",
                vm,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        state = state_result.stdout.strip()
        ipv4 = None

        # domifaddr only works when the VM is running
        if state.lower() == "running":
            try:
                addr_result = subprocess.run(
                    [
                        "virsh",
                        "-c", connection,
                        "domifaddr",
                        vm,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )

                for line in addr_result.stdout.splitlines():
                    line = line.strip()

                    if "ipv4" not in line.lower():
                        continue

                    for field in line.split():
                        if "/" not in field:
                            continue

                        address = field.split("/")[0]
                        parts = address.split(".")

                        if len(parts) != 4:
                            continue

                        try:
                            if all(
                                0 <= int(part) <= 255
                                for part in parts
                            ):
                                ipv4 = address
                                break
                        except ValueError:
                            continue

                    if ipv4:
                        break

            except subprocess.CalledProcessError:
                # VM is running but an IP address could not be obtained.
                ipv4 = None

        return json.dumps({
            "vm": vm,
            "state": state,
            "ipv4": ipv4,
        })

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Getting information for VM '{vm}' timed out"
        ) from e

    except subprocess.CalledProcessError as e:
        error = e.stderr.strip() if e.stderr else str(e)

        raise RuntimeError(
            f"Failed to get information for VM '{vm}': {error}"
        ) from e

    except Exception as e:
        raise RuntimeError(
            f"Unable to get information for VM '{vm}': {e}"
        ) from e

def create_vm_from_template(vm: str, template: str = "almalinux10-template"):
    """
    Create a VM from a template in KVM/libvirt. Then start the VM
    Args:
        vm: virtual machine name
        template: template name to clone vm from
    Output:
        The IP address of the newly created VM
    """

    import json
    import subprocess

    create_remote_directory(f"/product/VMs/{vm}")

    connection = "qemu+ssh://ansible@homeserver/system"
    virt_clone = "/usr/bin/virt-clone"

    command = [
        virt_clone,
        "--connect", connection,
        "--original", template,
        "--name", vm,
        "--auto-clone",
        "--file", f"/product/VMs/{vm}/disk1.qcow2",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )

        return json.dumps({
            "status": "created",
            "vm": vm,
            "template": template,
            "message": result.stdout.strip(),
        })

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Creating VM '{vm}' from template '{template}' "
            "timed out after 60 seconds"
        ) from e

    except subprocess.CalledProcessError as e:
        error = e.stderr.strip() if e.stderr else str(e)

        raise RuntimeError(
            f"Failed to create VM '{vm}' from template '{template}': "
            f"{error}"
        ) from e

    except Exception as e:
        raise RuntimeError(
            f"Unable to create VM '{vm}' from template '{template}': "
            f"{e}"
        ) from e

    start_vm(vm)

def get_vms():
    """Run virsh list --all and return the result as JSON."""

    import json

    command = [
        "virsh",
        "-c",
        "qemu+ssh://ansible@homeserver/system",
        "list",
        "--all",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        vms = []

        for line in result.stdout.splitlines():

            line = line.strip()

            # Skip empty lines, header, and separator.
            if (
                not line
                or line.startswith("Id")
                or line.startswith("---")
            ):
                continue

            parts = line.split()

            if len(parts) < 3:
                continue

            vm_id = parts[0]
            vm_name = parts[1]
            state = " ".join(parts[2:])

            vms.append({
                "id": vm_id,
                "name": vm_name,
                "state": state,
            })

        return json.dumps(
            {
                "vms": vms
            },
            indent=2,
        )

    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "virsh command timed out"
        })

    except subprocess.CalledProcessError as e:
        return json.dumps({
            "error": e.stderr.strip()
        })

    except Exception as e:
        return json.dumps({
            "error": str(e)
        })

def get_vm_ip(vm: str) -> str:
    """get the IP address of the VM from the KVM/libvirt server.
    Args:
        vm: virtual machine name
    Output:
        list of VMs and their respective IPs, MACs, NAMES
    """
    print(vm)
    res = subprocess.run("virsh -c qemu+ssh://ansible@homeserver/system domifaddr {}".format(vm),
                         shell=True,
                         capture_output=True,
                         text=True,)
    return res.stdout

#--------------------------------------------------------------------
# loading properties from config.json|config.yaml|config.properties
#--------------------------------------------------------------------
def load_properties(path: Path) -> dict[str, Any]:
    """Read Java-style properties and convert them to nested settings."""
    config = {}

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith(("#", "!")):
                continue

            key, separator, value = line.partition("=")

            if not separator:
                raise ValueError(f"Invalid properties entry: {line}")

            parts = key.strip().split(".")
            current = config

            for part in parts[:-1]:
                current = current.setdefault(part, {})

            value = value.strip()
            leaf = parts[-1]

            # Convert numeric configuration values to integers.
            if leaf in ("timeout", "max_retries"):
                value = int(value)

            current[leaf] = value

    return config


def load_config(filename: str) -> dict[str, Any]:
    path = Path(filename)

    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".yaml" or suffix == ".yml":
        import yaml

        with path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)

    elif suffix == ".properties":
        config = load_properties(path)

    else:
        raise ValueError(
            "Unsupported configuration format. "
            "Use .yaml, .yml, .json, or .properties."
        )

    if not isinstance(config, dict):
        raise ValueError("Configuration must contain a mapping/object.")

    print("config: ", config)
    return config


def create_model(config: dict[str, Any]):
    provider = config.get("provider", "").lower()

    if provider == "local":
        settings = config.get("local", {})
        print("get_local_model :", get_local_model(**settings))
        return get_local_model(**settings)

    if provider == "claude":
        settings = config.get("claude", {})

        # API key must be supplied through ANTHROPIC_API_KEY.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise EnvironmentError(
                "Set the ANTHROPIC_API_KEY environment variable."
            )

        return get_claude_model(**settings)

    raise ValueError(
        f"Unsupported provider: {provider!r}. "
        "Expected 'local' or 'claude'."
    )

# -------------------------------------------------------------------
# Tools
# -------------------------------------------------------------------

tools = [
    append_inventory_entry,
    get_vm_bridge_mac,
    delete_vm,
    destroy_vm,
    create_vm_from_template,
    start_vm,
    shutdown_vm,
    get_vm,
    get_vms,
    get_vm_ip,
]

def get_tools() -> list[str]:
    return [
    "append_inventory_entry()",
    "get_vm_bridge_mac()",
    "delete_vm()",
    "destroy_vm()",
    "create_vm_from_template()",
    "start_vm()",
    "shutdown_vm()",
    "get_vm()",
    "get_vms()",
    "get_vm_ip()",
    ]

#model = get_local_model(timeout = 300)
##model = get_claude_model(timeout = 300)
#
#model_with_tools = model.bind_tools(
#    tools,
#    parallel_tool_calls=False,
#)


# -------------------------------------------------------------------
# System prompt
# -------------------------------------------------------------------

sys_msg = SystemMessage(
    content="""
You are a helpful infrastructure assistant that manages and
inspects a KVM/libvirt environment.

You have access to tools that allow you to query virtual machines.

GENERAL RULES:

1. Always use the available tools when the user asks for information
   about the KVM/libvirt environment.

2. Never invent VM names, VM states, IP addresses, MAC addresses,
   or other infrastructure information.

3. Complete all necessary tool calls before producing the final answer.

4. Never expose:
   - tool calls
   - tool names
   - tool arguments
   - tool results
   - internal message objects
   - IDs
   - signatures
   - internal reasoning
   - intermediate processing

5. Return only the final response intended for the user.

6. Do not repeat the user's question.

7. Keep the response concise and easy to read.

VM RULES:

- Use get_vms() to obtain the list of virtual machines.

- If the user asks for VM IP addresses:
    1. First call get_vms().
    2. Identify the running VMs.
    3. Call get_vm_ip() for each running VM.
    4. Do not call get_vm_ip() for shut-off VMs.
    5. Combine the information into one final response.

FORMATTING RULES:

Return the final answer using Markdown.

When displaying a table:

- Put a blank line before the table.
- Put the table on its own lines.
- Put every table row on its own line.
- Use a Markdown header separator row.
- Use actual newline characters.
- Do not put the entire table on one line.
- Do not put explanatory text on the same line as the table.

Example:

There are 3 running VMs.

| VM Name | State | IPv4 Address |
|---------|-------|--------------|
| agent   | running | 192.168.122.133 |
| ansible | running | 192.168.122.26 |
| helper  | running | 192.168.122.172 |

Do not return the table like this:

| VM Name | State | IPv4 Address | |---------|-------|--------------| | agent | running | 192.168.122.133 |

Always use properly formatted Markdown.
"""
)

def assistant(state: MessagesState):
    print("\n===== MESSAGES SENT TO CLAUDE =====")

    for i, message in enumerate(state["messages"]):
        print(f"\n--- MESSAGE {i} ---")
        print("TYPE:", type(message).__name__)
        print("CONTENT:", repr(message.content))

        if hasattr(message, "tool_calls"):
            print("TOOL CALLS:", message.tool_calls)

        if hasattr(message, "tool_call_id"):
            print("TOOL CALL ID:", message.tool_call_id)

    print("===================================\n")

    return {
        "messages": [
            model_with_tools.invoke(
                [sys_msg] + state["messages"]
            )
        ]
    }

# -------------------------------------------------------------------
# LangGraph
# -------------------------------------------------------------------

#parser = argparse.ArgumentParser(
#    description="Initialize a chat model from a configuration file."
#)
#parser.add_argument(
#    "--config",
#    default="config.yaml",
#    help="Path to config.yaml, config.json, or config.properties",
#)
#args = parser.parse_args()

#config = load_config(args.config)
config = load_config("config.yaml")
model = create_model(config)
model_with_tools = model.bind_tools(
    tools,
    parallel_tool_calls=False,
)

print(f"Initialized provider: {config['provider']}")

tool_node = ToolNode(tools)

memory = MemorySaver()

builder = StateGraph(MessagesState)

builder.add_node("assistant", assistant)
builder.add_node("tools", tool_node)

builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant",
    tools_condition,
)

builder.add_edge(
    "tools",
    "assistant",
)

react_graph = builder.compile(
    checkpointer=memory
)
