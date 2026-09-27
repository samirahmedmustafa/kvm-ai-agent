import subprocess
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

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

# -------------------------------------------------------------------
# Tools
# -------------------------------------------------------------------

tools = [
    delete_vm,
    destroy_vm,
    create_vm_from_template,
    start_vm,
    shutdown_vm,
    get_vm,
    get_vms,
    get_vm_ip,
]


# -------------------------------------------------------------------
# Claude model
# -------------------------------------------------------------------

model = ChatAnthropic(
    model="claude-opus-5-5",
    timeout=30,
    max_retries=2,
)

model_with_tools = model.bind_tools(
    tools,
    parallel_tool_calls=False,
)


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

#def assistant(state: MessagesState):
#    """Invoke Claude with the current conversation state."""
#    return { "messages": [ model_with_tools.invoke( [sys_msg] + state["messages"] ) ] }

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

#thread_id = str(uuid.uuid4())
# Conversation configuration
config = {
    "configurable": {
        "thread_id": 1
    }
}
