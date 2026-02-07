import sys
import os
import shutil
import re
import logging
from typing import List, Tuple, Optional
from mcp.server.fastmcp import FastMCP
import subprocess

# --- 1. System Configuration & Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("CoderAIAllocator")

mcp = FastMCP("Coder AI Allocator v1.2 (Strict Security)")
my_env = os.environ.copy()

# --- 2. CLI Command Configuration ---
CLI_CONFIG = {
    "codex": {
        "exec": ["codex", "exec"],       
        "health": ["codex", "--version"], 
    },
    "gemini": {
        "exec": ["gemini"],              
        "health": ["gemini", "--version"], 
    },
    "ollama": {
        "exec": ["ollama", "run"],       
        "health": ["ollama", "--version"],
    }
}

# --- 3. Helper Functions ---
def clean_markdown_fences(content: str) -> str:
    pattern = r"^```[a-zA-Z]*\n([\s\S]*?)\n```$"
    match = re.match(pattern, content.strip())
    if match:
        return match.group(1)
    return content

def save_to_file(content: str, path: str) -> str:
    try:
        full_path = os.path.abspath(os.path.expanduser(path))
        # [SECURITY] Prevent saving to system paths
        if full_path.startswith(("/etc", "/var", "/usr", "/bin", "/sbin", "/root")):
            return f"[SECURITY ERROR] Writing to system path '{path}' is forbidden."
        
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        clean_content = clean_markdown_fences(content)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(clean_content)
        return f"[FILE SAVED] Successfully saved to: {path}\n(Markdown fences removed automatically)"
    except Exception as e:
        return f"[FILE ERROR] Failed to save: {str(e)}"

# --- 4. Security Middleware (v1.2 Enhanced) ---
class SecuritySanitizer:
    
    BLOCK_PATTERNS = [
        r"rm\s+(-r[a-zA-Z]*f|-f[a-zA-Z]*r)\s+",
        r"mkfs\.",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&",
        r"dd\s+if=",
        r"chmod\s+777",
    ]

    # Block reading/writing to these paths GLOBALLY
    SENSITIVE_PATHS = [
        r"/etc/", r"/var/", r"/boot/", r"/proc/", r"/root/"
    ]

    @staticmethod
    def inspect(prompt: str, mode: str = "execution") -> Tuple[bool, str]:
        # 1. Block malicious command patterns
        for pattern in SecuritySanitizer.BLOCK_PATTERNS:
            if re.search(pattern, prompt):
                return False, f"[SECURITY BLOCK] Destructive command pattern detected ({pattern}). Execution blocked."

        # 2. Block sensitive path access (REGARDLESS of mode)
        # We removed 'if mode == execution' check. Now it applies to 'analysis' too.
        for path in SecuritySanitizer.SENSITIVE_PATHS:
            if path in prompt:
                logger.warning(f"Sensitive Path Access Blocked: {path}")
                return False, f"[SECURITY BLOCK] Access to critical system path '{path}' is strictly FORBIDDEN."
        
        return True, ""

# --- 5. Execution Logic ---
def run_cli_command(service_name: str, args: List[str], input_text: str) -> Tuple[bool, str]:
    config = CLI_CONFIG.get(service_name, {})
    cmd_base = config.get("exec")
    if not cmd_base or not shutil.which(cmd_base[0]):
        return False, f"System Error: Command '{cmd_base[0]}' not found."

    system_suffix = "\n\n[SYSTEM INSTRUCTION: Return raw code/text only. Do NOT use emojis. Do NOT use markdown code blocks.]"
    full_cmd = cmd_base + args + [input_text + system_suffix]
    
    try:
        logger.info(f"Executing {service_name}...")
        result = subprocess.run(full_cmd, capture_output=True, text=True, env=my_env, check=False)
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)

def get_health_report():
    report = "\n\n--- CLI Health Check ---\n"
    for tool_name in ["codex", "gemini", "ollama"]:
        cmd = CLI_CONFIG[tool_name].get("health")
        if cmd and shutil.which(cmd[0]):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, env=my_env, check=False)
                report += f"[{tool_name.capitalize()}]: {'Online' if res.returncode == 0 else 'Error'}\n"
            except:
                report += f"[{tool_name.capitalize()}]: Unreachable\n"
    return report

def format_response(content: str, routing: List[str]) -> str:
    return f"{content}\n\n--- [Routing Log] ---\n" + "\n".join(routing)

def format_error(routing: List[str], msg: str) -> str:
    return f"[Task Execution Failed]\n{msg}{get_health_report()}\n\n--- [Routing Log] ---\n" + "\n".join(routing)

def execute_with_failover(primary: str, secondary: str, prompt: str, mode: str, save_path: Optional[str] = None, force_primary: bool = False) -> str:
    is_safe, sec_msg = SecuritySanitizer.inspect(prompt, mode=mode)
    if not is_safe: return sec_msg

    routing_log = []
    
    def handle_success(source: str, content: str, log: List[str]) -> str:
        log.append(f"    [SUCCESS]")
        if save_path:
            return format_response(f"{save_to_file(content, save_path)}\n(Source: {source})", log)
        return format_response(content, log)

    # Primary
    routing_log.append(f"[1] Primary ({primary}): Trying...")
    success, output = run_cli_command(primary, [], prompt)
    if success: return handle_success(primary, output, routing_log)
    
    routing_log.append(f"    [FAILED]")
    if force_primary: return format_error(routing_log, f"Forced Primary ({primary}) failed.\nError: {output}")

    # Secondary
    logger.warning(f"Failover: {primary} -> {secondary}")
    routing_log.append(f"[2] Secondary ({secondary}): Trying...")
    failover_prompt = f"[Context: {primary} failed] {prompt}"
    success, output = run_cli_command(secondary, [], failover_prompt)
    if success: return handle_success(secondary, output, routing_log)
    
    routing_log.append(f"    [FAILED]")
    
    # Tertiary
    if primary != "ollama":
        logger.warning(f"Failover: {secondary} -> Ollama")
        routing_log.append(f"[3] Ollama: Trying...")
        success, output = run_cli_command("ollama", ["qwen3-coder:30b-a3b-q8_0"], failover_prompt)
        if success: return handle_success("Ollama", output, routing_log)
        routing_log.append(f"    [FAILED]")

    return format_error(routing_log, f"All services failed. Last Error: {output}")

# --- 6. MCP Tools ---

@mcp.tool()
def ask_chatgpt_cli(prompt: str, save_path: str = None, force_model: bool = False) -> str:
    return execute_with_failover("codex", "gemini", prompt, "execution", save_path, force_model)

@mcp.tool()
def ask_gemini_cli(prompt: str, save_path: str = None, force_model: bool = False) -> str:
    return execute_with_failover("gemini", "codex", prompt, "analysis", save_path, force_model)

@mcp.tool()
def ask_ollama(prompt: str, save_path: str = None, model: str = "llama3.2") -> str:
    is_safe, sec_msg = SecuritySanitizer.inspect(prompt, mode="execution")
    if not is_safe: return sec_msg
    
    success, output = run_cli_command("ollama", [model], prompt)
    if success:
        if save_path: return save_to_file(output, save_path)
        return f"[Source: Ollama]\n{output}"
    
    logger.warning("Ollama unreachable. Failing over to Cloud...")
    cloud_prompt = f"[WARNING: Local Ollama failed. Executing via Cloud Backup] {prompt}"
    return execute_with_failover("codex", "gemini", cloud_prompt, "execution", save_path, force_primary=False)

if __name__ == "__main__":
    mcp.run()
