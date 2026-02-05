"""ASCII art banners for Kōan startup sequences."""

from pathlib import Path

# ANSI color codes
CYAN = "\033[36m"
BLUE = "\033[34m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
WHITE = "\033[97m"
MAGENTA = "\033[35m"
GREEN = "\033[32m"
YELLOW = "\033[33m"

BANNERS_DIR = Path(__file__).parent


def _read_art(filename: str) -> str:
    """Read raw ASCII art from file."""
    art_file = BANNERS_DIR / filename
    if art_file.exists():
        return art_file.read_text()
    return ""


def colorize_agent(art: str) -> str:
    """Apply ANSI colors to the agent (run loop) banner."""
    lines = art.split("\n")
    colored = []
    for line in lines:
        # Eyes glow cyan
        line = line.replace("◉", f"{CYAN}◉{RESET}{DIM}{BLUE}")
        # Radioactive symbol in yellow
        line = line.replace("☢", f"{YELLOW}☢{RESET}{DIM}{BLUE}")
        colored.append(f"{DIM}{BLUE}{line}{RESET}")
    return "\n".join(colored)


def colorize_bridge(art: str) -> str:
    """Apply ANSI colors to the bridge (awake) banner."""
    lines = art.split("\n")
    colored = []
    for line in lines:
        # Signal waves in cyan
        line = line.replace("◇", f"{CYAN}◇{RESET}{DIM}{MAGENTA}")
        line = line.replace("◆", f"{CYAN}◆{RESET}{DIM}{MAGENTA}")
        # Arrows in green
        line = line.replace("→", f"{GREEN}→{RESET}{DIM}{MAGENTA}")
        line = line.replace("←", f"{GREEN}←{RESET}{DIM}{MAGENTA}")
        colored.append(f"{DIM}{MAGENTA}{line}{RESET}")
    return "\n".join(colored)


def print_agent_banner(version_info: str = "") -> None:
    """Print the agent loop startup banner."""
    art = _read_art("agent.txt")
    if not art:
        return
    print()
    print(colorize_agent(art), end="")
    if version_info:
        print(f"  {DIM}{WHITE}{version_info}{RESET}")
    else:
        print()
    print()


def print_bridge_banner(version_info: str = "") -> None:
    """Print the bridge (awake) startup banner."""
    art = _read_art("bridge.txt")
    if not art:
        return
    print()
    print(colorize_bridge(art), end="")
    if version_info:
        print(f"  {DIM}{WHITE}{version_info}{RESET}")
    else:
        print()
    print()


def colorize_startup(art: str) -> str:
    """Apply ANSI colors to the combined startup banner."""
    lines = art.split("\n")
    colored = []
    for line in lines:
        # Agent robot: eyes glow cyan, radioactive yellow
        line = line.replace("◉", f"{CYAN}◉{RESET}{DIM}{BLUE}")
        line = line.replace("☢", f"{YELLOW}☢{RESET}{DIM}{BLUE}")
        # Bridge signals: diamonds in cyan, arrows in green
        line = line.replace("◇", f"{CYAN}◇{RESET}{DIM}{BLUE}")
        line = line.replace("◆", f"{CYAN}◆{RESET}{DIM}{BLUE}")
        line = line.replace("→", f"{GREEN}→{RESET}{DIM}{BLUE}")
        line = line.replace("←", f"{GREEN}←{RESET}{DIM}{BLUE}")
        line = line.replace("↔", f"{GREEN}↔{RESET}{DIM}{BLUE}")
        # Box frame in bold cyan
        for ch in "╔╗╚╝═║":
            line = line.replace(ch, f"{BOLD}{CYAN}{ch}{RESET}{DIM}{BLUE}")
        # KOAN title in bold white
        if "K   Ō   A   N" in line:
            line = line.replace("K   Ō   A   N", f"{BOLD}{WHITE}K   Ō   A   N{RESET}{DIM}{BLUE}")
        colored.append(f"{DIM}{BLUE}{line}{RESET}")
    return "\n".join(colored)


def print_startup_banner() -> None:
    """Print the combined startup banner (used by unified launcher)."""
    art = _read_art("startup.txt")
    if not art:
        return
    print(colorize_startup(art))
