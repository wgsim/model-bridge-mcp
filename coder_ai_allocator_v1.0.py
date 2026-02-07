import sys
import os
import shutil
import re
import logging
from typing import List, Tuple
from mcp.server.fastmcp import FastMCP
import subprocess

# --- 1. System Configuration & Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("CoderAIAllocator")

mcp = FastMCP("Coder AI Allocator v1.0")
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

# --- 3. Security Middleware ---
class SecuritySanitizer:
    
    BLOCK_PATTERNS = [
        r"rm\s+(-r[a-zA-Z]*f|-f[a-zA-Z]*r)\s+",
        r"mkfs\.",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&",
        r"dd\s+if=",
        r"chmod\s+777",
    ]

    SENSITIVE_PATHS = [
        r"/etc/", r"/var/", r"/boot/", r"/proc/", r"/root/"
    ]

    @staticmethod
    def inspect(prompt: str, mode: str = "execution") -> Tuple[bool, str]:
        for pattern in SecuritySanitizer.BLOCK_PATTERNS:
            if re.search(pattern, prompt):
                logger.warning(f"Security Block Triggered: {pattern}")
                return False, f"[SECURITY BLOCK] Destructive command pattern detected ({pattern}). Execution blocked."

        if mode == "execution":
            for path in SecuritySanitizer.SENSITIVE_PATHS:
                if path in prompt:
                    logger.warning(f"Sensitive Path Access Blocked: {path}")
                    return False, f"[SECURITY BLOCK] Write/Exec access to system path '{path}' is restricted."
        
        return True, ""

# --- 4. Execution Logic ---
def run_cli_command(service_name: str, args: List[str], input_text: str) -> Tuple[bool, str]:
    config = CLI_CONFIG.get(service_name, {})
    cmd_base = config.get("exec")
    
    if not cmd_base:
        return False, f"Configuration Error: No command defined for {service_name}"

    if not shutil.which(cmd_base[0]):
        return False, f"System Error: Command '{cmd_base[0]}' not found in PATH."

    full_cmd = cmd_base + args + [input_text]
    
    try:
        logger.info(f"Executing {service_name}...")
        result = subprocess.run(
            full_cmd,
            capture_output=True, text=True, env=my_env, check=False
        )
        
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            error_msg = (result.stdout + result.stderr).strip()
            logger.error(f"{service_name} failed with code {result.returncode}: {error_msg}")
            return False, error_msg

    except Exception as e:
        logger.error(f"Exception running {service_name}: {str(e)}")
        return False, str(e)

def get_health_report():
    report = "\n\n--- CLI Health Check ---\n"
    for tool_name in ["codex", "gemini", "ollama"]:
        cmd = CLI_CONFIG[tool_name].get("health")
        if cmd and shutil.which(cmd[0]):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, env=my_env, check=False)
                status = "Online" if res.returncode == 0 else "Error"
                report += f"[{tool_name.capitalize()}]: {status}\n"
            except:
                report += f"[{tool_name.capitalize()}]: Unreachable\n"
    return report

def execute_with_failover(primary: str, secondary: str, prompt: str, mode: str, force_primary: bool = False) -> str:
    is_safe, sec_msg = SecuritySanitizer.inspect(prompt, mode=mode)
    if not is_safe: return sec_msg

    routing_log = []
    
    # Tier 1: Primary
    routing_log.append(f"[1] Primary ({primary}): Trying...")
    success, output = run_cli_command(primary, [], prompt)
    
    if success:
        routing_log.append(f"    [SUCCESS]")
        return format_response(output, routing_log)
    
    routing_log.append(f"    [FAILED]: Process exited with error.")
    
    if force_primary:
        return format_error(routing_log, f"Forced Primary ({primary}) failed.\nError: {output}")

    # Tier 2: Secondary
    logger.warning(f"Failover triggered: {primary} -> {secondary}")
    routing_log.append(f"[2] Secondary ({secondary}): Trying...")
    
    failover_prompt = f"[Context: {primary} failed] {prompt}"
    success, output = run_cli_command(secondary, [], failover_prompt)
    
    if success:
        routing_log.append(f"    [SUCCESS]")
        return format_response(output, routing_log)
    
    routing_log.append(f"    [FAILED]")
    
    # Tier 3: Ollama (Only if we are not ALREADY in ask_ollama)
    # Since ask_ollama calls this function as a backup, we prevent infinite loops implicitly 
    # by not having Ollama as a tertiary backup here if it was the primary failure.
    # But for Codex/Gemini calls, we still want Ollama as backup.
    
    if primary != "ollama":
        logger.warning(f"Failover triggered: {secondary} -> Ollama")
        routing_log.append(f"[3] Final Backup (Ollama): Trying...")
        success, output = run_cli_command("ollama", ["llama3.2"], failover_prompt)
        if success:
            routing_log.append(f"    [SUCCESS]")
            return format_response(output, routing_log)
        routing_log.append(f"    [FAILED]")

    return format_error(routing_log, f"All services failed. Last Error: {output}")

def format_response(content: str, routing: List[str]) -> str:
    return f"{content}{get_health_report()}\n\n--- [Routing Log] ---\n" + "\n".join(routing)

def format_error(routing: List[str], msg: str) -> str:
    return f"[Task Execution Failed]\n{msg}{get_health_report()}\n\n--- [Routing Log] ---\n" + "\n".join(routing)

# --- 5. MCP Tools ---

@mcp.tool()
def ask_chatgpt_cli(prompt: str, force_model: bool = False) -> str:
    """Coding Task: Codex -> Gemini -> Ollama"""
    return execute_with_failover("codex", "gemini", prompt, "execution", force_model)

@mcp.tool()
def ask_gemini_cli(prompt: str, force_model: bool = False) -> str:
    """Analysis Task: Gemini -> Codex -> Ollama"""
    return execute_with_failover("gemini", "codex", prompt, "analysis", force_model)

@mcp.tool()
def ask_ollama(prompt: str, model: str = "llama3.2") -> str:
    """
    Local/Offline Task.
    IF Ollama is offline/unreachable, it will AUTOMATICALLY Failover to Codex -> Gemini.
    WARNING: Use caution with sensitive data if Ollama is off.
    """
    # 1. Security Check
    is_safe, sec_msg = SecuritySanitizer.inspect(prompt, mode="execution")
    if not is_safe: return sec_msg
    
    # 2. Try Ollama (Primary)
    success, output = run_cli_command("ollama", [model], prompt)
    if success:
        return f"[Source: Ollama]\n{output}{get_health_report()}"
    
    # 3. Failover to Cloud (Codex -> Gemini)
    logger.warning("Ollama unreachable. Failing over to Cloud (Codex)...")
    
    # Add a warning prefix to the prompt so the user knows this happened
    cloud_prompt = f"[WARNING: Local Ollama failed. Executing via Cloud Backup] {prompt}"
    
    # Reuse the failover logic starting with Codex
    return execute_with_failover("codex", "gemini", cloud_prompt, "execution", force_primary=False)

if __name__ == "__main__":
    mcp.run()
